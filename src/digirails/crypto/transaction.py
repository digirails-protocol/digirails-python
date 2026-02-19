"""DigiByte transaction construction, BIP-143 SegWit signing, and serialization.

Implements the subset needed for DR-Pay: P2WPKH inputs, P2WPKH/P2PKH/OP_RETURN outputs.
DigiByte uses the same transaction format and signing algorithm as Bitcoin.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

from digirails.crypto.keys import privkey_to_pubkey, sign_data
from digirails.crypto.script import (
    OP_CHECKSIG,
    OP_DUP,
    OP_EQUALVERIFY,
    OP_HASH160,
    address_to_script_pubkey,
    op_return_script,
)
from digirails.network.params import MAINNET, NetworkParams

# Sighash types
SIGHASH_ALL = 0x01


def _double_sha256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def _serialize_varint(n: int) -> bytes:
    if n < 0xFD:
        return struct.pack("<B", n)
    elif n <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", n)
    elif n <= 0xFFFFFFFF:
        return b"\xfe" + struct.pack("<I", n)
    else:
        return b"\xff" + struct.pack("<Q", n)


def _push_data(data: bytes) -> bytes:
    """Encode a data push for script."""
    length = len(data)
    if length <= 75:
        return bytes([length]) + data
    elif length <= 255:
        return bytes([0x4C, length]) + data
    elif length <= 65535:
        return bytes([0x4D]) + struct.pack("<H", length) + data
    else:
        raise ValueError(f"Push data too large: {length}")


@dataclass
class TxInput:
    txid: str  # Previous tx hash (hex, big-endian display order)
    vout: int  # Output index
    amount: int  # Value in satoshis (needed for SegWit signing)
    script_pubkey: bytes  # scriptPubKey of the UTXO being spent
    sequence: int = 0xFFFFFFFE


@dataclass
class TxOutput:
    script_pubkey: bytes  # Destination scriptPubKey
    amount: int  # Value in satoshis


class Transaction:
    """Construct, sign, and serialize a DigiByte SegWit transaction."""

    def __init__(self, version: int = 2, locktime: int = 0):
        self.version = version
        self.locktime = locktime
        self.inputs: list[TxInput] = []
        self.outputs: list[TxOutput] = []
        self._witnesses: list[list[bytes]] = []

    def add_input(self, inp: TxInput) -> None:
        self.inputs.append(inp)
        self._witnesses.append([])  # Empty witness initially

    def add_output(self, out: TxOutput) -> None:
        self.outputs.append(out)

    def add_op_return(self, data: bytes) -> None:
        """Add an OP_RETURN output (zero value)."""
        self.outputs.append(TxOutput(script_pubkey=op_return_script(data), amount=0))

    def _bip143_sighash(self, input_index: int, sighash_type: int = SIGHASH_ALL) -> bytes:
        """Compute BIP-143 sighash for a P2WPKH input.

        BIP-143 defines the serialization for SegWit signature hashing:
        1. nVersion
        2. hashPrevouts
        3. hashSequence
        4. outpoint (txid + vout)
        5. scriptCode (P2PKH script for P2WPKH)
        6. value
        7. nSequence
        8. hashOutputs
        9. nLockTime
        10. sighash type
        """
        inp = self.inputs[input_index]

        # hashPrevouts: double-SHA256 of all outpoints
        prevouts = b""
        for i in self.inputs:
            prevouts += bytes.fromhex(i.txid)[::-1]  # txid is big-endian display, reverse for internal
            prevouts += struct.pack("<I", i.vout)
        hash_prevouts = _double_sha256(prevouts)

        # hashSequence: double-SHA256 of all sequences
        sequences = b""
        for i in self.inputs:
            sequences += struct.pack("<I", i.sequence)
        hash_sequence = _double_sha256(sequences)

        # outpoint being signed
        outpoint = bytes.fromhex(inp.txid)[::-1] + struct.pack("<I", inp.vout)

        # scriptCode for P2WPKH: standard P2PKH script using the keyhash from the witness program
        keyhash = inp.script_pubkey[2:]  # P2WPKH scriptPubKey is [OP_0, 0x14, <20-byte hash>]
        script_code = bytes([OP_DUP, OP_HASH160, 0x14]) + keyhash + bytes([OP_EQUALVERIFY, OP_CHECKSIG])
        script_code_with_len = _serialize_varint(len(script_code)) + script_code

        # value
        value = struct.pack("<q", inp.amount)

        # sequence
        n_sequence = struct.pack("<I", inp.sequence)

        # hashOutputs: double-SHA256 of all outputs
        outputs = b""
        for o in self.outputs:
            outputs += struct.pack("<q", o.amount)
            outputs += _serialize_varint(len(o.script_pubkey)) + o.script_pubkey
        hash_outputs = _double_sha256(outputs)

        # Assemble the preimage
        preimage = (
            struct.pack("<i", self.version)
            + hash_prevouts
            + hash_sequence
            + outpoint
            + script_code_with_len
            + value
            + n_sequence
            + hash_outputs
            + struct.pack("<I", self.locktime)
            + struct.pack("<I", sighash_type)
        )

        return _double_sha256(preimage)

    def sign_input(self, input_index: int, private_key: bytes) -> None:
        """Sign a P2WPKH input using BIP-143."""
        sighash = self._bip143_sighash(input_index)
        signature = sign_data(private_key, sighash)
        # Append sighash type byte to DER signature
        sig_with_hashtype = signature + bytes([SIGHASH_ALL])
        pubkey = privkey_to_pubkey(private_key)
        # SegWit witness: [signature, pubkey]
        self._witnesses[input_index] = [sig_with_hashtype, pubkey]

    def serialize(self) -> bytes:
        """Serialize the transaction in SegWit format (BIP-144)."""
        has_witness = any(w for w in self._witnesses)
        parts: list[bytes] = []

        # Version
        parts.append(struct.pack("<i", self.version))

        # SegWit marker and flag
        if has_witness:
            parts.append(b"\x00\x01")

        # Input count
        parts.append(_serialize_varint(len(self.inputs)))

        # Inputs (scriptSig is empty for SegWit)
        for inp in self.inputs:
            parts.append(bytes.fromhex(inp.txid)[::-1])  # txid little-endian
            parts.append(struct.pack("<I", inp.vout))
            parts.append(b"\x00")  # empty scriptSig
            parts.append(struct.pack("<I", inp.sequence))

        # Output count
        parts.append(_serialize_varint(len(self.outputs)))

        # Outputs
        for out in self.outputs:
            parts.append(struct.pack("<q", out.amount))
            parts.append(_serialize_varint(len(out.script_pubkey)) + out.script_pubkey)

        # Witness data
        if has_witness:
            for witness_items in self._witnesses:
                parts.append(_serialize_varint(len(witness_items)))
                for item in witness_items:
                    parts.append(_serialize_varint(len(item)) + item)

        # Locktime
        parts.append(struct.pack("<I", self.locktime))

        return b"".join(parts)

    def txid(self) -> str:
        """Compute the transaction ID (double-SHA256 of non-witness serialization)."""
        # txid is computed WITHOUT witness data
        parts: list[bytes] = []
        parts.append(struct.pack("<i", self.version))
        parts.append(_serialize_varint(len(self.inputs)))
        for inp in self.inputs:
            parts.append(bytes.fromhex(inp.txid)[::-1])
            parts.append(struct.pack("<I", inp.vout))
            parts.append(b"\x00")
            parts.append(struct.pack("<I", inp.sequence))
        parts.append(_serialize_varint(len(self.outputs)))
        for out in self.outputs:
            parts.append(struct.pack("<q", out.amount))
            parts.append(_serialize_varint(len(out.script_pubkey)) + out.script_pubkey)
        parts.append(struct.pack("<I", self.locktime))
        raw = b"".join(parts)
        return _double_sha256(raw)[::-1].hex()

    def hex(self) -> str:
        """Return the serialized transaction as a hex string."""
        return self.serialize().hex()


def build_payment_tx(
    utxos: list[tuple[str, int, int, bytes]],  # (txid, vout, amount_sat, script_pubkey)
    to_address: str,
    amount_sat: int,
    change_address: str,
    fee_sat: int = 1000,
    op_return_data: bytes | None = None,
    network: NetworkParams = MAINNET,
) -> Transaction:
    """Build a standard payment transaction.

    Args:
        utxos: List of (txid, vout, amount_sat, script_pubkey) tuples.
        to_address: Destination address.
        amount_sat: Amount to send in satoshis.
        change_address: Address for change output.
        fee_sat: Transaction fee in satoshis.
        op_return_data: Optional OP_RETURN data.
        network: Network parameters.

    Returns:
        Unsigned Transaction ready for signing.
    """
    # Calculate totals
    total_in = sum(u[2] for u in utxos)
    total_out = amount_sat + fee_sat
    change = total_in - total_out

    if change < 0:
        raise ValueError(
            f"Insufficient funds: have {total_in} sat, need {total_out} sat"
        )

    tx = Transaction()

    # Add inputs
    for txid, vout, amt, spk in utxos:
        tx.add_input(TxInput(txid=txid, vout=vout, amount=amt, script_pubkey=spk))

    # Payment output
    tx.add_output(
        TxOutput(
            script_pubkey=address_to_script_pubkey(to_address, network),
            amount=amount_sat,
        )
    )

    # Change output (skip dust)
    if change > 546:  # Dust threshold
        tx.add_output(
            TxOutput(
                script_pubkey=address_to_script_pubkey(change_address, network),
                amount=change,
            )
        )

    # OP_RETURN output
    if op_return_data is not None:
        tx.add_op_return(op_return_data)

    return tx
