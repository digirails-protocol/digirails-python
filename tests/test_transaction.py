"""Tests for transaction construction and signing."""

from digirails.crypto.keys import _hash160, generate_keypair
from digirails.crypto.script import p2wpkh_script_pubkey
from digirails.crypto.transaction import (
    Transaction,
    TxInput,
    TxOutput,
    build_payment_tx,
)
from digirails.network.params import MAINNET, REGTEST


class TestTransaction:
    def test_build_and_serialize(self):
        privkey, pubkey, addr = generate_keypair(MAINNET)
        keyhash = _hash160(pubkey)
        spk = p2wpkh_script_pubkey(keyhash)

        tx = Transaction()
        tx.add_input(TxInput(txid="aa" * 32, vout=0, amount=100000, script_pubkey=spk))
        tx.add_output(TxOutput(script_pubkey=spk, amount=90000))

        tx.sign_input(0, privkey)
        raw = tx.serialize()

        # Should be valid SegWit format: version + marker + flag + ...
        assert raw[:4] == b"\x02\x00\x00\x00"  # version 2
        assert raw[4:6] == b"\x00\x01"  # SegWit marker + flag
        assert len(raw) > 100

    def test_txid_is_deterministic(self):
        privkey, pubkey, _ = generate_keypair(MAINNET)
        spk = p2wpkh_script_pubkey(_hash160(pubkey))

        tx = Transaction()
        tx.add_input(TxInput(txid="bb" * 32, vout=1, amount=50000, script_pubkey=spk))
        tx.add_output(TxOutput(script_pubkey=spk, amount=40000))
        tx.sign_input(0, privkey)

        txid1 = tx.txid()
        txid2 = tx.txid()
        assert txid1 == txid2
        assert len(txid1) == 64

    def test_op_return_output(self):
        privkey, pubkey, _ = generate_keypair(MAINNET)
        spk = p2wpkh_script_pubkey(_hash160(pubkey))

        tx = Transaction()
        tx.add_input(TxInput(txid="cc" * 32, vout=0, amount=100000, script_pubkey=spk))
        tx.add_output(TxOutput(script_pubkey=spk, amount=90000))
        tx.add_op_return(b"\x44\x52\x01\x01\x01")  # DR-Pay header
        tx.sign_input(0, privkey)

        raw = tx.hex()
        assert "6a054452010101" in raw  # OP_RETURN + push5 + DR header

    def test_build_payment_tx(self):
        privkey, pubkey, addr = generate_keypair(REGTEST)
        spk = p2wpkh_script_pubkey(_hash160(pubkey))

        utxos = [("dd" * 32, 0, 1_000_000, spk)]

        # Build to a different address
        _, _, to_addr = generate_keypair(REGTEST)
        tx = build_payment_tx(
            utxos=utxos,
            to_address=to_addr,
            amount_sat=500_000,
            change_address=addr,
            fee_sat=1000,
            network=REGTEST,
        )

        assert len(tx.inputs) == 1
        assert len(tx.outputs) == 2  # payment + change
        assert tx.outputs[0].amount == 500_000
        assert tx.outputs[1].amount == 499_000  # 1_000_000 - 500_000 - 1000

    def test_build_payment_tx_with_op_return(self):
        privkey, pubkey, addr = generate_keypair(REGTEST)
        spk = p2wpkh_script_pubkey(_hash160(pubkey))

        utxos = [("ee" * 32, 0, 200_000, spk)]
        _, _, to_addr = generate_keypair(REGTEST)

        tx = build_payment_tx(
            utxos=utxos,
            to_address=to_addr,
            amount_sat=100_000,
            change_address=addr,
            fee_sat=1000,
            op_return_data=b"\x44\x52\x01\x01\x02" + b"\x00" * 16,
            network=REGTEST,
        )

        assert len(tx.outputs) == 3  # payment + change + OP_RETURN
        assert tx.outputs[2].amount == 0  # OP_RETURN has zero value

    def test_insufficient_funds_raises(self):
        import pytest

        privkey, pubkey, addr = generate_keypair(REGTEST)
        spk = p2wpkh_script_pubkey(_hash160(pubkey))

        utxos = [("ff" * 32, 0, 1000, spk)]
        _, _, to_addr = generate_keypair(REGTEST)

        with pytest.raises(ValueError, match="Insufficient funds"):
            build_payment_tx(
                utxos=utxos,
                to_address=to_addr,
                amount_sat=500_000,
                change_address=addr,
                fee_sat=1000,
                network=REGTEST,
            )
