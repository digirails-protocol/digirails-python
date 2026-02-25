"""DigiRails OP_RETURN header encoding and decoding.

Implements the 5-byte DR header format from the DR-Pay specification:
  Offset 0: 0x4452 (2 bytes) — "DR" magic
  Offset 2: version byte (1 byte) — lower 7 bits = version, bit 7 = test flag
  Offset 3: sub-protocol (1 byte) — 0x00 DR-Core, 0x01 DR-Pay, 0x02 DR-Rep
  Offset 4: message type (1 byte)
"""

from __future__ import annotations

import hashlib
import struct

from digirails.network.constants import (
    DR_HEADER_SIZE,
    DR_MAGIC,
    DR_MAX_PAYLOAD,
    DR_TEST_FLAG,
    DR_VERSION,
    CoreMessageType,
    PayMessageType,
    RepMessageType,
    SubProtocol,
)


def encode_header(
    sub_protocol: SubProtocol, message_type: int, *, test: bool = False
) -> bytes:
    """Encode 5-byte DigiRails OP_RETURN header.

    Args:
        sub_protocol: Sub-protocol identifier.
        message_type: Message type code within the sub-protocol.
        test: If True, set the test flag (bit 7) in the version byte.
    """
    version_byte = DR_VERSION | DR_TEST_FLAG if test else DR_VERSION
    return DR_MAGIC + bytes([version_byte, sub_protocol, message_type])


def decode_header(data: bytes) -> tuple[int, SubProtocol, int, bytes, bool] | None:
    """Decode a DigiRails OP_RETURN payload.

    Returns:
        (version, sub_protocol, message_type, payload, is_test) or None
        if not a valid DR header.
    """
    if len(data) < DR_HEADER_SIZE:
        return None
    if data[:2] != DR_MAGIC:
        return None
    raw_version = data[2]
    is_test = bool(raw_version & DR_TEST_FLAG)
    version = raw_version & 0x7F
    try:
        sub_protocol = SubProtocol(data[3])
    except ValueError:
        return None
    message_type = data[4]
    payload = data[DR_HEADER_SIZE:]
    return (version, sub_protocol, message_type, payload, is_test)


# --- DR-Core (0x00) messages ---


def encode_identity_declaration(label: str = "", *, test: bool = False) -> bytes:
    """Build OP_RETURN payload for identity declaration.

    Format: DR_HEADER(Core, 0x01) + label (UTF-8, 0-75 bytes)
    """
    label_bytes = label.encode("utf-8")
    if len(label_bytes) > DR_MAX_PAYLOAD:
        raise ValueError(
            f"Label too long: {len(label_bytes)} bytes (max {DR_MAX_PAYLOAD})"
        )
    return encode_header(SubProtocol.DR_CORE, CoreMessageType.IDENTITY_DECLARATION, test=test) + label_bytes


def encode_identity_transfer(new_address_hash: bytes, *, test: bool = False) -> bytes:
    """Build OP_RETURN payload for identity transfer.

    Format: DR_HEADER(Core, 0x02) + new_address (20 or 32 bytes)
    """
    if len(new_address_hash) not in (20, 32):
        raise ValueError(f"Address hash must be 20 or 32 bytes, got {len(new_address_hash)}")
    return encode_header(SubProtocol.DR_CORE, CoreMessageType.IDENTITY_TRANSFER, test=test) + new_address_hash


# --- DR-Pay (0x01) messages ---


def encode_service_declaration(
    category: int,
    flags: int,
    manifest_hash: bytes,
    *,
    manifest_domain: str = "",
    test: bool = False,
) -> bytes:
    """Build OP_RETURN payload for service declaration.

    Format: DR_HEADER(Pay, 0x01) + category (2B) + flags (2B) + manifest_hash (32B) + [domain]
    Total: 41 bytes without domain, up to 80 bytes with domain.
    """
    if len(manifest_hash) != 32:
        raise ValueError(f"Manifest hash must be 32 bytes, got {len(manifest_hash)}")
    domain_bytes = manifest_domain.encode("utf-8") if manifest_domain else b""
    if len(domain_bytes) > DR_MAX_PAYLOAD - 36:  # 75 - 36 = 39 bytes
        raise ValueError(
            f"Domain too long: {len(domain_bytes)} bytes (max {DR_MAX_PAYLOAD - 36})"
        )
    header = encode_header(SubProtocol.DR_PAY, PayMessageType.SERVICE_DECLARATION, test=test)
    return header + struct.pack(">H", category) + struct.pack(">H", flags) + manifest_hash + domain_bytes


def encode_payment_memo(
    invoice_id: bytes, service_ref: bytes = b"", *, test: bool = False
) -> bytes:
    """Build OP_RETURN payload for payment memo.

    Format: DR_HEADER(Pay, 0x02) + invoice_id (16B) + service_ref (0-59B)
    Total: 21-80 bytes
    """
    if len(invoice_id) != 16:
        raise ValueError(f"Invoice ID must be 16 bytes, got {len(invoice_id)}")
    max_ref = DR_MAX_PAYLOAD - 16  # 75 - 16 = 59 bytes
    if len(service_ref) > max_ref:
        raise ValueError(f"Service ref too long: {len(service_ref)} bytes (max {max_ref})")
    header = encode_header(SubProtocol.DR_PAY, PayMessageType.PAYMENT_MEMO, test=test)
    return header + invoice_id + service_ref


# --- DR-Rep (0x02) messages ---


def encode_attestation(
    target_address_hash: bytes, score: int, nonce: int, *, test: bool = False
) -> bytes:
    """Build OP_RETURN payload for reputation attestation.

    Format: DR_HEADER(Rep, 0x01) + target_address (20B) + score (1B) + nonce (4B)
    Total: 30 bytes
    """
    if len(target_address_hash) != 20:
        raise ValueError(f"Target address hash must be 20 bytes, got {len(target_address_hash)}")
    if not 0 <= score <= 255:
        raise ValueError(f"Score must be 0-255, got {score}")
    header = encode_header(SubProtocol.DR_REP, RepMessageType.ATTESTATION, test=test)
    return header + target_address_hash + bytes([score]) + struct.pack(">I", nonce)


def manifest_hash(manifest_json: str) -> bytes:
    """Compute SHA-256 hash of a capabilities manifest JSON string."""
    return hashlib.sha256(manifest_json.encode("utf-8")).digest()
