"""Buyer-side payment flow: request service, pay invoice, receive delivery."""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

import aiohttp

from digirails._opreturn import encode_payment_memo
from digirails.exceptions import InvoiceExpiredError, PaymentError
from digirails.models.enums import ConfirmationTier
from digirails.models.messages import (
    AddressField,
    PaymentBroadcast,
    PaymentInvoice,
    PaymentRequest,
    RequestPayment,
    ServiceDelivery,
    ServiceParams,
)
from digirails.network.constants import SATOSHIS_PER_DGB
from digirails.wallet.wallet import Wallet


async def request_service(
    wallet: Wallet,
    seller_url: str,
    service_id: str,
    params: dict[str, Any] | None = None,
    max_amount: str = "0.01",
    confirmation_tier: ConfirmationTier = ConfirmationTier.MEMPOOL,
    seller_address: str = "",
) -> tuple[PaymentInvoice, str]:
    """Send a PAYMENT_REQUEST, receive a PAYMENT_INVOICE.

    Returns (invoice, request_endpoint_url).
    """
    request = PaymentRequest(
        **{"from": AddressField(address=wallet.address)},
        to=AddressField(address=seller_address),
        service=ServiceParams(id=service_id, params=params),
        payment=RequestPayment(
            max_amount=max_amount,
            confirmation_tier=confirmation_tier,
        ),
    )

    url = f"{seller_url.rstrip('/')}/drpay/request"
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            json=request.model_dump(by_alias=True),
            headers={"Content-Type": "application/vnd.digirails.pay+json"},
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise PaymentError(f"Seller returned HTTP {resp.status}: {body}")
            data = await resp.json()

    invoice = PaymentInvoice.model_validate(data)

    # Validate invoice
    if invoice.payment.expires_at < int(time.time()):
        raise InvoiceExpiredError("Invoice already expired")

    max_sat = int(Decimal(max_amount) * SATOSHIS_PER_DGB)
    invoice_sat = int(Decimal(invoice.payment.amount) * SATOSHIS_PER_DGB)
    if invoice_sat > max_sat:
        raise PaymentError(
            f"Invoice amount {invoice.payment.amount} DGB exceeds max {max_amount} DGB"
        )

    return invoice, url


async def pay_invoice(
    wallet: Wallet,
    invoice: PaymentInvoice,
    seller_url: str,
) -> ServiceDelivery:
    """Build TX, broadcast, send PAYMENT_BROADCAST, receive SERVICE_DELIVERY."""
    amount_sat = int(Decimal(invoice.payment.amount) * SATOSHIS_PER_DGB)

    # Build OP_RETURN payment memo
    invoice_id_bytes = bytes.fromhex(invoice.id.replace("inv_", "").ljust(32, "0")[:32])
    op_return_data = encode_payment_memo(invoice_id_bytes[:16])

    # Build and sign the transaction
    tx = await wallet.build_payment(
        to_address=invoice.payment.address,
        amount_sat=amount_sat,
        op_return_data=op_return_data,
    )

    # Broadcast
    txid = await wallet.broadcast(tx)

    # Find the payment output vout
    from digirails.crypto.script import address_to_script_pubkey

    payment_spk = address_to_script_pubkey(invoice.payment.address, wallet._network)
    vout = 0
    for i, out in enumerate(tx.outputs):
        if out.script_pubkey == payment_spk:
            vout = i
            break

    # Send PAYMENT_BROADCAST to seller
    broadcast = PaymentBroadcast(
        invoice_id=invoice.id,
        txid=txid,
        vout=vout,
        raw_tx=tx.hex() if invoice.terms.confirmation_tier == ConfirmationTier.MEMPOOL else None,
    )

    url = f"{seller_url.rstrip('/')}/drpay/broadcast"
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            json=broadcast.model_dump(),
            headers={"Content-Type": "application/vnd.digirails.pay+json"},
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise PaymentError(f"Seller returned HTTP {resp.status}: {body}")
            data = await resp.json()

    return ServiceDelivery.model_validate(data)
