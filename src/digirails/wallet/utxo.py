"""UTXO tracking and coin selection."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from digirails.network.constants import SATOSHIS_PER_DGB


@dataclass
class Utxo:
    txid: str
    vout: int
    amount_sat: int
    script_pubkey: bytes
    confirmations: int = 0

    @property
    def amount_dgb(self) -> Decimal:
        return Decimal(self.amount_sat) / Decimal(SATOSHIS_PER_DGB)

    def as_tuple(self) -> tuple[str, int, int, bytes]:
        """Return (txid, vout, amount_sat, script_pubkey) for build_payment_tx."""
        return (self.txid, self.vout, self.amount_sat, self.script_pubkey)


class UtxoSet:
    """Track and select UTXOs for spending."""

    def __init__(self) -> None:
        self._utxos: dict[tuple[str, int], Utxo] = {}

    def add(self, utxo: Utxo) -> None:
        self._utxos[(utxo.txid, utxo.vout)] = utxo

    def remove(self, txid: str, vout: int) -> None:
        self._utxos.pop((txid, vout), None)

    def all(self) -> list[Utxo]:
        return list(self._utxos.values())

    @property
    def total_sat(self) -> int:
        return sum(u.amount_sat for u in self._utxos.values())

    @property
    def total_dgb(self) -> Decimal:
        return Decimal(self.total_sat) / Decimal(SATOSHIS_PER_DGB)

    def select(self, target_sat: int) -> list[Utxo]:
        """Select UTXOs to cover target amount (largest-first strategy).

        Returns a list of UTXOs whose combined value >= target_sat.
        Raises ValueError if insufficient funds.
        """
        if self.total_sat < target_sat:
            raise ValueError(
                f"Insufficient funds: have {self.total_sat} sat, need {target_sat} sat"
            )

        # Sort largest first for fewer inputs (lower fees)
        sorted_utxos = sorted(self._utxos.values(), key=lambda u: u.amount_sat, reverse=True)
        selected: list[Utxo] = []
        total = 0
        for utxo in sorted_utxos:
            selected.append(utxo)
            total += utxo.amount_sat
            if total >= target_sat:
                break
        return selected

    def clear(self) -> None:
        self._utxos.clear()
