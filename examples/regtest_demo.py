"""Self-contained regtest demo: two agents transact.

Prerequisites:
    1. DigiByte Core running in regtest mode:
       digibyted -regtest -daemon -server -rpcuser=digirails -rpcpassword=digirails -txindex=1 -fallbackfee=0.0001

    2. Install the SDK:
       pip install digirails

Usage:
    python regtest_demo.py
"""

import asyncio

from digirails import Agent, ServiceCategory, REGTEST


def handle_echo(params: dict) -> dict:
    """Echo service: returns the input message."""
    return {"echo": params.get("message", "(empty)"), "processed_by": "digirails-demo-seller"}


async def main():
    rpc_url = "http://digirails:digirails@127.0.0.1:18443"

    # --- Create agents ---
    seller = Agent.generate(network=REGTEST, rpc_url=rpc_url)
    buyer = Agent.generate(network=REGTEST, rpc_url=rpc_url)

    print(f"Seller address: {seller.address}")
    print(f"Buyer  address: {buyer.address}")
    print()

    # --- Register a service on the seller ---
    seller.register_service(
        service_id="echo",
        handler=handle_echo,
        price="0.001",
        description="Echo service",
        category=ServiceCategory.GENERAL_COMPUTE,
    )

    # Start seller HTTP server in background
    await seller.serve(host="127.0.0.1", port=9001)
    print("Seller server running on http://127.0.0.1:9001")

    # --- Fund the buyer ---
    # Import buyer's address so listunspent can find coinbase outputs
    await buyer.rpc.importaddress(buyer.address, "buyer", False)
    # Mine 101 blocks to buyer's address (coinbase maturity = 100)
    await buyer.rpc.generatetoaddress(101, buyer.address)
    balance = await buyer.balance()
    print(f"Buyer funded: {balance} DGB")
    print()

    # --- Execute the payment flow ---
    print("=== Payment Flow ===")
    print("1. Buyer discovers seller manifest...")
    print("2. Buyer sends SERVICE_REQUEST...")
    print("3. Seller returns PAYMENT_INVOICE...")
    print("4. Buyer builds, signs, broadcasts TX...")
    print("5. Buyer sends PAYMENT_BROADCAST...")
    print("6. Seller verifies payment, executes service...")
    print("7. Seller returns SERVICE_DELIVERY...")
    print()

    result = await buyer.request_service(
        seller_url="http://127.0.0.1:9001",
        service_id="echo",
        params={"message": "Hello from DigiRails!"},
        max_amount="0.01",
    )

    print(f"Result: {result.result}")
    print(f"Status: {result.status}")
    print()
    print("=== Demo Complete ===")

    # Cleanup
    await seller.close()
    await buyer.close()


if __name__ == "__main__":
    asyncio.run(main())
