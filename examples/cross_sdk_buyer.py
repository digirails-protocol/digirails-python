"""Cross-SDK test: Python buyer paying a Node.js seller.

Prerequisites:
    1. DGB Core regtest running with a legacy wallet
    2. Node.js seller running: npx tsx examples/cross_sdk_seller.ts
       (from the digirails-node directory)

Usage:
    python cross_sdk_buyer.py
"""

import asyncio
from digirails import Agent, REGTEST


async def main():
    rpc_url = "http://digirails:digirails@127.0.0.1:18443"

    buyer = Agent.generate(network=REGTEST, rpc_url=rpc_url)
    print(f"PYTHON BUYER address: {buyer.address}")

    # Fund buyer
    await buyer.rpc.importaddress(buyer.address, "buyer", False)
    await buyer.rpc.generatetoaddress(101, buyer.address)
    balance = await buyer.balance()
    print(f"Buyer funded: {balance} DGB")
    print()

    # Discover Node.js seller manifest
    manifest = await buyer.discover("http://127.0.0.1:9003")
    if manifest:
        print(f"Discovered seller: {manifest.agent}")
        print(f"  Services: {[s.id for s in manifest.services]}")
    else:
        print("ERROR: Could not discover seller manifest!")
        await buyer.close()
        return

    print()
    print("=== Cross-SDK Payment Flow (Python buyer -> Node.js seller) ===")

    result = await buyer.request_service(
        seller_url="http://127.0.0.1:9003",
        service_id="echo",
        params={"message": "Hello from Python to Node.js!"},
        max_amount="0.01",
    )

    print(f"Result: {result.result}")
    print(f"Status: {result.status}")
    print()

    if result.result and result.result.get("cross_sdk"):
        print("=== CROSS-SDK INTEROP TEST PASSED ===")
    else:
        print("=== CROSS-SDK TEST FAILED ===")

    await buyer.close()


if __name__ == "__main__":
    asyncio.run(main())
