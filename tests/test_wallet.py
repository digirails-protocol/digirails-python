"""Tests for wallet, UTXO tracking, and keystore."""

import os
import tempfile

import pytest

from digirails.wallet.keystore import EncryptedKeystore, EnvKeystore, RawKeystore
from digirails.wallet.utxo import Utxo, UtxoSet


class TestUtxoSet:
    def test_add_and_total(self):
        us = UtxoSet()
        us.add(Utxo("aa" * 32, 0, 100_000, b"\x00" * 22))
        us.add(Utxo("bb" * 32, 1, 200_000, b"\x00" * 22))
        assert us.total_sat == 300_000

    def test_remove(self):
        us = UtxoSet()
        us.add(Utxo("aa" * 32, 0, 100_000, b"\x00" * 22))
        us.remove("aa" * 32, 0)
        assert us.total_sat == 0

    def test_select_largest_first(self):
        us = UtxoSet()
        us.add(Utxo("aa" * 32, 0, 50_000, b"\x00" * 22))
        us.add(Utxo("bb" * 32, 0, 200_000, b"\x00" * 22))
        us.add(Utxo("cc" * 32, 0, 100_000, b"\x00" * 22))

        selected = us.select(150_000)
        assert len(selected) == 1
        assert selected[0].amount_sat == 200_000

    def test_select_multiple(self):
        us = UtxoSet()
        us.add(Utxo("aa" * 32, 0, 50_000, b"\x00" * 22))
        us.add(Utxo("bb" * 32, 0, 60_000, b"\x00" * 22))
        us.add(Utxo("cc" * 32, 0, 70_000, b"\x00" * 22))

        selected = us.select(120_000)
        assert len(selected) == 2
        total = sum(u.amount_sat for u in selected)
        assert total >= 120_000

    def test_select_insufficient_funds(self):
        us = UtxoSet()
        us.add(Utxo("aa" * 32, 0, 1000, b"\x00" * 22))
        with pytest.raises(ValueError, match="Insufficient"):
            us.select(50_000)

    def test_utxo_amount_dgb(self):
        u = Utxo("aa" * 32, 0, 100_000_000, b"\x00" * 22)
        from decimal import Decimal

        assert u.amount_dgb == Decimal("1")


class TestRawKeystore:
    def test_load(self):
        key = os.urandom(32)
        ks = RawKeystore(key)
        assert ks.load() == key

    def test_invalid_length(self):
        with pytest.raises(Exception):
            RawKeystore(b"\x00" * 16)


class TestEncryptedKeystore:
    def test_roundtrip(self):
        key = os.urandom(32)
        with tempfile.NamedTemporaryFile(suffix=".keyfile", delete=False) as f:
            path = f.name
        try:
            ks = EncryptedKeystore(path, "mypassword")
            ks.save(key)
            loaded = ks.load()
            assert loaded == key
        finally:
            os.unlink(path)

    def test_wrong_password(self):
        key = os.urandom(32)
        with tempfile.NamedTemporaryFile(suffix=".keyfile", delete=False) as f:
            path = f.name
        try:
            EncryptedKeystore(path, "correct").save(key)
            with pytest.raises(Exception, match="[Dd]ecryption|password|corrupted"):
                EncryptedKeystore(path, "wrong").load()
        finally:
            os.unlink(path)


class TestEnvKeystore:
    def test_load(self):
        key = os.urandom(32)
        os.environ["TEST_DR_KEY"] = key.hex()
        try:
            ks = EnvKeystore("TEST_DR_KEY")
            assert ks.load() == key
        finally:
            del os.environ["TEST_DR_KEY"]

    def test_missing_env(self):
        ks = EnvKeystore("NONEXISTENT_DR_KEY_12345")
        with pytest.raises(Exception, match="not set"):
            ks.load()
