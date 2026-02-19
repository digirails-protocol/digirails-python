"""DigiByte network parameters for mainnet, testnet, and regtest."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NetworkParams:
    name: str
    bech32_hrp: str
    pubkey_version: int  # Base58 P2PKH version byte
    script_version: int  # Base58 P2SH version byte
    wif_version: int  # WIF private key prefix
    bip44_coin_type: int
    default_rpc_port: int
    default_p2p_port: int
    default_rpc_url: str  # For light mode
    magic: bytes  # 4-byte network magic


MAINNET = NetworkParams(
    name="mainnet",
    bech32_hrp="dgb",
    pubkey_version=0x1E,  # "D..."
    script_version=0x3F,  # "S..."
    wif_version=0x80,
    bip44_coin_type=20,
    default_rpc_port=14022,
    default_p2p_port=12024,
    default_rpc_url="https://rpc.digirails.org",
    magic=bytes([0xFA, 0xC3, 0xB6, 0xDA]),
)

TESTNET = NetworkParams(
    name="testnet",
    bech32_hrp="dgbt",
    pubkey_version=0x7E,
    script_version=0x8C,
    wif_version=0xFE,
    bip44_coin_type=20,
    default_rpc_port=14023,
    default_p2p_port=12026,
    default_rpc_url="https://rpc.digirails.org",
    magic=bytes([0xFD, 0xC8, 0xBD, 0xDD]),
)

REGTEST = NetworkParams(
    name="regtest",
    bech32_hrp="dgbrt",
    pubkey_version=0x7E,
    script_version=0x8C,
    wif_version=0xFE,
    bip44_coin_type=20,
    default_rpc_port=18443,
    default_p2p_port=18444,
    default_rpc_url="http://127.0.0.1:18443",
    magic=bytes([0xFA, 0xBF, 0xB5, 0xDA]),
)
