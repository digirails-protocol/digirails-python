"""Tests for bech32/bech32m encoding and decoding."""

from digirails.crypto.bech32 import (
    decode_segwit_address,
    encode_segwit_address,
)


def test_encode_decode_roundtrip_dgb():
    """P2WPKH address (witness v0) should use bech32."""
    keyhash = bytes(range(20))
    addr = encode_segwit_address("dgb", 0, keyhash)
    assert addr is not None
    assert addr.startswith("dgb1q")
    witver, witprog = decode_segwit_address("dgb", addr)
    assert witver == 0
    assert witprog == keyhash


def test_encode_decode_roundtrip_regtest():
    """Regtest addresses use dgbrt prefix."""
    keyhash = bytes(range(20))
    addr = encode_segwit_address("dgbrt", 0, keyhash)
    assert addr is not None
    assert addr.startswith("dgbrt1q")
    witver, witprog = decode_segwit_address("dgbrt", addr)
    assert witver == 0
    assert witprog == keyhash


def test_taproot_address_uses_bech32m():
    """P2TR address (witness v1, 32 bytes) should use bech32m."""
    xonly_pubkey = bytes(range(32))
    addr = encode_segwit_address("dgb", 1, xonly_pubkey)
    assert addr is not None
    assert addr.startswith("dgb1p")
    witver, witprog = decode_segwit_address("dgb", addr)
    assert witver == 1
    assert witprog == xonly_pubkey


def test_wrong_hrp_fails():
    keyhash = bytes(range(20))
    addr = encode_segwit_address("dgb", 0, keyhash)
    assert addr is not None
    witver, witprog = decode_segwit_address("btc", addr)
    assert witver is None


def test_invalid_address():
    witver, witprog = decode_segwit_address("dgb", "dgb1qinvalid")
    assert witver is None
