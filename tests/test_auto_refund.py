"""Tests for auto-refund on service delivery failure (Feb 27, 2026)."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from digirails.models.enums import ConfirmationTier, ErrorCode
from digirails.models.manifest import Pricing, Service
from digirails.models.messages import (
    AddressField,
    ErrorResponse,
    PaymentBroadcast,
    PaymentRequest,
    RequestPayment,
    ServiceDelivery,
    ServiceParams,
)
from digirails.network.constants import SATOSHIS_PER_DGB
from digirails.network.params import MAINNET
from digirails.payment.seller import DUST_THRESHOLD_SAT, REFUND_FEE_SAT, SellerFlow
from digirails.wallet.wallet import Wallet

# Deterministic test keys (valid secp256k1 scalars, no real funds)
SELLER_KEY = bytes.fromhex(
    "0000000000000000000000000000000000000000000000000000000000000001"
)
BUYER_KEY = bytes.fromhex(
    "0000000000000000000000000000000000000000000000000000000000000002"
)

FAKE_REFUND_TXID = "aaaa1111bbbb2222cccc3333dddd4444eeee5555ffff6666aaaa7777bbbb8888"

SERVICE_PRICE_DGB = "1.00"
SERVICE_PRICE_SAT = int(Decimal(SERVICE_PRICE_DGB) * SATOSHIS_PER_DGB)

TEST_SERVICE = Service(
    id="test-echo",
    description="Echo service (test)",
    pricing=Pricing(model="per-request", amount=SERVICE_PRICE_DGB, currency="DGB"),
    endpoint="http://localhost:9999/test",
)

# Fake raw_tx bytes — verification is mocked so contents don't matter
FAKE_RAW_TX = "0200000001" + "00" * 100


def _mock_rpc():
    """Mock RPC that returns a 5 DGB UTXO and accepts broadcast."""
    rpc = AsyncMock()
    rpc.listunspent = AsyncMock(
        return_value=[
            {"txid": "ff" * 32, "vout": 0, "amount": "5.0", "confirmations": 6}
        ]
    )
    rpc.sendrawtransaction = AsyncMock(return_value=FAKE_REFUND_TXID)
    return rpc


def _request(buyer_addr: str, seller_addr: str) -> PaymentRequest:
    return PaymentRequest(
        **{
            "from": AddressField(address=buyer_addr),
            "to": AddressField(address=seller_addr),
            "service": ServiceParams(id="test-echo", params={"text": "hello"}),
            "payment": RequestPayment(
                currency="DGB",
                max_amount="2.0",
                confirmation_tier=ConfirmationTier.MEMPOOL,
            ),
        }
    )


async def _run_flow(seller: SellerFlow, buyer_addr: str, seller_addr: str):
    """Drive a full REQUEST → INVOICE → BROADCAST → result flow."""
    request = _request(buyer_addr, seller_addr)

    invoice = seller.handle_request(request)
    assert not isinstance(invoice, ErrorResponse), f"Expected invoice, got: {invoice}"

    broadcast = PaymentBroadcast(
        invoice_id=invoice.id, txid="bb" * 32, vout=0, raw_tx=FAKE_RAW_TX
    )
    return await seller.handle_broadcast(broadcast)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAutoRefund:
    """Auto-refund on service handler failure."""

    @pytest.mark.asyncio
    @patch("digirails.payment.seller.verify_raw_tx_simple", return_value=0)
    async def test_handler_failure_triggers_refund(self, _mock_verify):
        """Handler throws → ErrorResponse with RefundInfo attached."""
        rpc = _mock_rpc()
        wallet = Wallet(private_key=SELLER_KEY, network=MAINNET, rpc=rpc)

        def failing_handler(params):
            raise RuntimeError("Simulated service failure")

        seller = SellerFlow(
            wallet=wallet,
            services={"test-echo": TEST_SERVICE},
            handlers={"test-echo": failing_handler},
            auto_refund=True,
        )

        result = await _run_flow(seller, Wallet(BUYER_KEY).address, wallet.address)

        assert isinstance(result, ErrorResponse)
        assert result.error.code == ErrorCode.SERVICE_UNAVAILABLE
        assert "Simulated service failure" in result.error.message

        # Refund should be present
        assert result.error.refund is not None
        assert result.error.refund.txid == FAKE_REFUND_TXID

        # Full refund — seller absorbs the miner fee
        expected = str(Decimal(SERVICE_PRICE_SAT) / SATOSHIS_PER_DGB)
        assert result.error.refund.amount == expected

        # Broadcast was called exactly once (the refund TX)
        rpc.sendrawtransaction.assert_called_once()

    @pytest.mark.asyncio
    @patch("digirails.payment.seller.verify_raw_tx_simple", return_value=0)
    async def test_refund_amount_math(self, _mock_verify):
        """Refund = payment − 50,000 sat fee. Verify with 2.50 DGB price."""
        rpc = _mock_rpc()
        wallet = Wallet(private_key=SELLER_KEY, network=MAINNET, rpc=rpc)

        svc = Service(
            id="test-echo",
            pricing=Pricing(model="per-request", amount="2.50", currency="DGB"),
            endpoint="http://localhost:9999/test",
        )

        def boom(params):
            raise ValueError("boom")

        seller = SellerFlow(
            wallet=wallet,
            services={"test-echo": svc},
            handlers={"test-echo": boom},
        )

        result = await _run_flow(seller, Wallet(BUYER_KEY).address, wallet.address)

        assert isinstance(result, ErrorResponse)
        assert result.error.refund is not None
        # Full refund: 2.50 DGB — seller absorbs the miner fee
        assert result.error.refund.amount == "2.5"

    @pytest.mark.asyncio
    @patch("digirails.payment.seller.verify_raw_tx_simple", return_value=0)
    async def test_auto_refund_disabled(self, _mock_verify):
        """auto_refund=False → no refund attempted, no RPC call."""
        rpc = _mock_rpc()
        wallet = Wallet(private_key=SELLER_KEY, network=MAINNET, rpc=rpc)

        def fail(params):
            raise RuntimeError("fail")

        seller = SellerFlow(
            wallet=wallet,
            services={"test-echo": TEST_SERVICE},
            handlers={"test-echo": fail},
            auto_refund=False,
        )

        result = await _run_flow(seller, Wallet(BUYER_KEY).address, wallet.address)

        assert isinstance(result, ErrorResponse)
        assert result.error.refund is None
        rpc.sendrawtransaction.assert_not_called()

    @pytest.mark.asyncio
    @patch("digirails.payment.seller.verify_raw_tx_simple", return_value=0)
    async def test_no_rpc_skips_refund(self, _mock_verify):
        """Wallet without RPC → refund silently skipped."""
        wallet = Wallet(private_key=SELLER_KEY, network=MAINNET, rpc=None)

        def fail(params):
            raise RuntimeError("fail")

        seller = SellerFlow(
            wallet=wallet,
            services={"test-echo": TEST_SERVICE},
            handlers={"test-echo": fail},
            auto_refund=True,
        )

        result = await _run_flow(seller, Wallet(BUYER_KEY).address, wallet.address)

        assert isinstance(result, ErrorResponse)
        assert result.error.refund is None

    @pytest.mark.asyncio
    @patch("digirails.payment.seller.verify_raw_tx_simple", return_value=0)
    async def test_payment_too_small_to_refund(self, _mock_verify):
        """Payment ≤ dust threshold → refund skipped."""
        rpc = _mock_rpc()
        wallet = Wallet(private_key=SELLER_KEY, network=MAINNET, rpc=rpc)

        # 0.00000546 DGB = 546 sat (dust threshold) → refund skipped
        tiny_svc = Service(
            id="test-echo",
            pricing=Pricing(model="per-request", amount="0.00000546", currency="DGB"),
            endpoint="http://localhost:9999/test",
        )

        def fail(params):
            raise RuntimeError("fail")

        seller = SellerFlow(
            wallet=wallet,
            services={"test-echo": tiny_svc},
            handlers={"test-echo": fail},
        )

        result = await _run_flow(seller, Wallet(BUYER_KEY).address, wallet.address)

        assert isinstance(result, ErrorResponse)
        assert result.error.refund is None
        rpc.sendrawtransaction.assert_not_called()

    @pytest.mark.asyncio
    @patch("digirails.payment.seller.verify_raw_tx_simple", return_value=0)
    async def test_successful_handler_no_refund(self, _mock_verify):
        """Happy path: handler succeeds → ServiceDelivery, no refund."""
        rpc = _mock_rpc()
        wallet = Wallet(private_key=SELLER_KEY, network=MAINNET, rpc=rpc)

        def echo(params):
            return {"echo": params.get("text", "")}

        seller = SellerFlow(
            wallet=wallet,
            services={"test-echo": TEST_SERVICE},
            handlers={"test-echo": echo},
        )

        result = await _run_flow(seller, Wallet(BUYER_KEY).address, wallet.address)

        assert isinstance(result, ServiceDelivery)
        assert result.status == "complete"
        assert result.result == {"echo": "hello"}
        rpc.sendrawtransaction.assert_not_called()

    @pytest.mark.asyncio
    @patch("digirails.payment.seller.verify_raw_tx_simple", return_value=0)
    async def test_pending_cleaned_up_on_failure(self, _mock_verify):
        """Pending invoice dict must be empty after failure (memory leak fix)."""
        rpc = _mock_rpc()
        wallet = Wallet(private_key=SELLER_KEY, network=MAINNET, rpc=rpc)

        def fail(params):
            raise RuntimeError("fail")

        seller = SellerFlow(
            wallet=wallet,
            services={"test-echo": TEST_SERVICE},
            handlers={"test-echo": fail},
        )

        # After handle_request, pending should have one entry
        request = _request(Wallet(BUYER_KEY).address, wallet.address)
        invoice = seller.handle_request(request)
        assert len(seller._pending) == 1

        broadcast = PaymentBroadcast(
            invoice_id=invoice.id, txid="cc" * 32, vout=0, raw_tx=FAKE_RAW_TX
        )
        await seller.handle_broadcast(broadcast)

        # After failure + refund, pending must be empty
        assert len(seller._pending) == 0
