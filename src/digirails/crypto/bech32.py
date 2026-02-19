"""Bech32/Bech32m encoding and decoding.

Vendored from the BIP-173/BIP-350 reference implementation.
Adapted for DigiByte address prefixes (dgb, dgbt, dgbrt).
"""

from __future__ import annotations

from enum import IntEnum

CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


class Encoding(IntEnum):
    BECH32 = 1
    BECH32M = 2


BECH32M_CONST = 0x2BC830A3


def _bech32_polymod(values: list[int]) -> int:
    """Internal function that computes the Bech32 checksum."""
    GEN = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            chk ^= GEN[i] if ((b >> i) & 1) else 0
    return chk


def _bech32_hrp_expand(hrp: str) -> list[int]:
    """Expand the HRP into values for checksum computation."""
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _bech32_verify_checksum(hrp: str, data: list[int]) -> Encoding | None:
    """Verify a checksum given HRP and converted data characters."""
    const = _bech32_polymod(_bech32_hrp_expand(hrp) + data)
    if const == 1:
        return Encoding.BECH32
    if const == BECH32M_CONST:
        return Encoding.BECH32M
    return None


def _bech32_create_checksum(hrp: str, data: list[int], spec: Encoding) -> list[int]:
    """Compute the checksum values given HRP and data."""
    values = _bech32_hrp_expand(hrp) + data
    const = BECH32M_CONST if spec == Encoding.BECH32M else 1
    polymod = _bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ const
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def bech32_encode(hrp: str, data: list[int], spec: Encoding) -> str:
    """Compute a Bech32 string given HRP and data values."""
    combined = data + _bech32_create_checksum(hrp, data, spec)
    return hrp + "1" + "".join([CHARSET[d] for d in combined])


def bech32_decode(bech: str) -> tuple[str, list[int], Encoding] | tuple[None, None, None]:
    """Validate a Bech32/Bech32m string, and determine HRP and data."""
    if any(ord(x) < 33 or ord(x) > 126 for x in bech):
        return (None, None, None)
    if bech.lower() != bech and bech.upper() != bech:
        return (None, None, None)
    bech = bech.lower()
    pos = bech.rfind("1")
    if pos < 1 or pos + 7 > len(bech) or len(bech) > 90:
        return (None, None, None)
    if not all(x in CHARSET for x in bech[pos + 1 :]):
        return (None, None, None)
    hrp = bech[:pos]
    data = [CHARSET.find(x) for x in bech[pos + 1 :]]
    spec = _bech32_verify_checksum(hrp, data)
    if spec is None:
        return (None, None, None)
    return (hrp, data[:-6], spec)


def _convertbits(data: list[int] | bytes, frombits: int, tobits: int, pad: bool = True) -> list[int] | None:
    """General power-of-2 base conversion."""
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            return None
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return ret


def encode_segwit_address(hrp: str, witver: int, witprog: bytes) -> str | None:
    """Encode a segwit address."""
    spec = Encoding.BECH32 if witver == 0 else Encoding.BECH32M
    ret = _convertbits(list(witprog), 8, 5)
    if ret is None:
        return None
    return bech32_encode(hrp, [witver] + ret, spec)


def decode_segwit_address(hrp: str, addr: str) -> tuple[int, bytes] | tuple[None, None]:
    """Decode a segwit address. Returns (witness_version, witness_program) or (None, None)."""
    hrpgot, data, spec = bech32_decode(addr)
    if hrpgot is None or hrpgot != hrp or data is None:
        return (None, None)
    decoded = _convertbits(data[1:], 5, 8, False)
    if decoded is None or len(decoded) < 2 or len(decoded) > 40:
        return (None, None)
    witver = data[0]
    if witver > 16:
        return (None, None)
    if witver == 0 and len(decoded) != 20 and len(decoded) != 32:
        return (None, None)
    if witver == 0 and spec != Encoding.BECH32:
        return (None, None)
    if witver != 0 and spec != Encoding.BECH32M:
        return (None, None)
    return (witver, bytes(decoded))
