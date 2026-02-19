"""Async JSON-RPC client for DigiByte chain data."""

from __future__ import annotations

import json
from typing import Any

import aiohttp

from digirails.exceptions import NetworkError, RpcError
from digirails.network.params import MAINNET, NetworkParams


class RpcClient:
    """Async JSON-RPC 2.0 client.

    Works identically against rpc.digirails.org (light mode)
    or a local DigiByte Core node (full mode / regtest).
    """

    def __init__(
        self,
        url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        network: NetworkParams = MAINNET,
    ):
        self.url = url or network.default_rpc_url
        self._auth: aiohttp.BasicAuth | None = None
        if username and password:
            self._auth = aiohttp.BasicAuth(username, password)
        elif "://" in self.url and "@" in self.url:
            # Parse credentials from URL: http://user:pass@host:port
            from urllib.parse import urlparse

            parsed = urlparse(self.url)
            if parsed.username and parsed.password:
                self._auth = aiohttp.BasicAuth(parsed.username, parsed.password)
                self.url = parsed._replace(
                    netloc=f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname
                ).geturl()

        self._session: aiohttp.ClientSession | None = None
        self._request_id = 0

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(auth=self._auth)
        return self._session

    async def call(self, method: str, params: list[Any] | None = None) -> Any:
        """Make a JSON-RPC 2.0 call."""
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or [],
            "id": self._request_id,
        }
        session = await self._get_session()
        try:
            async with session.post(
                self.url,
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                body = await resp.text()
                if resp.status == 429:
                    raise NetworkError("Rate limit exceeded")
                data = json.loads(body)
        except aiohttp.ClientError as e:
            raise NetworkError(f"Connection error: {e}") from e
        except json.JSONDecodeError as e:
            raise NetworkError(f"Invalid JSON response: {e}") from e

        if "error" in data and data["error"] is not None:
            err = data["error"]
            raise RpcError(err.get("code", -1), err.get("message", "Unknown error"))

        return data.get("result")

    # --- Typed convenience methods (matching the RPC Worker's allowlist) ---

    async def getblockcount(self) -> int:
        return await self.call("getblockcount")

    async def getblockhash(self, height: int) -> str:
        return await self.call("getblockhash", [height])

    async def getblock(self, blockhash: str, verbosity: int = 1) -> dict[str, Any]:
        return await self.call("getblock", [blockhash, verbosity])

    async def getblockchaininfo(self) -> dict[str, Any]:
        return await self.call("getblockchaininfo")

    async def getrawtransaction(
        self, txid: str, verbose: bool = True
    ) -> dict[str, Any] | str:
        return await self.call("getrawtransaction", [txid, verbose])

    async def gettxout(self, txid: str, vout: int) -> dict[str, Any] | None:
        return await self.call("gettxout", [txid, vout])

    async def getrawmempool(self) -> list[str]:
        return await self.call("getrawmempool")

    async def getmempoolentry(self, txid: str) -> dict[str, Any]:
        return await self.call("getmempoolentry", [txid])

    async def sendrawtransaction(self, hex_string: str) -> str:
        return await self.call("sendrawtransaction", [hex_string])

    # --- Regtest / full-mode only helpers ---

    async def generatetoaddress(self, nblocks: int, address: str) -> list[str]:
        """Mine blocks on regtest. Not available on public RPC."""
        return await self.call("generatetoaddress", [nblocks, address])

    async def listunspent(
        self, minconf: int = 1, maxconf: int = 9999999, addresses: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """List unspent outputs. Available on regtest/full mode, not on public RPC."""
        params: list[Any] = [minconf, maxconf]
        if addresses:
            params.append(addresses)
        return await self.call("listunspent", params)

    async def importaddress(self, address: str, label: str = "", rescan: bool = False) -> None:
        """Import an address for watch-only tracking. Regtest/full mode only."""
        await self.call("importaddress", [address, label, rescan])

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
