"""Pydantic models for all DR-Pay protocol messages."""

from __future__ import annotations

import secrets
import time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from digirails.models.enums import ConfirmationTier, ErrorCode
from digirails.network.constants import PROTOCOL_VERSION


class AddressField(BaseModel):
    address: str


class ServiceParams(BaseModel):
    id: str
    params: dict[str, Any] | None = None


class RequestPayment(BaseModel):
    currency: Literal["DGB", "DD"] = "DGB"
    max_amount: str
    confirmation_tier: ConfirmationTier


class PaymentRequest(BaseModel):
    """Message 1: Buyer → Seller."""

    model_config = ConfigDict(populate_by_name=True)

    protocol: Literal["drpay"] = "drpay"
    version: str = PROTOCOL_VERSION
    type: Literal["payment_request"] = "payment_request"
    id: str = Field(default_factory=lambda: f"req_{secrets.token_hex(4)}")
    timestamp: int = Field(default_factory=lambda: int(time.time()))
    from_: AddressField = Field(alias="from")
    to: AddressField
    service: ServiceParams
    payment: RequestPayment


class InvoicePayment(BaseModel):
    address: str
    amount: str
    currency: Literal["DGB", "DD"] = "DGB"
    expires_at: int
    memo: str | None = None


class InvoiceTerms(BaseModel):
    confirmation_tier: ConfirmationTier
    delivery: str = "immediate"
    refund_policy: str | None = None


class PaymentInvoice(BaseModel):
    """Message 2: Seller → Buyer."""

    protocol: Literal["drpay"] = "drpay"
    version: str = PROTOCOL_VERSION
    type: Literal["payment_invoice"] = "payment_invoice"
    id: str = Field(default_factory=lambda: f"inv_{secrets.token_hex(4)}")
    request_id: str
    timestamp: int = Field(default_factory=lambda: int(time.time()))
    payment: InvoicePayment
    terms: InvoiceTerms


class PaymentBroadcast(BaseModel):
    """Message 3: Buyer → Seller."""

    protocol: Literal["drpay"] = "drpay"
    version: str = PROTOCOL_VERSION
    type: Literal["payment_broadcast"] = "payment_broadcast"
    invoice_id: str
    txid: str
    vout: int
    raw_tx: str | None = None


class ServiceDelivery(BaseModel):
    """Message 4: Seller → Buyer."""

    protocol: Literal["drpay"] = "drpay"
    version: str = PROTOCOL_VERSION
    type: Literal["service_delivery"] = "service_delivery"
    invoice_id: str
    status: Literal["complete", "partial", "error"] = "complete"
    result: dict[str, Any] | None = None


class ErrorDetail(BaseModel):
    code: ErrorCode
    message: str
    retry: bool = False


class ErrorResponse(BaseModel):
    """Error response (either direction)."""

    protocol: Literal["drpay"] = "drpay"
    version: str = PROTOCOL_VERSION
    type: Literal["error"] = "error"
    request_id: str | None = None
    error: ErrorDetail
