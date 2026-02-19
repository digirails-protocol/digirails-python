"""Tests for Pydantic protocol message models."""

import time

from digirails.models.enums import ConfirmationTier, ErrorCode, ServiceCategory
from digirails.models.manifest import Manifest, Pricing, Service
from digirails.models.messages import (
    AddressField,
    ErrorDetail,
    ErrorResponse,
    InvoicePayment,
    InvoiceTerms,
    PaymentBroadcast,
    PaymentInvoice,
    PaymentRequest,
    RequestPayment,
    ServiceDelivery,
    ServiceParams,
)


class TestPaymentRequest:
    def test_create_and_serialize(self):
        pr = PaymentRequest(
            **{"from": AddressField(address="dgb1qbuyer")},
            to=AddressField(address="dgb1qseller"),
            service=ServiceParams(id="echo", params={"message": "hello"}),
            payment=RequestPayment(
                max_amount="0.01",
                confirmation_tier=ConfirmationTier.MEMPOOL,
            ),
        )
        data = pr.model_dump(by_alias=True)
        assert data["protocol"] == "drpay"
        assert data["version"] == "0.2.0"
        assert data["type"] == "payment_request"
        assert data["from"]["address"] == "dgb1qbuyer"
        assert data["service"]["id"] == "echo"
        assert data["payment"]["confirmation_tier"] == "mempool"
        assert data["id"].startswith("req_")

    def test_roundtrip(self):
        pr = PaymentRequest(
            **{"from": AddressField(address="dgb1qbuyer")},
            to=AddressField(address="dgb1qseller"),
            service=ServiceParams(id="test"),
            payment=RequestPayment(
                max_amount="1.0", confirmation_tier=ConfirmationTier.FLASH
            ),
        )
        data = pr.model_dump(by_alias=True)
        pr2 = PaymentRequest.model_validate(data)
        assert pr2.service.id == "test"
        assert pr2.payment.confirmation_tier == ConfirmationTier.FLASH


class TestPaymentInvoice:
    def test_create(self):
        inv = PaymentInvoice(
            request_id="req_12345678",
            payment=InvoicePayment(
                address="dgb1qinvoice",
                amount="0.005",
                expires_at=int(time.time()) + 300,
            ),
            terms=InvoiceTerms(confirmation_tier=ConfirmationTier.MEMPOOL),
        )
        data = inv.model_dump()
        assert data["type"] == "payment_invoice"
        assert data["request_id"] == "req_12345678"
        assert data["id"].startswith("inv_")


class TestPaymentBroadcast:
    def test_create(self):
        pb = PaymentBroadcast(
            invoice_id="inv_abcdef",
            txid="aa" * 32,
            vout=0,
            raw_tx="0200000001" + "00" * 100,
        )
        data = pb.model_dump()
        assert data["type"] == "payment_broadcast"
        assert data["raw_tx"] is not None


class TestServiceDelivery:
    def test_create(self):
        sd = ServiceDelivery(
            invoice_id="inv_abcdef",
            result={"echo": "hello world"},
        )
        data = sd.model_dump()
        assert data["status"] == "complete"
        assert data["result"]["echo"] == "hello world"


class TestErrorResponse:
    def test_create(self):
        er = ErrorResponse(
            request_id="req_12345678",
            error=ErrorDetail(
                code=ErrorCode.UNKNOWN_SERVICE,
                message="Service 'foo' not found",
            ),
        )
        data = er.model_dump()
        assert data["type"] == "error"
        assert data["error"]["code"] == "UNKNOWN_SERVICE"
        assert data["error"]["retry"] is False


class TestManifest:
    def test_create(self):
        m = Manifest(
            address="dgb1qagent",
            agent="test-agent",
            services=[
                Service(
                    id="echo",
                    description="Echo service",
                    pricing=Pricing(model="per-request", amount="0.001"),
                    endpoint="http://localhost:8080/drpay/request",
                )
            ],
        )
        data = m.model_dump()
        assert data["drpay"] == "0.2.0"
        assert len(data["services"]) == 1
        assert data["services"][0]["id"] == "echo"

    def test_find_service(self):
        m = Manifest(
            address="dgb1qtest",
            services=[
                Service(
                    id="echo",
                    pricing=Pricing(model="per-request", amount="0.001"),
                    endpoint="http://localhost/drpay/request",
                ),
                Service(
                    id="translate",
                    pricing=Pricing(model="per-word", amount="0.0001"),
                    endpoint="http://localhost/drpay/request",
                ),
            ],
        )
        assert m.find_service("echo") is not None
        assert m.find_service("translate") is not None
        assert m.find_service("nonexistent") is None


class TestEnums:
    def test_confirmation_tiers(self):
        assert ConfirmationTier.MEMPOOL.confirmations == 0
        assert ConfirmationTier.FLASH.confirmations == 1
        assert ConfirmationTier.STANDARD.confirmations == 4
        assert ConfirmationTier.SECURE.confirmations == 10

    def test_confirmation_tier_max_dgb(self):
        from decimal import Decimal

        assert ConfirmationTier.MEMPOOL.max_dgb == Decimal("1")
        assert ConfirmationTier.SECURE.max_dgb is None

    def test_service_categories(self):
        assert ServiceCategory.LLM_INFERENCE == 0x0001
        assert ServiceCategory.WEB_SEARCH == 0x000B
        assert ServiceCategory.COMPLIANCE == 0x0012

    def test_error_code_retryable(self):
        assert ErrorCode.RATE_LIMITED.retryable is True
        assert ErrorCode.INVALID_REQUEST.retryable is False
        assert ErrorCode.PAYMENT_MISMATCH.retryable is False
