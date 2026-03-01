"""Wallet: key management, UTXO tracking, and transaction building."""

from __future__ import annotations

import threading
import time as _time
from decimal import Decimal

from digirails.crypto.keys import privkey_to_pubkey, pubkey_to_p2wpkh_address, _hash160
from digirails.crypto.script import p2wpkh_script_pubkey
from digirails.crypto.transaction import Transaction, build_payment_tx
from digirails.network.constants import SATOSHIS_PER_DGB
from digirails.network.params import MAINNET, NetworkParams
from digirails.rpc.client import RpcClient
from digirails.wallet.utxo import Utxo, UtxoSet


# ---------------------------------------------------------------------------
# Module-level pending spend tracker
# ---------------------------------------------------------------------------
# Persists across Agent/Wallet instances within a process. Prevents
# double-spending when the same address is used by multiple short-lived
# Agent instances (e.g. chaos testing, rapid-fire buyer flows).
# ---------------------------------------------------------------------------

class _PendingTracker:
    """Track recently-spent outpoints and pending change outputs."""

    _TTL = 120  # seconds before entries auto-expire

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (txid, vout) -> expiry timestamp
        self._spent: dict[tuple[str, int], float] = {}
        # (txid, vout) -> (Utxo, expiry timestamp)
        self._change: dict[tuple[str, int], tuple[Utxo, float]] = {}

    def record_spend(
        self,
        spent_outpoints: list[tuple[str, int]],
        change_utxo: Utxo | None = None,
    ) -> None:
        """Record spent outpoints and optional change output."""
        now = _time.time()
        expiry = now + self._TTL
        with self._lock:
            for op in spent_outpoints:
                self._spent[op] = expiry
            if change_utxo is not None:
                key = (change_utxo.txid, change_utxo.vout)
                self._change[key] = (change_utxo, expiry)
            self._purge()

    def apply(self, address: str, utxos: list[Utxo], script_pubkey: bytes) -> list[Utxo]:
        """Filter out spent UTXOs and inject pending change for *address*."""
        with self._lock:
            self._purge()
            # Remove anything we know was recently spent
            filtered = [
                u for u in utxos
                if (u.txid, u.vout) not in self._spent
            ]
            # Add pending change outputs that belong to this address
            existing = {(u.txid, u.vout) for u in filtered}
            for key, (utxo, _exp) in self._change.items():
                if key not in existing and key not in self._spent and utxo.script_pubkey == script_pubkey:
                    filtered.append(utxo)
            return filtered

    def _purge(self) -> None:
        now = _time.time()
        self._spent = {k: v for k, v in self._spent.items() if v > now}
        self._change = {k: v for k, v in self._change.items() if v[1] > now}


_pending = _PendingTracker()


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
        self._uncommitted: tuple[list[tuple[str, int]], Utxo | None, list[Utxo]] | None = None
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
        """Fetch UTXOs from the RPC node, filtered by pending spend tracker.

        On regtest/full mode, uses listunspent then removes outpoints that
        were recently spent (but may still appear due to mempool propagation
        delay) and injects pending change outputs.
        On light mode, this is a no-op (UTXOs must be tracked manually).
        """
        if self._rpc is None:
            return

        self._utxos.clear()
        try:
            # Try listunspent (available on regtest / full mode with wallet)
            raw_utxos = await self._rpc.listunspent(0, 9999999, [self.address])
            fetched = [
                Utxo(
                    txid=u["txid"],
                    vout=u["vout"],
                    amount_sat=int(Decimal(str(u["amount"])) * SATOSHIS_PER_DGB),
                    script_pubkey=self.script_pubkey,
                    confirmations=u.get("confirmations", 0),
                )
                for u in raw_utxos
            ]
            # Apply pending spend tracker: remove spent, inject change
            resolved = _pending.apply(self.address, fetched, self.script_pubkey)
            for u in resolved:
                self._utxos.add(u)
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
        fee_sat: int = 50000,
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

        # Compute txid now (possible after signing)
        computed_txid = tx.txid()

        # Find change output (goes to self.address)
        change_utxo = None
        my_spk = self.script_pubkey
        for i, out in enumerate(tx.outputs):
            if out.script_pubkey == my_spk and out.amount > 0:
                change_utxo = Utxo(
                    txid=computed_txid,
                    vout=i,
                    amount_sat=out.amount,
                    script_pubkey=my_spk,
                    confirmations=0,
                )
                break

        # Stash pending info — committed to module-level tracker only after
        # successful broadcast to avoid phantom state on RPC failure.
        spent_outpoints = [(u.txid, u.vout) for u in selected]
        self._uncommitted = (spent_outpoints, change_utxo, list(selected))

        # Update local UTXO tracking: remove spent, add change
        for utxo in selected:
            self._utxos.remove(utxo.txid, utxo.vout)
        if change_utxo is not None:
            self._utxos.add(change_utxo)

        return tx

    async def broadcast(self, tx: Transaction) -> str:
        """Broadcast a signed transaction. Returns txid.

        On success, commits spend info to the module-level pending tracker
        so other Wallet instances (same process) see the spent outpoints.
        On failure, rolls back local UTXO state so the wallet can retry.
        """
        if self._rpc is None:
            raise RuntimeError("No RPC client configured — cannot broadcast")
        try:
            txid = await self._rpc.sendrawtransaction(tx.hex())
        except Exception:
            # Broadcast failed — roll back local state so UTXOs are available
            # for retry.  Do NOT record in _pending.
            if self._uncommitted is not None:
                spent_outpoints, change_utxo, selected = self._uncommitted
                for utxo in selected:
                    self._utxos.add(utxo)
                if change_utxo is not None:
                    self._utxos.remove(change_utxo.txid, change_utxo.vout)
                self._uncommitted = None
            raise

        # Broadcast succeeded — commit to module-level tracker
        if self._uncommitted is not None:
            spent_outpoints, change_utxo, _ = self._uncommitted
            _pending.record_spend(spent_outpoints, change_utxo)
            self._uncommitted = None

        return txid
