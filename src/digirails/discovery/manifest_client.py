"""Fetch and validate remote agent manifests."""

from __future__ import annotations

import aiohttp

from digirails.exceptions import NetworkError
from digirails.models.manifest import Manifest


async def fetch_manifest(base_url: str) -> Manifest:
    """Fetch a capabilities manifest from a seller's well-known URL.

    Tries /.well-known/digirails.json on the given base URL.
    """
    url = f"{base_url.rstrip('/')}/.well-known/digirails.json"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    raise NetworkError(
                        f"Failed to fetch manifest from {url}: HTTP {resp.status}"
                    )
                data = await resp.json()
        except aiohttp.ClientError as e:
            raise NetworkError(f"Failed to fetch manifest from {url}: {e}") from e

    return Manifest.model_validate(data)
