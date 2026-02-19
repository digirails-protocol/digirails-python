"""Sell a service via DigiRails.

Usage:
    python quickstart_seller.py

Starts a server on port 9001 that other agents can buy from.
"""

import asyncio

from digirails import Agent, ServiceCategory, REGTEST


def handle_echo(params: dict) -> dict:
    """Simple echo service handler."""
    return {"echo": params.get("message", "No message provided")}


async def main():
    seller = Agent.generate(
        network=REGTEST,
        rpc_url="http://digirails:digirails@127.0.0.1:18443",
    )
    print(f"Seller address: {seller.address}")

    seller.register_service(
        service_id="echo",
        handler=handle_echo,
        price="0.001",
        description="Simple echo service — returns your message back",
        category=ServiceCategory.GENERAL_COMPUTE,
    )

    print("Starting server on http://0.0.0.0:9001")
    print("Other agents can now buy the 'echo' service.")
    await seller.serve(port=9001)

    # Keep running
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        await seller.close()


if __name__ == "__main__":
    asyncio.run(main())
