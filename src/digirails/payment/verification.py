"""Payment verification: validate that a transaction pays an invoice correctly."""

from __future__ import annotations

import struct

from digirails.crypto.script import address_to_script_pubkey
from digirails.exceptions import VerificationError
from digirails.network.params import MAINNET, NetworkParams


def _parse_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Parse a Bitcoin varint. Returns (value, new_offset)."""
    first = data[offset]
    if first < 0xFD:
        return first, offset + 1
    elif first == 0xFD:
        return struct.unpack_from("<H", data, offset + 1)[0], offset + 3
    elif first == 0xFE:
        return struct.unpack_from("<I", data, offset + 1)[0], offset + 5
    else:
        return struct.unpack_from("<Q", data, offset + 1)[0], offset + 9


def verify_raw_tx(
    raw_tx_hex: str,
    expected_address: str,
    expected_amount_sat: int,
    network: NetworkParams = MAINNET,
) -> tuple[str, int]:
    """Verify that a raw transaction pays the expected address and amount.

    Returns (txid_hex, matching_vout) if valid.
    Raises VerificationError if not.
    """
    raw = bytes.fromhex(raw_tx_hex)
    expected_spk = address_to_script_pubkey(expected_address, network)

    # Parse enough of the transaction to find outputs
    offset = 0

    # Version (4 bytes)
    offset += 4

    # Check for SegWit marker
    is_segwit = raw[offset] == 0x00 and raw[offset + 1] == 0x01
    if is_segwit:
        offset += 2  # Skip marker + flag

    # Input count
    input_count, offset = _parse_varint(raw, offset)

    # Skip inputs
    for _ in range(input_count):
        offset += 32  # prev txid
        offset += 4  # prev vout
        script_len, offset = _parse_varint(raw, offset)
        offset += script_len  # scriptSig
        offset += 4  # sequence

    # Output count
    output_count, offset = _parse_varint(raw, offset)

    # Parse outputs
    for vout_idx in range(output_count):
        value = struct.unpack_from("<q", raw, offset)[0]
        offset += 8
        spk_len, offset = _parse_varint(raw, offset)
        spk = raw[offset : offset + spk_len]
        offset += spk_len

        if spk == expected_spk and value >= expected_amount_sat:
            # txid must be computed from non-witness serialization;
            # for simplicity, return "pending" and let caller verify via RPC.
            return ("pending", vout_idx)

    raise VerificationError(
        f"No output pays {expected_address} with >= {expected_amount_sat} sat"
    )


def verify_raw_tx_simple(
    raw_tx_hex: str,
    expected_address: str,
    expected_amount_sat: int,
    network: NetworkParams = MAINNET,
) -> int:
    """Simplified verification: check outputs match, return matching vout index.

    For mempool-tier payments where the seller validates before mining.
    Does NOT compute the txid (use RPC for that after broadcast).
    """
    raw = bytes.fromhex(raw_tx_hex)
    expected_spk = address_to_script_pubkey(expected_address, network)

    offset = 4  # Skip version

    # Check for SegWit marker
    if raw[offset] == 0x00 and raw[offset + 1] == 0x01:
        offset += 2

    # Skip inputs
    input_count, offset = _parse_varint(raw, offset)
    for _ in range(input_count):
        offset += 36  # prev_txid (32) + prev_vout (4)
        script_len, offset = _parse_varint(raw, offset)
        offset += script_len + 4  # scriptSig + sequence

    # Parse outputs
    output_count, offset = _parse_varint(raw, offset)
    for vout_idx in range(output_count):
        value = struct.unpack_from("<q", raw, offset)[0]
        offset += 8
        spk_len, offset = _parse_varint(raw, offset)
        spk = raw[offset : offset + spk_len]
        offset += spk_len

        if spk == expected_spk and value >= expected_amount_sat:
            return vout_idx

    raise VerificationError(
        f"No output pays {expected_address} with >= {expected_amount_sat} sat"
    )
