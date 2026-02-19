"""Key storage backends for DigiRails agents."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from digirails.exceptions import KeystoreError


class Keystore(ABC):
    """Abstract key storage backend."""

    @abstractmethod
    def load(self) -> bytes:
        """Load the 32-byte private key."""
        ...

    @abstractmethod
    def save(self, private_key: bytes) -> None:
        """Save a 32-byte private key."""
        ...


class EncryptedKeystore(Keystore):
    """AES-256-GCM encrypted keyfile.

    File format: salt (16B) + nonce (12B) + ciphertext + tag (16B)
    Key derivation: PBKDF2-SHA256 with 600,000 iterations.
    """

    SALT_LEN = 16
    NONCE_LEN = 12
    ITERATIONS = 600_000

    def __init__(self, path: Path | str, password: str):
        self.path = Path(path)
        self._password = password.encode("utf-8")

    def _derive_key(self, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=self.ITERATIONS,
        )
        return kdf.derive(self._password)

    def load(self) -> bytes:
        try:
            data = self.path.read_bytes()
        except FileNotFoundError as e:
            raise KeystoreError(f"Keyfile not found: {self.path}") from e

        if len(data) < self.SALT_LEN + self.NONCE_LEN + 32 + 16:
            raise KeystoreError("Keyfile too short — corrupted or wrong format")

        salt = data[: self.SALT_LEN]
        nonce = data[self.SALT_LEN : self.SALT_LEN + self.NONCE_LEN]
        ciphertext = data[self.SALT_LEN + self.NONCE_LEN :]

        key = self._derive_key(salt)
        aesgcm = AESGCM(key)
        try:
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        except Exception as e:
            raise KeystoreError("Decryption failed — wrong password or corrupted keyfile") from e

        if len(plaintext) != 32:
            raise KeystoreError(f"Decrypted key has wrong length: {len(plaintext)}")
        return plaintext

    def save(self, private_key: bytes) -> None:
        if len(private_key) != 32:
            raise KeystoreError(f"Private key must be 32 bytes, got {len(private_key)}")

        salt = os.urandom(self.SALT_LEN)
        nonce = os.urandom(self.NONCE_LEN)
        key = self._derive_key(salt)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, private_key, None)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(salt + nonce + ciphertext)


class EnvKeystore(Keystore):
    """Read private key from environment variable (hex-encoded)."""

    def __init__(self, env_var: str = "DIGIRAILS_PRIVATE_KEY"):
        self.env_var = env_var

    def load(self) -> bytes:
        value = os.environ.get(self.env_var)
        if not value:
            raise KeystoreError(f"Environment variable {self.env_var} not set")
        try:
            key = bytes.fromhex(value)
        except ValueError as e:
            raise KeystoreError(f"Invalid hex in {self.env_var}") from e
        if len(key) != 32:
            raise KeystoreError(f"Key from {self.env_var} has wrong length: {len(key)}")
        return key

    def save(self, private_key: bytes) -> None:
        raise KeystoreError("Cannot save to environment variable — set it manually")


class RawKeystore(Keystore):
    """In-memory key (for testing only)."""

    def __init__(self, private_key: bytes):
        if len(private_key) != 32:
            raise KeystoreError(f"Private key must be 32 bytes, got {len(private_key)}")
        self._key = private_key

    def load(self) -> bytes:
        return self._key

    def save(self, private_key: bytes) -> None:
        self._key = private_key
