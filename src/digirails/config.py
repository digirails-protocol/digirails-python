"""DigiRails SDK configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Literal

from digirails.network.params import MAINNET, REGTEST, TESTNET, NetworkParams


@dataclass
class DigiRailsConfig:
    network: NetworkParams = field(default_factory=lambda: MAINNET)
    mode: Literal["light", "full"] = "light"
    rpc_url: str | None = None
    rpc_username: str | None = None
    rpc_password: str | None = None
    private_key: str | None = None  # WIF or hex
    keyfile_path: Path | None = None
    keyfile_password: str | None = None
    env_key_var: str | None = None
    spending_limit_per_tx: Decimal = Decimal("1.0")
    spending_limit_per_hour: Decimal = Decimal("100.0")

    @property
    def effective_rpc_url(self) -> str:
        if self.rpc_url:
            return self.rpc_url
        return self.network.default_rpc_url

    @classmethod
    def from_env(cls) -> DigiRailsConfig:
        """Build config from DIGIRAILS_* environment variables."""
        network_name = os.environ.get("DIGIRAILS_NETWORK", "mainnet")
        network = {"mainnet": MAINNET, "testnet": TESTNET, "regtest": REGTEST}.get(
            network_name, MAINNET
        )
        return cls(
            network=network,
            mode=os.environ.get("DIGIRAILS_MODE", "light"),  # type: ignore[arg-type]
            rpc_url=os.environ.get("DIGIRAILS_RPC_URL"),
            rpc_username=os.environ.get("DIGIRAILS_RPC_USER"),
            rpc_password=os.environ.get("DIGIRAILS_RPC_PASS"),
            private_key=os.environ.get("DIGIRAILS_PRIVATE_KEY"),
            env_key_var="DIGIRAILS_PRIVATE_KEY" if os.environ.get("DIGIRAILS_PRIVATE_KEY") else None,
        )

    @classmethod
    def regtest(
        cls,
        rpc_url: str = "http://127.0.0.1:18443",
        rpc_username: str = "digirails",
        rpc_password: str = "digirails",
        **kwargs: object,
    ) -> DigiRailsConfig:
        """Convenience constructor for regtest development."""
        return cls(
            network=REGTEST,
            rpc_url=rpc_url,
            rpc_username=rpc_username,
            rpc_password=rpc_password,
            **kwargs,  # type: ignore[arg-type]
        )
