"""PaymentFlow orchestrator — combines buyer and seller logic."""

from __future__ import annotations

from typing import Any

from digirails.models.enums import ConfirmationTier
from digirails.models.messages import ServiceDelivery
from digirails.payment.buyer import pay_invoice, request_service
from digirails.wallet.wallet import Wallet


class PaymentFlow:
    """Orchestrates the 4-message payment flow.

    Used internally by Agent, but also available for fine-grained control.
    """

    def __init__(self, wallet: Wallet):
        self._wallet = wallet

    async def buy(
        self,
        seller_url: str,
        service_id: str,
        params: dict[str, Any] | None = None,
        max_amount: str = "0.01",
        confirmation_tier: ConfirmationTier = ConfirmationTier.MEMPOOL,
        seller_address: str = "",
        test: bool = False,
    ) -> ServiceDelivery:
        """Complete the full buyer-side flow in one call."""
        invoice, _ = await request_service(
            wallet=self._wallet,
            seller_url=seller_url,
            service_id=service_id,
            params=params,
            max_amount=max_amount,
            confirmation_tier=confirmation_tier,
            seller_address=seller_address,
        )

        delivery = await pay_invoice(
            wallet=self._wallet,
            invoice=invoice,
            seller_url=seller_url,
            test=test,
        )

        return delivery
