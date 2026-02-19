"""Wallet: key management, UTXO tracking, and transaction building."""

from __future__ import annotations

from decimal import Decimal

from digirails.crypto.keys import privkey_to_pubkey, pubkey_to_p2wpkh_address, _hash160
from digirails.crypto.script import p2wpkh_script_pubkey
from digirails.crypto.transaction import Transaction, build_payment_tx
from digirails.network.constants import SATOSHIS_PER_DGB
from digirails.network.params import MAINNET, NetworkParams
from digirails.rpc.client import RpcClient
from digirails.wallet.utxo import Utxo, UtxoSet


class Wallet:
    """Single-key wallet for DigiByte. Tracks UTXOs, builds and signs transactions."""

    def __init__(
        self,
        private_key: bytes,
        network: NetworkParams = MAINNET,
        rpc: RpcClient | None = None,
    ):
        self._private_key = private_key
        self._pubkey = privkey_to_pubkey(private_key)
        self._network = network
        self._rpc = rpc
        self._utxos = UtxoSet()
        self._address_index = 0  # For generating "fresh" invoice addresses

    @property
    def address(self) -> str:
        """Primary P2WPKH address."""
        return pubkey_to_p2wpkh_address(self._pubkey, self._network)

    @property
    def public_key(self) -> bytes:
        return self._pubkey

    @property
    def script_pubkey(self) -> bytes:
        """P2WPKH scriptPubKey for this wallet's address."""
        keyhash = _hash160(self._pubkey)
        return p2wpkh_script_pubkey(keyhash)

    def fresh_address(self) -> str:
        """Return the primary address.

        In Phase 1 (single-key), this always returns the same address.
        Phase 2 will implement HD derivation for fresh addresses per invoice.
        """
        return self.address

    async def sync_utxos(self) -> None:
        """Fetch UTXOs from the RPC node.

        On regtest/full mode, uses listunspent.
        On light mode, this is a no-op (UTXOs must be tracked manually).
        """
        if self._rpc is None:
            return

        self._utxos.clear()
        try:
            # Try listunspent (available on regtest / full mode with wallet)
            raw_utxos = await self._rpc.listunspent(0, 9999999, [self.address])
            for u in raw_utxos:
                self._utxos.add(
                    Utxo(
                        txid=u["txid"],
                        vout=u["vout"],
                        amount_sat=int(Decimal(str(u["amount"])) * SATOSHIS_PER_DGB),
                        script_pubkey=self.script_pubkey,
                        confirmations=u.get("confirmations", 0),
                    )
                )
        except Exception:
            # listunspent not available (light mode) — UTXOs stay as-is
            pass

    def add_utxo(self, utxo: Utxo) -> None:
        """Manually track a UTXO (for light mode or direct tracking)."""
        self._utxos.add(utxo)

    def spend_utxo(self, txid: str, vout: int) -> None:
        """Remove a spent UTXO from tracking."""
        self._utxos.remove(txid, vout)

    @property
    def utxo_set(self) -> UtxoSet:
        return self._utxos

    async def balance(self) -> Decimal:
        """Return wallet balance in DGB."""
        await self.sync_utxos()
        return self._utxos.total_dgb

    async def build_payment(
        self,
        to_address: str,
        amount_sat: int,
        fee_sat: int = 1000,
        op_return_data: bytes | None = None,
    ) -> Transaction:
        """Build and sign a payment transaction."""
        await self.sync_utxos()

        total_needed = amount_sat + fee_sat
        selected = self._utxos.select(total_needed)
        utxo_tuples = [u.as_tuple() for u in selected]

        tx = build_payment_tx(
            utxos=utxo_tuples,
            to_address=to_address,
            amount_sat=amount_sat,
            change_address=self.address,
            fee_sat=fee_sat,
            op_return_data=op_return_data,
            network=self._network,
        )

        # Sign all inputs
        for i in range(len(tx.inputs)):
            tx.sign_input(i, self._private_key)

        # Update UTXO tracking: remove spent, add change
        for utxo in selected:
            self._utxos.remove(utxo.txid, utxo.vout)

        return tx

    async def broadcast(self, tx: Transaction) -> str:
        """Broadcast a signed transaction. Returns txid."""
        if self._rpc is None:
            raise RuntimeError("No RPC client configured — cannot broadcast")
        return await self._rpc.sendrawtransaction(tx.hex())
