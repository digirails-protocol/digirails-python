"""Bitcoin Script builders for DigiByte transaction outputs."""

from __future__ import annotations


from digirails.crypto.base58 import b58decode_check
from digirails.crypto.bech32 import decode_segwit_address
from digirails.network.params import MAINNET, NetworkParams

# Opcodes
OP_0 = 0x00
OP_RETURN = 0x6A
OP_DUP = 0x76
OP_HASH160 = 0xA9
OP_EQUALVERIFY = 0x88
OP_CHECKSIG = 0xAC


def p2wpkh_script_pubkey(keyhash: bytes) -> bytes:
    """Build P2WPKH scriptPubKey: OP_0 <20-byte-keyhash>."""
    assert len(keyhash) == 20
    return bytes([OP_0, 0x14]) + keyhash


def p2pkh_script_pubkey(keyhash: bytes) -> bytes:
    """Build P2PKH scriptPubKey: OP_DUP OP_HASH160 <20> <keyhash> OP_EQUALVERIFY OP_CHECKSIG."""
    assert len(keyhash) == 20
    return bytes([OP_DUP, OP_HASH160, 0x14]) + keyhash + bytes([OP_EQUALVERIFY, OP_CHECKSIG])


def op_return_script(data: bytes) -> bytes:
    """Build OP_RETURN scriptPubKey with push data."""
    assert len(data) <= 80, f"OP_RETURN data too large: {len(data)} bytes (max 80)"
    # OP_RETURN <pushbytes_N> <data>
    if len(data) <= 75:
        return bytes([OP_RETURN, len(data)]) + data
    elif len(data) <= 255:
        return bytes([OP_RETURN, 0x4C, len(data)]) + data  # OP_PUSHDATA1
    else:
        raise ValueError("OP_RETURN data too large")


def address_to_script_pubkey(address: str, network: NetworkParams = MAINNET) -> bytes:
    """Convert a DigiByte address to its scriptPubKey."""
    # Try bech32 (P2WPKH)
    witver, witprog = decode_segwit_address(network.bech32_hrp, address)
    if witver is not None and witprog is not None:
        if witver == 0 and len(witprog) == 20:
            return p2wpkh_script_pubkey(witprog)
        elif witver == 1 and len(witprog) == 32:
            # P2TR: OP_1 <32-byte-pubkey>
            return bytes([0x51, 0x20]) + witprog
        else:
            raise ValueError(f"Unsupported witness version {witver}")

    # Try Base58Check (P2PKH)
    payload = b58decode_check(address)
    version = payload[0]
    keyhash = payload[1:]
    if version == network.pubkey_version and len(keyhash) == 20:
        return p2pkh_script_pubkey(keyhash)
    elif version == network.script_version and len(keyhash) == 20:
        # P2SH: OP_HASH160 <20> <hash> OP_EQUAL
        return bytes([OP_HASH160, 0x14]) + keyhash + bytes([0x87])

    raise ValueError(f"Cannot convert address to scriptPubKey: {address}")


def script_pubkey_to_keyhash(script: bytes) -> bytes | None:
    """Extract the 20-byte keyhash from a P2WPKH or P2PKH scriptPubKey."""
    # P2WPKH: 00 14 <20 bytes>
    if len(script) == 22 and script[0] == OP_0 and script[1] == 0x14:
        return script[2:]
    # P2PKH: 76 a9 14 <20 bytes> 88 ac
    if (
        len(script) == 25
        and script[0] == OP_DUP
        and script[1] == OP_HASH160
        and script[2] == 0x14
        and script[23] == OP_EQUALVERIFY
        and script[24] == OP_CHECKSIG
    ):
        return script[3:23]
    return None
