"""Seller HTTP server for handling incoming DR-Pay payment flows."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from aiohttp import web

from digirails.models.manifest import Discovery, Manifest, PaymentTerms, Pricing, Service
from digirails.models.messages import ErrorResponse, PaymentBroadcast, PaymentRequest
from digirails.payment.seller import SellerFlow

if TYPE_CHECKING:
    from digirails.wallet.wallet import Wallet


class DigiRailsServer:
    """aiohttp-based HTTP server that handles incoming DR-Pay payment flows."""

    def __init__(
        self,
        wallet: "Wallet",
        host: str = "0.0.0.0",
        port: int = 8080,
    ):
        self._wallet = wallet
        self._host = host
        self._port = port
        self._services: dict[str, Service] = {}
        self._handlers: dict[str, Callable[..., Any]] = {}
        self._seller_flow: SellerFlow | None = None
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None

    def register_service(
        self,
        service_id: str,
        handler: Callable[..., Any],
        price: str,
        description: str = "",
        category: int = 0x0008,
        currency: str = "DGB",
        confirmations_required: int = 0,
        max_invoice_age_seconds: int = 300,
    ) -> None:
        """Register a service that this seller offers."""
        service = Service(
            id=service_id,
            description=description,
            pricing=Pricing(model="per-request", amount=price, currency=currency),
            endpoint=f"http://{self._host}:{self._port}/drpay/request",
            payment=PaymentTerms(
                confirmations_required=confirmations_required,
                max_invoice_age_seconds=max_invoice_age_seconds,
            ),
        )
        self._services[service_id] = service
        self._handlers[service_id] = handler

    def _build_manifest(self) -> Manifest:
        return Manifest(
            address=self._wallet.address,
            services=list(self._services.values()),
            discovery=Discovery(
                manifest_url=f"http://{self._host}:{self._port}/.well-known/digirails.json"
            ),
        )

    async def _handle_manifest(self, request: web.Request) -> web.Response:
        """GET /.well-known/digirails.json"""
        manifest = self._build_manifest()
        return web.json_response(
            manifest.model_dump(),
            content_type="application/vnd.digirails.pay+json",
        )

    async def _handle_payment_request(self, request: web.Request) -> web.Response:
        """POST /drpay/request"""
        assert self._seller_flow is not None
        try:
            data = await request.json()
            pr = PaymentRequest.model_validate(data)
        except Exception as e:
            return web.json_response(
                {"error": {"code": "INVALID_REQUEST", "message": str(e)}},
                status=400,
            )

        result = self._seller_flow.handle_request(pr)
        if isinstance(result, ErrorResponse):
            return web.json_response(result.model_dump(), status=400)
        return web.json_response(result.model_dump())

    async def _handle_payment_broadcast(self, request: web.Request) -> web.Response:
        """POST /drpay/broadcast"""
        assert self._seller_flow is not None
        try:
            data = await request.json()
            pb = PaymentBroadcast.model_validate(data)
        except Exception as e:
            return web.json_response(
                {"error": {"code": "INVALID_REQUEST", "message": str(e)}},
                status=400,
            )

        result = await self._seller_flow.handle_broadcast(pb)
        if isinstance(result, ErrorResponse):
            return web.json_response(result.model_dump(), status=400)
        return web.json_response(result.model_dump())

    async def start(self) -> None:
        """Start the HTTP server."""
        self._seller_flow = SellerFlow(self._wallet, self._services, self._handlers)
        self._app = web.Application()
        self._app.router.add_get("/.well-known/digirails.json", self._handle_manifest)
        self._app.router.add_post("/drpay/request", self._handle_payment_request)
        self._app.router.add_post("/drpay/broadcast", self._handle_payment_broadcast)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()

    async def stop(self) -> None:
        """Stop the HTTP server."""
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
