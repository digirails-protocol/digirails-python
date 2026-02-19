"""Tests for key generation, address derivation, and WIF encoding."""

import pytest

from digirails.crypto.base58 import b58decode_check, b58encode_check
from digirails.crypto.keys import (
    generate_keypair,
    privkey_to_pubkey,
    privkey_to_wif,
    pubkey_to_p2pkh_address,
    pubkey_to_p2wpkh_address,
    validate_address,
    wif_to_privkey,
)
from digirails.network.params import MAINNET, REGTEST, TESTNET


class TestKeyGeneration:
    def test_generate_mainnet(self):
        privkey, pubkey, address = generate_keypair(MAINNET)
        assert len(privkey) == 32
        assert len(pubkey) == 33
        assert address.startswith("dgb1q")

    def test_generate_regtest(self):
        _, _, address = generate_keypair(REGTEST)
        assert address.startswith("dgbrt1q")

    def test_generate_testnet(self):
        _, _, address = generate_keypair(TESTNET)
        assert address.startswith("dgbt1q")

    def test_compressed_pubkey(self):
        privkey, pubkey, _ = generate_keypair(MAINNET)
        assert pubkey[0] in (0x02, 0x03)
        assert len(pubkey) == 33

    def test_deterministic_pubkey(self):
        privkey = bytes(range(1, 33))
        pub1 = privkey_to_pubkey(privkey)
        pub2 = privkey_to_pubkey(privkey)
        assert pub1 == pub2


class TestWIF:
    def test_wif_roundtrip_mainnet(self):
        privkey, _, _ = generate_keypair(MAINNET)
        wif = privkey_to_wif(privkey, MAINNET)
        recovered, compressed, network = wif_to_privkey(wif)
        assert recovered == privkey
        assert compressed is True
        assert network == MAINNET

    def test_wif_roundtrip_regtest(self):
        privkey, _, _ = generate_keypair(REGTEST)
        wif = privkey_to_wif(privkey, REGTEST)
        recovered, compressed, _ = wif_to_privkey(wif)
        assert recovered == privkey

    def test_invalid_wif(self):
        with pytest.raises(ValueError):
            wif_to_privkey("notavalidwif")


class TestAddressDerivation:
    def test_p2wpkh_address(self):
        privkey = bytes(range(1, 33))
        pubkey = privkey_to_pubkey(privkey)
        addr = pubkey_to_p2wpkh_address(pubkey, MAINNET)
        assert addr.startswith("dgb1q")
        assert validate_address(addr, MAINNET)

    def test_p2pkh_address(self):
        privkey = bytes(range(1, 33))
        pubkey = privkey_to_pubkey(privkey)
        addr = pubkey_to_p2pkh_address(pubkey, MAINNET)
        assert addr.startswith("D")
        assert validate_address(addr, MAINNET)


class TestAddressValidation:
    def test_valid_segwit(self):
        _, _, addr = generate_keypair(MAINNET)
        assert validate_address(addr)

    def test_valid_legacy(self):
        privkey = bytes(range(1, 33))
        pubkey = privkey_to_pubkey(privkey)
        addr = pubkey_to_p2pkh_address(pubkey, MAINNET)
        assert validate_address(addr)

    def test_invalid(self):
        assert not validate_address("invalid")
        assert not validate_address("")
        assert not validate_address("bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4")  # Bitcoin, not DGB


class TestBase58:
    def test_roundtrip(self):
        payload = bytes(range(21))
        encoded = b58encode_check(payload)
        decoded = b58decode_check(encoded)
        assert decoded == payload

    def test_invalid_checksum(self):
        payload = bytes(range(21))
        encoded = b58encode_check(payload)
        # Corrupt last character
        corrupted = encoded[:-1] + ("a" if encoded[-1] != "a" else "b")
        with pytest.raises(ValueError, match="checksum"):
            b58decode_check(corrupted)
