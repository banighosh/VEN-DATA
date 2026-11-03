"""Ed25519 signing and canonical hashing.

Everything that carries authority in the trust layer (mandates, negotiation
messages, audit entries) is a JSON-safe dict signed over its canonical
encoding. Verification needs only the public key, so the gateway never holds
a principal's or an agent's secret.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def canonical_bytes(payload: Any) -> bytes:
    """Stable JSON encoding: sorted keys, no whitespace, no NaN."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def digest(payload: Any) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


class KeyPair:
    def __init__(self, private_key: Ed25519PrivateKey) -> None:
        self._private = private_key

    @classmethod
    def generate(cls) -> "KeyPair":
        return cls(Ed25519PrivateKey.generate())

    @property
    def public_hex(self) -> str:
        raw = self._private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return raw.hex()

    def sign(self, payload: Any) -> str:
        return self._private.sign(canonical_bytes(payload)).hex()


def verify(public_hex: str, payload: Any, signature_hex: str) -> bool:
    """True only if signature_hex is a valid signature of payload by public_hex."""
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex))
        key.verify(bytes.fromhex(signature_hex), canonical_bytes(payload))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
