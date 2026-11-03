"""Core value objects: deal terms, signed negotiation messages, agreed deals."""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from . import crypto

CENT = Decimal("0.01")
TENTH = Decimal("0.1")
BPS = Decimal("10000")

PRODUCT_FX_FORWARD = "fx_forward"
PRODUCT_LC_CONFIRMATION = "lc_confirmation"
PRODUCTS = (PRODUCT_FX_FORWARD, PRODUCT_LC_CONFIRMATION)


def dec(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def q_bps(value: Any) -> Decimal:
    """Prices are quantised to 0.1 bp so equal prices hash identically."""
    return dec(value).quantize(TENTH, rounding=ROUND_HALF_UP)


def money(value: Any) -> Decimal:
    return dec(value).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Terms:
    """What is being traded.

    fx_forward:      price_bps is the spread over the forward mid, charged once
                     on the notional. (Only that spread cost is settled in this
                     PoC; the principal exchange itself is out of scope.)
    lc_confirmation: price_bps is the confirmation fee, per annum, charged
                     pro rata over tenor_days on a 360-day basis.
    """

    product: str
    instrument: str
    currency: str
    notional: Decimal
    price_bps: Decimal
    tenor_days: int
    beneficiary_country: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "notional", money(self.notional))
        object.__setattr__(self, "price_bps", q_bps(self.price_bps))
        if self.product not in PRODUCTS:
            raise ValueError(f"unknown product: {self.product}")
        if self.notional <= 0:
            raise ValueError("notional must be positive")
        if self.price_bps < 0:
            raise ValueError("price_bps must not be negative")
        if self.tenor_days <= 0:
            raise ValueError("tenor_days must be positive")

    def cost(self) -> Decimal:
        """Cash amount the buyer owes the seller at settlement."""
        amount = self.notional * self.price_bps / BPS
        if self.product == PRODUCT_LC_CONFIRMATION:
            amount = amount * Decimal(self.tenor_days) / Decimal(360)
        return money(amount)

    def payload(self) -> dict:
        return {
            "product": self.product,
            "instrument": self.instrument,
            "currency": self.currency,
            "notional": str(self.notional),
            "price_bps": str(self.price_bps),
            "tenor_days": self.tenor_days,
            "beneficiary_country": self.beneficiary_country,
        }

    def digest(self) -> str:
        return crypto.digest(self.payload())

    def with_price(self, price_bps: Any) -> "Terms":
        return replace(self, price_bps=q_bps(price_bps))

    def same_except_price(self, other: "Terms") -> bool:
        return replace(self, price_bps=Decimal("0")) == replace(other, price_bps=Decimal("0"))


@dataclass(frozen=True)
class Message:
    """One signed step of a negotiation: offer, counter, accept or reject."""

    msg_id: str
    negotiation_id: str
    sender: str
    kind: str  # offer | counter | accept | reject
    seq: int
    terms: Optional[Terms]
    text: str
    ref_terms_hash: Optional[str]  # accept: digest of the exact terms being accepted
    sent_at: str
    signature: str = ""

    def signing_payload(self) -> dict:
        return {
            "msg_id": self.msg_id,
            "negotiation_id": self.negotiation_id,
            "sender": self.sender,
            "kind": self.kind,
            "seq": self.seq,
            "terms": self.terms.payload() if self.terms else None,
            "text": self.text,
            "ref_terms_hash": self.ref_terms_hash,
            "sent_at": self.sent_at,
        }


@dataclass(frozen=True)
class Deal:
    """A bilateral commitment: the offer one side signed plus the acceptance
    the other side signed over the same terms hash. Both messages are kept as
    the evidence trail for later disputes."""

    deal_id: str
    negotiation_id: str
    buyer: str
    seller: str
    terms: Terms
    offer: Message
    accept: Message
    agreed_at: str

    def expected_cost(self) -> Decimal:
        return self.terms.cost()
