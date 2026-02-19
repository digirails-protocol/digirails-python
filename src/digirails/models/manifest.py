"""Pydantic models for the DR-Pay capabilities manifest."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from digirails.network.constants import PROTOCOL_VERSION


class PricingReference(BaseModel):
    target_currency: str = "USD"
    target_amount: str
    update_frequency_seconds: int = 900


class Pricing(BaseModel):
    model: str  # e.g., "per-request", "per-token", "per-second"
    amount: str  # DGB amount as string
    currency: str = "DGB"
    pricing_reference: PricingReference | None = None


class PaymentTerms(BaseModel):
    confirmations_required: int = 0
    max_invoice_age_seconds: int = 300
    streaming_supported: bool = False


class Service(BaseModel):
    id: str
    description: str = ""
    pricing: Pricing
    endpoint: str
    payment: PaymentTerms = PaymentTerms()
    params_schema: dict[str, Any] | None = None  # Optional JSON schema for params


class Discovery(BaseModel):
    manifest_url: str


class Manifest(BaseModel):
    """DR-Pay capabilities manifest served at /.well-known/digirails.json."""

    drpay: str = PROTOCOL_VERSION
    agent: str = ""  # Agent label or domain
    address: str  # Agent's DigiByte address
    services: list[Service] = []
    discovery: Discovery | None = None

    def find_service(self, service_id: str) -> Service | None:
        """Look up a service by ID."""
        for s in self.services:
            if s.id == service_id:
                return s
        return None
