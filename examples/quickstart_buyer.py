"""Buy a service from a DigiRails agent.

Usage:
    python quickstart_buyer.py

Requires a seller running at http://127.0.0.1:9001.
"""

import asyncio

from digirails import Agent, REGTEST


async def main():
    async with Agent.generate(
        network=REGTEST,
        rpc_url="http://digirails:digirails@127.0.0.1:18443",
    ) as buyer:
        print(f"Buyer address: {buyer.address}")

        # Fund the buyer (regtest only: mine 101 blocks for coinbase maturity)
        await buyer.rpc.generatetoaddress(101, buyer.address)
        print(f"Balance: {await buyer.balance()} DGB")

        # Buy a service — one line!
        result = await buyer.request_service(
            seller_url="http://127.0.0.1:9001",
            service_id="echo",
            params={"message": "Hello from DigiRails!"},
            max_amount="0.01",
        )
        print(f"Service delivered: {result.result}")


if __name__ == "__main__":
    asyncio.run(main())
