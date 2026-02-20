"""Agent: the unified high-level API for DigiRails."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from digirails.config import DigiRailsConfig
from digirails.crypto.keys import generate_keypair, wif_to_privkey
from digirails.discovery.manifest_client import fetch_manifest
from digirails.models.enums import ConfirmationTier, ServiceCategory
from digirails.models.manifest import Manifest
from digirails.models.messages import ServiceDelivery
from digirails.network.params import MAINNET, NetworkParams
from digirails.payment.flow import PaymentFlow
from digirails.rpc.client import RpcClient
from digirails.server import DigiRailsServer
from digirails.wallet.wallet import Wallet


class Agent:
    """A DigiRails agent — can act as buyer, seller, or both.

    This is the primary interface for the SDK. Typical usage:

        async with Agent.generate(network=REGTEST, rpc_url="...") as agent:
            result = await agent.request_service(
                seller_url="http://...",
                service_id="echo",
                params={"message": "Hello"},
            )
    """

    def __init__(
        self,
        config: DigiRailsConfig | None = None,
        *,
        network: NetworkParams | None = None,
        private_key: str | bytes | None = None,
        rpc_url: str | None = None,
        rpc_username: str | None = None,
        rpc_password: str | None = None,
    ):
        cfg = config or DigiRailsConfig()
        net = network or cfg.network

        # Resolve private key
        if isinstance(private_key, str):
            if len(private_key) == 64:
                # Hex-encoded
                pk_bytes = bytes.fromhex(private_key)
            else:
                # WIF
                pk_bytes, _, _ = wif_to_privkey(private_key)
        elif isinstance(private_key, bytes):
            pk_bytes = private_key
        elif cfg.private_key:
            if len(cfg.private_key) == 64:
                pk_bytes = bytes.fromhex(cfg.private_key)
            else:
                pk_bytes, _, _ = wif_to_privkey(cfg.private_key)
        else:
            raise ValueError(
                "No private key provided. Use Agent.generate() for a new key, "
                "or pass private_key= as hex, WIF, or bytes."
            )

        # Build RPC client
        url = rpc_url or cfg.effective_rpc_url
        user = rpc_username or cfg.rpc_username
        pw = rpc_password or cfg.rpc_password
        self._rpc = RpcClient(url=url, username=user, password=pw, network=net)

        # Build wallet
        self._wallet = Wallet(pk_bytes, network=net, rpc=self._rpc)
        self._network = net
        self._flow = PaymentFlow(self._wallet)
        self._server: DigiRailsServer | None = None

    @classmethod
    def generate(
        cls,
        network: NetworkParams = MAINNET,
        rpc_url: str | None = None,
        rpc_username: str | None = None,
        rpc_password: str | None = None,
        **kwargs: Any,
    ) -> Agent:
        """Create a new agent with a freshly generated key pair."""
        privkey, _, _ = generate_keypair(network)
        return cls(
            network=network,
            private_key=privkey,
            rpc_url=rpc_url,
            rpc_username=rpc_username,
            rpc_password=rpc_password,
            **kwargs,
        )

    # --- Identity ---

    @property
    def address(self) -> str:
        return self._wallet.address

    @property
    def public_key(self) -> bytes:
        return self._wallet.public_key

    @property
    def wallet(self) -> Wallet:
        return self._wallet

    @property
    def rpc(self) -> RpcClient:
        return self._rpc

    # --- Buyer operations ---

    async def request_service(
        self,
        seller_url: str,
        service_id: str,
        params: dict[str, Any] | None = None,
        max_amount: str = "0.01",
        confirmation_tier: ConfirmationTier = ConfirmationTier.MEMPOOL,
        test: bool = False,
    ) -> ServiceDelivery:
        """Complete the full payment flow in one call.

        1. Fetch seller manifest
        2. Send PAYMENT_REQUEST
        3. Receive PAYMENT_INVOICE
        4. Build + sign + broadcast transaction
        5. Send PAYMENT_BROADCAST
        6. Receive SERVICE_DELIVERY

        Set test=True to mark the on-chain OP_RETURN with the test flag.
        """
        # Optionally fetch manifest to discover seller address
        manifest = await self.discover(seller_url)
        seller_address = manifest.address if manifest else ""

        return await self._flow.buy(
            seller_url=seller_url,
            service_id=service_id,
            params=params,
            max_amount=max_amount,
            confirmation_tier=confirmation_tier,
            seller_address=seller_address,
            test=test,
        )

    async def discover(self, url: str) -> Manifest | None:
        """Fetch and validate a seller's capabilities manifest."""
        try:
            return await fetch_manifest(url)
        except Exception:
            return None

    # --- Seller operations ---

    def register_service(
        self,
        service_id: str,
        handler: Callable[..., Any],
        price: str,
        description: str = "",
        category: ServiceCategory = ServiceCategory.GENERAL_COMPUTE,
    ) -> None:
        """Register a service that this agent offers."""
        if self._server is None:
            self._server = DigiRailsServer(self._wallet)
        self._server.register_service(
            service_id=service_id,
            handler=handler,
            price=price,
            description=description,
            category=int(category),
        )

    async def serve(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        """Start the seller HTTP server."""
        if self._server is None:
            self._server = DigiRailsServer(self._wallet, host=host, port=port)
        else:
            self._server._host = host
            self._server._port = port
        await self._server.start()

    # --- Wallet operations ---

    async def balance(self) -> Decimal:
        return await self._wallet.balance()

    # --- Lifecycle ---

    async def close(self) -> None:
        """Clean up resources."""
        if self._server:
            await self._server.stop()
        await self._rpc.close()

    async def __aenter__(self) -> Agent:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
