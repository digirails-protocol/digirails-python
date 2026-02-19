"""Key generation, address derivation, and WIF encoding for DigiByte."""

from __future__ import annotations

import hashlib
import os

from digirails.crypto.base58 import b58decode_check, b58encode_check
from digirails.crypto.bech32 import decode_segwit_address, encode_segwit_address
from digirails.network.params import MAINNET, REGTEST, TESTNET, NetworkParams

# Try native secp256k1 first, fall back to pure-Python ecdsa
try:
    from coincurve import PrivateKey as _CoinPrivateKey

    _BACKEND = "coincurve"
except ImportError:
    from ecdsa import SECP256k1, SigningKey as _ECDSASigningKey  # type: ignore[no-redef]

    _BACKEND = "ecdsa"


def _hash160(data: bytes) -> bytes:
    """RIPEMD-160(SHA-256(data))."""
    sha = hashlib.sha256(data).digest()
    return hashlib.new("ripemd160", sha).digest()


def generate_keypair(
    network: NetworkParams = MAINNET,
) -> tuple[bytes, bytes, str]:
    """Generate a new secp256k1 key pair.

    Returns:
        (private_key_bytes_32, compressed_public_key_bytes_33, bech32_address)
    """
    privkey = os.urandom(32)
    pubkey = privkey_to_pubkey(privkey)
    address = pubkey_to_p2wpkh_address(pubkey, network)
    return privkey, pubkey, address


def privkey_to_pubkey(private_key: bytes, compressed: bool = True) -> bytes:
    """Derive public key from private key bytes."""
    if _BACKEND == "coincurve":
        pk = _CoinPrivateKey(private_key)
        return pk.public_key.format(compressed=compressed)
    else:
        sk = _ECDSASigningKey.from_string(private_key, curve=SECP256k1)
        vk = sk.get_verifying_key()
        if compressed:
            x = vk.pubkey.point.x()
            y = vk.pubkey.point.y()
            prefix = b"\x02" if y % 2 == 0 else b"\x03"
            return prefix + x.to_bytes(32, "big")
        return b"\x04" + vk.to_string()


def sign_data(private_key: bytes, data: bytes) -> bytes:
    """Sign a 32-byte hash and return a DER-encoded signature."""
    if _BACKEND == "coincurve":
        pk = _CoinPrivateKey(private_key)
        return pk.sign(data, hasher=None)
    else:
        from ecdsa.util import sigencode_der  # type: ignore[import-untyped]

        sk = _ECDSASigningKey.from_string(private_key, curve=SECP256k1)
        return sk.sign_digest(data, sigencode=sigencode_der)


def pubkey_to_p2wpkh_address(pubkey: bytes, network: NetworkParams = MAINNET) -> str:
    """Derive P2WPKH (dgb1q...) address from compressed public key."""
    assert len(pubkey) == 33, "Expected 33-byte compressed public key"
    keyhash = _hash160(pubkey)
    addr = encode_segwit_address(network.bech32_hrp, 0, keyhash)
    if addr is None:
        raise ValueError("Failed to encode segwit address")
    return addr


def pubkey_to_p2pkh_address(pubkey: bytes, network: NetworkParams = MAINNET) -> str:
    """Derive P2PKH (D...) address from public key."""
    keyhash = _hash160(pubkey)
    payload = bytes([network.pubkey_version]) + keyhash
    return b58encode_check(payload)


def privkey_to_wif(
    private_key: bytes, network: NetworkParams = MAINNET, compressed: bool = True
) -> str:
    """Encode private key as WIF string."""
    payload = bytes([network.wif_version]) + private_key
    if compressed:
        payload += b"\x01"
    return b58encode_check(payload)


def wif_to_privkey(wif: str) -> tuple[bytes, bool, NetworkParams]:
    """Decode WIF string to (private_key_bytes, compressed, network)."""
    payload = b58decode_check(wif)
    version = payload[0]

    # Determine network from version byte
    if version == MAINNET.wif_version:
        network = MAINNET
    elif version == TESTNET.wif_version:
        # TESTNET and REGTEST share WIF version byte
        network = TESTNET
    else:
        raise ValueError(f"Unknown WIF version byte: 0x{version:02x}")

    if len(payload) == 34 and payload[-1] == 0x01:
        return payload[1:33], True, network
    elif len(payload) == 33:
        return payload[1:33], False, network
    else:
        raise ValueError(f"Invalid WIF payload length: {len(payload)}")


def validate_address(address: str, network: NetworkParams | None = None) -> bool:
    """Validate a DigiByte address (P2PKH, P2WPKH, or P2TR)."""
    # Try bech32/bech32m (dgb1q... / dgb1p...)
    networks_to_try = [network] if network else [MAINNET, TESTNET, REGTEST]
    for net in networks_to_try:
        witver, witprog = decode_segwit_address(net.bech32_hrp, address)
        if witver is not None and witprog is not None:
            return True

    # Try Base58Check (D... legacy)
    try:
        payload = b58decode_check(address)
        version = payload[0]
        for net in networks_to_try:
            if version in (net.pubkey_version, net.script_version):
                return len(payload) == 21
    except (ValueError, IndexError):
        pass

    return False
