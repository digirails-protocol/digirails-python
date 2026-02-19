"""DigiRails exception hierarchy."""

from __future__ import annotations


class DigiRailsError(Exception):
    """Base exception for all DigiRails errors."""


class NetworkError(DigiRailsError):
    """RPC or HTTP communication failure."""


class RpcError(NetworkError):
    """JSON-RPC error response from the node."""

    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(f"RPC error {code}: {message}")


class PaymentError(DigiRailsError):
    """Error during the payment flow."""


class InvoiceExpiredError(PaymentError):
    """The payment invoice has expired."""


class InsufficientFundsError(PaymentError):
    """Wallet does not have enough DGB to pay the invoice."""


class VerificationError(PaymentError):
    """Payment verification failed."""


class TransactionError(DigiRailsError):
    """Error building or signing a transaction."""


class KeystoreError(DigiRailsError):
    """Error loading or saving keys."""
