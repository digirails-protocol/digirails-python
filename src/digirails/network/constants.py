"""DigiRails protocol constants from the DR-Pay specification."""

from __future__ import annotations

from enum import IntEnum

# On-chain magic prefix: ASCII "DR"
DR_MAGIC = b"\x44\x52"

# DigiRails header version (lower 7 bits; bit 7 is the test flag)
DR_VERSION = 0x01

# Test flag: bit 7 of the version byte marks test/integration transactions
DR_TEST_FLAG = 0x80

# DR-Pay protocol version string (used in JSON messages)
PROTOCOL_VERSION = "0.3.0"

# DigiByte OP_RETURN size limit
OP_RETURN_MAX_BYTES = 80

# DR header size (magic 2B + version 1B + sub-protocol 1B + type 1B)
DR_HEADER_SIZE = 5

# Maximum payload after header
DR_MAX_PAYLOAD = OP_RETURN_MAX_BYTES - DR_HEADER_SIZE  # 75 bytes

# DigiByte block time in seconds
BLOCK_TIME_SECONDS = 15

# Default escrow timeout in blocks (~2 hours)
DEFAULT_ESCROW_TIMEOUT_BLOCKS = 480

# Satoshis per DGB
SATOSHIS_PER_DGB = 100_000_000


class SubProtocol(IntEnum):
    DR_CORE = 0x00
    DR_PAY = 0x01
    DR_REP = 0x02
    EXPERIMENTAL = 0xFF


class CoreMessageType(IntEnum):
    IDENTITY_DECLARATION = 0x01
    IDENTITY_TRANSFER = 0x02


class PayMessageType(IntEnum):
    SERVICE_DECLARATION = 0x01
    PAYMENT_MEMO = 0x02
    REFUND_MEMO = 0x03


class RepMessageType(IntEnum):
    ATTESTATION = 0x01


# Confirmation tier parameters: (required_confirmations, max_dgb_amount or None for unlimited)
CONFIRMATION_TIERS = {
    "mempool": (0, 1),
    "flash": (1, 100),
    "standard": (4, 10_000),
    "secure": (10, None),
}
