# digirails

Python SDK for the [DR-Pay protocol](https://github.com/digirails-protocol/digirails-spec) — permissionless AI agent payments on DigiByte.

## What is this?

DigiRails enables autonomous AI agents to discover, negotiate with, and pay each other using DigiByte's Layer 1 blockchain. This SDK implements the DR-Pay protocol: the 4-message payment flow, agent identity, service manifests, and on-chain data encoding.

Every payment settles on-chain as a standard DigiByte transaction. No sidechains, no Layer 2, no API keys.

## Install

```bash
pip install digirails
```

## Quick Start

### Buyer — purchase a service in one call

```python
import asyncio
from digirails import Agent, REGTEST

async def main():
    async with Agent.generate(
        network=REGTEST,
        rpc_url="http://digirails:digirails@127.0.0.1:18443",
    ) as buyer:
        result = await buyer.request_service(
            seller_url="http://127.0.0.1:9001",
            service_id="echo",
            params={"message": "Hello from DigiRails!"},
            max_amount="0.01",
        )
        print(result.result)

asyncio.run(main())
```

### Seller — offer a service

```python
import asyncio
from digirails import Agent, ServiceCategory, REGTEST

def handle_echo(params: dict) -> dict:
    return {"echo": params.get("message", "")}

async def main():
    seller = Agent.generate(
        network=REGTEST,
        rpc_url="http://digirails:digirails@127.0.0.1:18443",
    )
    seller.register_service(
        service_id="echo",
        handler=handle_echo,
        price="0.001",
        category=ServiceCategory.GENERAL_COMPUTE,
    )
    await seller.serve(port=9001)
    await asyncio.Event().wait()  # Run forever

asyncio.run(main())
```

## What happens under the hood

```
Buyer                                Seller
  |                                    |
  |  GET /.well-known/digirails.json   |
  |----------------------------------->|  1. Discover manifest
  |<-----------------------------------|
  |                                    |
  |  POST /drpay/request               |
  |----------------------------------->|  2. SERVICE_REQUEST
  |<-----------------------------------|  3. PAYMENT_INVOICE
  |                                    |
  |  [build, sign, broadcast tx]       |
  |                                    |
  |  POST /drpay/broadcast             |
  |----------------------------------->|  4. PAYMENT_BROADCAST
  |                                    |  5. Verify payment
  |                                    |  6. Execute service
  |<-----------------------------------|  7. SERVICE_DELIVERY
```

## Regtest Demo

Run the self-contained demo with two agents transacting locally:

```bash
# 1. Start DigiByte Core in regtest mode
digibyted -regtest -daemon -server \
  -rpcuser=digirails -rpcpassword=digirails \
  -txindex=1 -fallbackfee=0.0001

# 2. Run the demo
python examples/regtest_demo.py
```

## Features

- **Light mode**: No DigiByte node required. Connects to `rpc.digirails.org` or any RPC endpoint.
- **Async-native**: Built on asyncio + aiohttp.
- **Type-safe**: Pydantic models for all protocol messages.
- **4 dependencies**: pydantic, aiohttp, cryptography, ecdsa. All with pre-built wheels.
- **SegWit transactions**: BIP-143 signing for P2WPKH inputs.
- **Encrypted keystore**: AES-256-GCM encrypted key files.
- **All 18 service categories** from the DR-Pay spec.

## Protocol Version

Implements DR-Pay specification v0.3.0.

## License

MIT
