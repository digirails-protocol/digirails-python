"""Base58Check encoding and decoding for DigiByte legacy addresses and WIF keys."""

from __future__ import annotations

import hashlib

ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
ALPHABET_MAP = {c: i for i, c in enumerate(ALPHABET)}


def _double_sha256(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def b58encode(payload: bytes) -> str:
    """Encode bytes to Base58 (no checksum)."""
    n = int.from_bytes(payload, "big")
    result = bytearray()
    while n > 0:
        n, r = divmod(n, 58)
        result.append(ALPHABET[r])
    # Preserve leading zero bytes
    for b in payload:
        if b == 0:
            result.append(ALPHABET[0])
        else:
            break
    return bytes(reversed(result)).decode("ascii")


def b58decode(s: str) -> bytes:
    """Decode Base58 string to bytes (no checksum)."""
    n = 0
    for c in s.encode("ascii"):
        if c not in ALPHABET_MAP:
            raise ValueError(f"Invalid Base58 character: {chr(c)}")
        n = n * 58 + ALPHABET_MAP[c]
    # Determine byte length
    byte_length = (n.bit_length() + 7) // 8
    result = n.to_bytes(byte_length, "big") if byte_length > 0 else b""
    # Preserve leading '1's as zero bytes
    pad = 0
    for c in s.encode("ascii"):
        if c == ALPHABET[0]:
            pad += 1
        else:
            break
    return b"\x00" * pad + result


def b58encode_check(payload: bytes) -> str:
    """Encode bytes to Base58Check (with 4-byte checksum)."""
    checksum = _double_sha256(payload)[:4]
    return b58encode(payload + checksum)


def b58decode_check(s: str) -> bytes:
    """Decode Base58Check string, verify checksum, return payload."""
    data = b58decode(s)
    if len(data) < 4:
        raise ValueError("Base58Check data too short")
    payload, checksum = data[:-4], data[-4:]
    expected = _double_sha256(payload)[:4]
    if checksum != expected:
        raise ValueError("Base58Check checksum mismatch")
    return payload
