"""Seller-side payment flow: handle request, create invoice, verify payment, deliver."""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Callable

from digirails.exceptions import VerificationError
from digirails.models.enums import ConfirmationTier, ErrorCode
from digirails.models.messages import (
    ErrorDetail,
    ErrorResponse,
    InvoicePayment,
    InvoiceTerms,
    PaymentBroadcast,
    PaymentInvoice,
    PaymentRequest,
    ServiceDelivery,
)
from digirails.models.manifest import Service
from digirails.network.constants import SATOSHIS_PER_DGB
from digirails.payment.verification import verify_raw_tx_simple
from digirails.wallet.wallet import Wallet


class PendingInvoice:
    """Tracks a pending invoice awaiting payment."""

    def __init__(self, invoice: PaymentInvoice, service: Service, request: PaymentRequest):
        self.invoice = invoice
        self.service = service
        self.request = request
        self.paid = False


class SellerFlow:
    """Manages the seller side of the payment flow."""

    def __init__(self, wallet: Wallet, services: dict[str, Service], handlers: dict[str, Callable[..., Any]]):
        self._wallet = wallet
        self._services = services
        self._handlers = handlers
        self._pending: dict[str, PendingInvoice] = {}

    def handle_request(self, request: PaymentRequest) -> PaymentInvoice | ErrorResponse:
        """Process a PAYMENT_REQUEST, return a PAYMENT_INVOICE or error."""
        service = self._services.get(request.service.id)
        if service is None:
            return ErrorResponse(
                request_id=request.id,
                error=ErrorDetail(
                    code=ErrorCode.UNKNOWN_SERVICE,
                    message=f"Service '{request.service.id}' not found",
                ),
            )

        # Create invoice
        payment_address = self._wallet.fresh_address()
        amount = service.pricing.amount
        tier = ConfirmationTier(request.payment.confirmation_tier)

        invoice = PaymentInvoice(
            request_id=request.id,
            payment=InvoicePayment(
                address=payment_address,
                amount=amount,
                currency=service.pricing.currency,
                expires_at=int(time.time()) + service.payment.max_invoice_age_seconds,
                memo=f"{request.service.id}",
            ),
            terms=InvoiceTerms(
                confirmation_tier=tier,
            ),
        )

        # Track pending invoice
        self._pending[invoice.id] = PendingInvoice(
            invoice=invoice, service=service, request=request
        )

        return invoice

    async def handle_broadcast(self, broadcast: PaymentBroadcast) -> ServiceDelivery | ErrorResponse:
        """Process a PAYMENT_BROADCAST, verify payment, execute handler, return SERVICE_DELIVERY."""
        pending = self._pending.get(broadcast.invoice_id)
        if pending is None:
            return ErrorResponse(
                error=ErrorDetail(
                    code=ErrorCode.PAYMENT_NOT_FOUND,
                    message=f"Invoice '{broadcast.invoice_id}' not found",
                ),
            )

        invoice = pending.invoice

        # Check expiry
        if invoice.payment.expires_at < int(time.time()):
            del self._pending[broadcast.invoice_id]
            return ErrorResponse(
                error=ErrorDetail(
                    code=ErrorCode.INVOICE_EXPIRED,
                    message="Invoice has expired",
                    retry=True,
                ),
            )

        expected_sat = int(Decimal(invoice.payment.amount) * SATOSHIS_PER_DGB)

        # For mempool tier with raw_tx: verify locally
        if broadcast.raw_tx and invoice.terms.confirmation_tier == ConfirmationTier.MEMPOOL:
            try:
                verify_raw_tx_simple(
                    broadcast.raw_tx,
                    invoice.payment.address,
                    expected_sat,
                    self._wallet._network,
                )
            except VerificationError as e:
                return ErrorResponse(
                    error=ErrorDetail(
                        code=ErrorCode.PAYMENT_MISMATCH,
                        message=str(e),
                    ),
                )
        elif self._wallet._rpc:
            # For other tiers: check via RPC that the transaction exists
            try:
                tx_data = await self._wallet._rpc.getrawtransaction(broadcast.txid, True)
                # Verify output matches
                found = False
                for vout in tx_data.get("vout", []):
                    spk_hex = vout.get("scriptPubKey", {}).get("hex", "")
                    value_sat = int(Decimal(str(vout.get("value", 0))) * SATOSHIS_PER_DGB)
                    from digirails.crypto.script import address_to_script_pubkey

                    expected_spk = address_to_script_pubkey(
                        invoice.payment.address, self._wallet._network
                    ).hex()
                    if spk_hex == expected_spk and value_sat >= expected_sat:
                        found = True
                        break
                if not found:
                    return ErrorResponse(
                        error=ErrorDetail(
                            code=ErrorCode.PAYMENT_MISMATCH,
                            message="Transaction does not pay the invoice address/amount",
                        ),
                    )
            except Exception as e:
                return ErrorResponse(
                    error=ErrorDetail(
                        code=ErrorCode.PAYMENT_NOT_FOUND,
                        message=f"Could not verify transaction: {e}",
                        retry=True,
                    ),
                )

        # Payment verified — execute the service handler
        pending.paid = True
        handler = self._handlers.get(pending.service.id)
        if handler is None:
            return ErrorResponse(
                error=ErrorDetail(
                    code=ErrorCode.SERVICE_UNAVAILABLE,
                    message="Service handler not registered",
                ),
            )

        try:
            result = handler(pending.request.service.params or {})
        except Exception as e:
            return ErrorResponse(
                error=ErrorDetail(
                    code=ErrorCode.SERVICE_UNAVAILABLE,
                    message=f"Service execution failed: {e}",
                ),
            )

        # Clean up
        del self._pending[broadcast.invoice_id]

        return ServiceDelivery(
            invoice_id=invoice.id,
            status="complete",
            result=result if isinstance(result, dict) else {"result": result},
        )
