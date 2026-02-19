"""Protocol enumerations from the DR-Pay specification."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum, IntEnum


class ConfirmationTier(str, Enum):
    MEMPOOL = "mempool"
    FLASH = "flash"
    STANDARD = "standard"
    SECURE = "secure"

    @property
    def confirmations(self) -> int:
        return {
            ConfirmationTier.MEMPOOL: 0,
            ConfirmationTier.FLASH: 1,
            ConfirmationTier.STANDARD: 4,
            ConfirmationTier.SECURE: 10,
        }[self]

    @property
    def max_dgb(self) -> Decimal | None:
        """Maximum DGB amount for this tier, or None for unlimited."""
        return {
            ConfirmationTier.MEMPOOL: Decimal("1"),
            ConfirmationTier.FLASH: Decimal("100"),
            ConfirmationTier.STANDARD: Decimal("10000"),
            ConfirmationTier.SECURE: None,
        }[self]


class ServiceCategory(IntEnum):
    LLM_INFERENCE = 0x0001
    IMAGE_GENERATION = 0x0002
    CODE_EXECUTION = 0x0003
    DATA_RETRIEVAL = 0x0004
    EMBEDDING_VECTOR_SEARCH = 0x0005
    MEDIA_PROCESSING = 0x0006
    TRANSLATION = 0x0007
    GENERAL_COMPUTE = 0x0008
    STORAGE = 0x0009
    RELAY_PROXY = 0x000A
    WEB_SEARCH = 0x000B
    WEB_SCRAPING = 0x000C
    DOCUMENT_PARSING = 0x000D
    DATA_ENRICHMENT = 0x000E
    FACT_VERIFICATION = 0x000F
    AGENT_TASK_DELEGATION = 0x0010
    KNOWLEDGE_GRAPH = 0x0011
    COMPLIANCE = 0x0012


class ErrorCode(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    UNKNOWN_SERVICE = "UNKNOWN_SERVICE"
    INSUFFICIENT_PAYMENT = "INSUFFICIENT_PAYMENT"
    INVOICE_EXPIRED = "INVOICE_EXPIRED"
    PAYMENT_NOT_FOUND = "PAYMENT_NOT_FOUND"
    PAYMENT_MISMATCH = "PAYMENT_MISMATCH"
    TIER_REJECTED = "TIER_REJECTED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    CURRENCY_NOT_ACCEPTED = "CURRENCY_NOT_ACCEPTED"

    @property
    def retryable(self) -> bool:
        return self in {
            ErrorCode.INSUFFICIENT_PAYMENT,
            ErrorCode.INVOICE_EXPIRED,
            ErrorCode.PAYMENT_NOT_FOUND,
            ErrorCode.TIER_REJECTED,
            ErrorCode.SERVICE_UNAVAILABLE,
            ErrorCode.RATE_LIMITED,
            ErrorCode.CURRENCY_NOT_ACCEPTED,
        }
