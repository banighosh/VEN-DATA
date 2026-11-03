"""Builds a complete, self-contained cast for a scenario.

Cast
  Meridian Bank        operates the trust gateway (the rail). Fictional.
  Acme Exports         corporate treasury, buy side.  Agent: acme-treasury-agent
  Harbor Capital       liquidity provider, sell side. Agent: harbor-pricing-agent
  rogue-agent          never onboarded; used to show KYA refusing an unknown agent

All names are fictional. All rates, limits and the restricted-country list are
illustrative, not market data or a real screening list.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import timedelta
from decimal import Decimal
from typing import Callable, Dict, List, Optional

from . import mandate as mandate_mod
from .agents import Agent, AgentCard, Brief, CatalogEntry
from .audit import AuditLog
from .clock import Clock
from .crypto import KeyPair
from .gateway import Approver, GatewayDenied, Mode, TrustGateway
from .kya import AgentRecord, KYARegistry, Principal, Tier
from .ledger import Ledger
from .mandate import Mandate, SignedMandate
from .models import PRODUCT_FX_FORWARD, PRODUCT_LC_CONFIRMATION, Terms
from .policy import Policy
from .strategies import RuleBasedStrategy, Strategy

BANK = "meridian-bank"
ACME = "acme-exports"
HARBOR = "harbor-capital"
BUYER = "acme-treasury-agent"
SELLER = "harbor-pricing-agent"
ROGUE = "rogue-agent"
ACME_OWNER = "priya.nair@acme.example"
HARBOR_OWNER = "tom.reyes@harbor.example"
ACME_ACCT = "ACME-OPERATING-USD"
HARBOR_ACCT = "HARBOR-REVENUE-USD"
ACME_OPENING_BALANCE = Decimal("5000000.00")

# (opening bid for the buyer, buyer ceiling, seller opening ask, seller floor), in bps
PRICING = {
    PRODUCT_FX_FORWARD: dict(instrument="USD/INR", buy_open="30", buy_max="60", sell_open="80", sell_min="40"),
    PRODUCT_LC_CONFIRMATION: dict(instrument="LC", buy_open="80", buy_max="150", sell_open="160", sell_min="90"),
}

# Optional hook: wrap the default rule-based strategy (used by `--claude`).
_default_wrapper: Optional[Callable[[Strategy], Strategy]] = None


def set_default_strategy_wrapper(fn: Optional[Callable[[Strategy], Strategy]]) -> None:
    global _default_wrapper
    _default_wrapper = fn


def default_strategy() -> Strategy:
    base = RuleBasedStrategy()
    return _default_wrapper(base) if _default_wrapper else base


@dataclass
class World:
    clock: Clock
    registry: KYARegistry
    ledger: Ledger
    audit: AuditLog
    gateway: TrustGateway
    keys: Dict[str, KeyPair]
    agents: Dict[str, Agent]
    mandates: Dict[str, SignedMandate]
    directory: Dict[str, AgentCard]
    brief_terms: Terms
    notes: List[str] = field(default_factory=list)
    registration_errors: Dict[str, tuple] = field(default_factory=dict)

    @property
    def buyer(self) -> Agent:
        return self.agents[BUYER]

    @property
    def seller(self) -> Agent:
        return self.agents[SELLER]


def build_world(
    *,
    product: str = PRODUCT_FX_FORWARD,
    notional: str = "500000",
    tenor_days: int = 90,
    beneficiary_country: Optional[str] = None,
    buyer_strategy: Optional[Strategy] = None,
    seller_strategy: Optional[Strategy] = None,
    mode: Mode = Mode.LIVE,
    approver: Optional[Approver] = None,
    buyer_tier: Tier = Tier.AUTONOMOUS,
    seller_tier: Tier = Tier.AUTONOMOUS,
    buyer_overrides: Optional[dict] = None,
    seller_overrides: Optional[dict] = None,
    tamper_buyer_mandate: bool = False,
    ledger_fault: Optional[Callable[[Decimal], Decimal]] = None,
) -> World:
    clock = Clock()
    now = clock.peek()
    price = PRICING[product]
    if product == PRODUCT_LC_CONFIRMATION and beneficiary_country is None:
        beneficiary_country = "AE"

    keys = {k: KeyPair.generate() for k in (BANK, ACME, HARBOR, BUYER, SELLER, ROGUE)}
    registry = KYARegistry()
    kyb_until = now + timedelta(days=365)
    registry.register_principal(Principal(ACME, "Acme Exports Pvt Ltd", "IN", keys[ACME].public_hex, ACME_ACCT, True, kyb_until))
    registry.register_principal(Principal(HARBOR, "Harbor Capital Ltd", "GB", keys[HARBOR].public_hex, HARBOR_ACCT, True, kyb_until))
    cred_until = now + timedelta(days=90)
    caps = (PRODUCT_FX_FORWARD, PRODUCT_LC_CONFIRMATION)
    registry.register_agent(AgentRecord(BUYER, ACME, "in-house treasury platform", ACME_OWNER,
                                        keys[BUYER].public_hex, buyer_tier, cred_until, caps))
    registry.register_agent(AgentRecord(SELLER, HARBOR, "harbor-markets-platform", HARBOR_OWNER,
                                        keys[SELLER].public_hex, seller_tier, cred_until, caps))

    ledger = Ledger(fault=ledger_fault)
    ledger.open_account(ACME_ACCT, "USD", ACME_OPENING_BALANCE)
    ledger.open_account(HARBOR_ACCT, "USD", Decimal("0"))
    audit = AuditLog(keys[BANK], clock)
    gateway = TrustGateway(operator=BANK, registry=registry, ledger=ledger, audit=audit, policy=Policy(),
                           clock=clock, mode=mode, approver=approver)

    valid_from, valid_until = now - timedelta(days=1), now + timedelta(days=30)
    buy_mandate = Mandate(
        mandate_id=f"MND-{BUYER}", principal_id=ACME, agent_id=BUYER, side="buy",
        valid_from=valid_from, valid_until=valid_until,
        products=caps, instruments=("USD/INR", "LC"), currency="USD",
        max_notional=Decimal("2000000"), aggregate_cap=Decimal("5000000"),
        price_limit_bps={PRODUCT_FX_FORWARD: Decimal("60"), PRODUCT_LC_CONFIRMATION: Decimal("150")},
        max_tenor_days=180, counterparties=(SELLER,), approval_threshold=Decimal("1000000"), nonce="n-buy-1",
    )
    sell_mandate = Mandate(
        mandate_id=f"MND-{SELLER}", principal_id=HARBOR, agent_id=SELLER, side="sell",
        valid_from=valid_from, valid_until=valid_until,
        products=caps, instruments=("USD/INR", "LC"), currency="USD",
        max_notional=Decimal("5000000"), aggregate_cap=Decimal("20000000"),
        price_limit_bps={PRODUCT_FX_FORWARD: Decimal("40"), PRODUCT_LC_CONFIRMATION: Decimal("90")},
        max_tenor_days=360, counterparties=(BUYER,), approval_threshold=Decimal("3000000"), nonce="n-sell-1",
    )
    if buyer_overrides:
        buy_mandate = replace(buy_mandate, **buyer_overrides)
    if seller_overrides:
        sell_mandate = replace(sell_mandate, **seller_overrides)

    signed_buy = mandate_mod.issue(buy_mandate, keys[ACME])
    signed_sell = mandate_mod.issue(sell_mandate, keys[HARBOR])
    world_notes: List[str] = []
    registration_errors: Dict[str, tuple] = {}
    if tamper_buyer_mandate:
        # Attacker edits the signed mandate to raise the price ceiling and the cap,
        # keeping the original signature, then asks the rail to accept it.
        forged = replace(
            signed_buy.mandate,
            price_limit_bps={PRODUCT_FX_FORWARD: Decimal("999"), PRODUCT_LC_CONFIRMATION: Decimal("999")},
            aggregate_cap=Decimal("999999999"),
        )
        signed_buy = SignedMandate(forged, signed_buy.signature)
    for signed in (signed_buy, signed_sell):
        try:
            gateway.register_mandate(signed)
        except GatewayDenied as exc:
            registration_errors[signed.mandate.agent_id] = exc.codes
            world_notes.append(f"mandate for {signed.mandate.agent_id} refused: {', '.join(exc.codes)}")

    template = Terms(product, price["instrument"], "USD", Decimal(notional), Decimal(price["buy_open"]),
                     tenor_days, beneficiary_country if product == PRODUCT_LC_CONFIRMATION else None)
    buyer = Agent(BUYER, keys[BUYER], "buy", buyer_strategy or default_strategy(), signed_buy,
                  Brief(Decimal(price["buy_open"]), template), clock)
    seller = Agent(SELLER, keys[SELLER], "sell", seller_strategy or default_strategy(), signed_sell,
                   Brief(Decimal(price["sell_open"]), None), clock)

    directory = {
        SELLER: AgentCard(
            agent_id=SELLER, name="Harbor Capital pricing desk", operator="harbor-markets-platform",
            protocol="a2a-sim/0.1",
            skills=(
                CatalogEntry(PRODUCT_FX_FORWARD, ("USD/INR",), "USD", Decimal("100000"), Decimal("5000000"), 360,
                             "bps spread over forward mid, one-off"),
                CatalogEntry(PRODUCT_LC_CONFIRMATION, ("LC",), "USD", Decimal("100000"), Decimal("5000000"), 360,
                             "bps per annum, pro rata, 360-day basis"),
            ),
        )
    }
    return World(clock, registry, ledger, audit, gateway, keys,
                 {BUYER: buyer, SELLER: seller}, {BUYER: signed_buy, SELLER: signed_sell},
                 directory, template, world_notes, registration_errors)


def rogue_agent(world: World) -> Agent:
    """An agent that was never onboarded. Valid keys, no KYA record."""
    template = world.brief_terms
    signed = world.mandates[BUYER]
    return Agent(ROGUE, world.keys[ROGUE], "buy", RuleBasedStrategy(), signed,
                 Brief(Decimal("30"), template), world.clock)
