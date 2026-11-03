"""Guardrails enforced in the rail, not in any agent's prompt.

Pure functions of (terms, mandate, usage, time). No agent, model or prompt can
change what they decide. check_side applies one party's mandate; check_bank_rules
applies the operating bank's own rules (jurisdiction screen, price sanity band).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, FrozenSet, List, Optional, Tuple

from .kya import Tier
from .mandate import Mandate
from .models import PRODUCT_FX_FORWARD, PRODUCT_LC_CONFIRMATION, Terms

ALLOW = "ALLOW"
REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
DENY = "DENY"


@dataclass(frozen=True)
class Violation:
    code: str
    detail: str = ""


@dataclass(frozen=True)
class ApprovalRequirement:
    agent_id: str
    reason: str


@dataclass
class PolicyResult:
    violations: List[Violation] = field(default_factory=list)
    approvals: List[ApprovalRequirement] = field(default_factory=list)

    @property
    def outcome(self) -> str:
        if self.violations:
            return DENY
        if self.approvals:
            return REQUIRE_APPROVAL
        return ALLOW

    @property
    def codes(self) -> Tuple[str, ...]:
        return tuple(v.code for v in self.violations)

    def extend(self, other: "PolicyResult") -> None:
        self.violations.extend(other.violations)
        self.approvals.extend(other.approvals)


DEFAULT_SANITY_BAND: Dict[str, Tuple[Decimal, Decimal]] = {
    PRODUCT_FX_FORWARD: (Decimal("0"), Decimal("100")),
    PRODUCT_LC_CONFIRMATION: (Decimal("0"), Decimal("400")),
}

# Illustrative only. A real bank screens against official, continuously updated
# sanctions lists through its screening platform, not a hard-coded set.
DEFAULT_RESTRICTED_COUNTRIES: FrozenSet[str] = frozenset({"KP", "IR"})


class Policy:
    def __init__(
        self,
        restricted_countries: Optional[FrozenSet[str]] = None,
        price_sanity_bps: Optional[Dict[str, Tuple[Decimal, Decimal]]] = None,
    ) -> None:
        self.restricted_countries = (
            DEFAULT_RESTRICTED_COUNTRIES if restricted_countries is None else restricted_countries
        )
        self.price_sanity_bps = DEFAULT_SANITY_BAND if price_sanity_bps is None else price_sanity_bps

    def check_bank_rules(self, terms: Terms) -> List[Violation]:
        out: List[Violation] = []
        if terms.product == PRODUCT_LC_CONFIRMATION and not terms.beneficiary_country:
            out.append(Violation("BENEFICIARY_COUNTRY_MISSING", "trade finance needs a beneficiary country"))
        if terms.beneficiary_country and terms.beneficiary_country.upper() in self.restricted_countries:
            out.append(Violation("RESTRICTED_JURISDICTION", terms.beneficiary_country.upper()))
        band = self.price_sanity_bps.get(terms.product)
        if band and not (band[0] <= terms.price_bps <= band[1]):
            out.append(Violation("PRICE_OUTSIDE_SANITY_BAND", f"{terms.price_bps} bps"))
        return out

    def check_side(
        self,
        *,
        agent_id: str,
        side: str,
        mandate: Mandate,
        terms: Terms,
        counterparty_id: str,
        used: Decimal,
        now: datetime,
        tier: Tier,
    ) -> PolicyResult:
        res = PolicyResult()
        add = res.violations.append
        if mandate.agent_id != agent_id:
            add(Violation("MANDATE_AGENT_MISMATCH", f"{mandate.agent_id} != {agent_id}"))
        if mandate.side != side:
            add(Violation("MANDATE_SIDE_MISMATCH", f"{mandate.side} != {side}"))
        if now < mandate.valid_from:
            add(Violation("MANDATE_NOT_YET_VALID"))
        if now >= mandate.valid_until:
            add(Violation("MANDATE_EXPIRED"))
        if terms.product not in mandate.products:
            add(Violation("PRODUCT_NOT_PERMITTED", terms.product))
        if terms.instrument not in mandate.instruments:
            add(Violation("INSTRUMENT_NOT_PERMITTED", terms.instrument))
        if terms.currency != mandate.currency:
            add(Violation("CURRENCY_NOT_PERMITTED", terms.currency))
        if terms.notional > mandate.max_notional:
            add(Violation("NOTIONAL_ABOVE_MANDATE", f"{terms.notional} > {mandate.max_notional}"))
        if terms.tenor_days > mandate.max_tenor_days:
            add(Violation("TENOR_ABOVE_MANDATE", f"{terms.tenor_days}d > {mandate.max_tenor_days}d"))
        limit = mandate.price_limit_bps.get(terms.product)
        if limit is None:
            add(Violation("PRICE_LIMIT_UNDEFINED", terms.product))
        elif side == "buy" and terms.price_bps > limit:
            add(Violation("PRICE_OUTSIDE_MANDATE", f"{terms.price_bps} bps > ceiling {limit}"))
        elif side == "sell" and terms.price_bps < limit:
            add(Violation("PRICE_OUTSIDE_MANDATE", f"{terms.price_bps} bps < floor {limit}"))
        if counterparty_id not in mandate.counterparties:
            add(Violation("COUNTERPARTY_NOT_PERMITTED", counterparty_id))
        if used + terms.notional > mandate.aggregate_cap:
            add(Violation("AGGREGATE_CAP_EXCEEDED", f"{used} + {terms.notional} > {mandate.aggregate_cap}"))
        if terms.notional > mandate.approval_threshold:
            res.approvals.append(ApprovalRequirement(agent_id, "NOTIONAL_ABOVE_APPROVAL_THRESHOLD"))
        if tier is Tier.APPROVAL:
            res.approvals.append(ApprovalRequirement(agent_id, "TIER_REQUIRES_APPROVAL"))
        return res
