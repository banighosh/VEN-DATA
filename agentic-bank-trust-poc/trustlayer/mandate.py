"""Signed mandates: the machine-readable authority a company gives its agent.

Modelled loosely on the intent-mandate idea in agent payment protocols such as
AP2: a bounded, time-limited, counterparty-limited authorisation signed by the
principal. This is a simplified stand-in, not an AP2 implementation.

For a buy-side agent price_limit_bps is a ceiling (never pay more than this);
for a sell-side agent it is a floor (never sell below this).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, Tuple

from . import crypto


@dataclass(frozen=True)
class Mandate:
    mandate_id: str
    principal_id: str
    agent_id: str
    side: str  # "buy" | "sell"
    valid_from: datetime
    valid_until: datetime
    products: Tuple[str, ...]
    instruments: Tuple[str, ...]
    currency: str
    max_notional: Decimal  # per deal
    aggregate_cap: Decimal  # cumulative notional across all deals under this mandate
    price_limit_bps: Dict[str, Decimal]  # product -> ceiling (buy) or floor (sell)
    max_tenor_days: int
    counterparties: Tuple[str, ...]  # agent ids this agent may deal with
    approval_threshold: Decimal  # notional above this needs the named human owner
    nonce: str = field(default="")

    def payload(self) -> dict:
        return {
            "mandate_id": self.mandate_id,
            "principal_id": self.principal_id,
            "agent_id": self.agent_id,
            "side": self.side,
            "valid_from": self.valid_from.isoformat(),
            "valid_until": self.valid_until.isoformat(),
            "products": list(self.products),
            "instruments": list(self.instruments),
            "currency": self.currency,
            "max_notional": str(self.max_notional),
            "aggregate_cap": str(self.aggregate_cap),
            "price_limit_bps": {k: str(v) for k, v in self.price_limit_bps.items()},
            "max_tenor_days": self.max_tenor_days,
            "counterparties": list(self.counterparties),
            "approval_threshold": str(self.approval_threshold),
            "nonce": self.nonce,
        }


@dataclass(frozen=True)
class SignedMandate:
    mandate: Mandate
    signature: str


def issue(mandate: Mandate, principal_keys: crypto.KeyPair) -> SignedMandate:
    return SignedMandate(mandate, principal_keys.sign(mandate.payload()))


def verify_signature(signed: SignedMandate, principal_public_hex: str) -> bool:
    return crypto.verify(principal_public_hex, signed.mandate.payload(), signed.signature)
