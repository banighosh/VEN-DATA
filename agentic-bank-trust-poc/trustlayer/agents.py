"""Agents: a keypair, a signed mandate, a brief and a strategy.

Agent Cards are a simplified, A2A-inspired capability descriptor: enough to show
machine-readable discovery of a bank-style product catalogue, not a wire-compatible
implementation of the A2A specification.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from . import crypto
from .clock import Clock
from .kya import KYARegistry
from .mandate import SignedMandate
from .models import Message, Terms
from .strategies import Action, DecisionContext, Strategy


@dataclass(frozen=True)
class CatalogEntry:
    product: str
    instruments: Tuple[str, ...]
    currency: str
    min_notional: Decimal
    max_notional: Decimal
    max_tenor_days: int
    price_unit: str


@dataclass(frozen=True)
class AgentCard:
    agent_id: str
    name: str
    operator: str
    protocol: str
    skills: Tuple[CatalogEntry, ...]

    def offers(self, product: str, instrument: str) -> bool:
        return any(s.product == product and instrument in s.instruments for s in self.skills)


def discover(
    directory: Dict[str, AgentCard], registry: KYARegistry, product: str, instrument: str, now
) -> List[AgentCard]:
    """Find counterparties that publish the product and currently pass KYA."""
    return [
        card for card in directory.values()
        if card.offers(product, instrument) and registry.verify_agent(card.agent_id, now).ok
    ]


@dataclass(frozen=True)
class Brief:
    """What the agent was asked to get done."""

    opening_bps: Decimal
    template: Optional[Terms] = None  # buyer: the deal it wants; seller: None
    max_turns: int = 5


class Agent:
    def __init__(
        self,
        agent_id: str,
        keys: crypto.KeyPair,
        side: str,
        strategy: Strategy,
        mandate: SignedMandate,
        brief: Brief,
        clock: Clock,
    ) -> None:
        self.agent_id = agent_id
        self.keys = keys
        self.side = side
        self.strategy = strategy
        self.mandate = mandate
        self.brief = brief
        self.clock = clock
        self._turns = 0
        self.decisions: List[Tuple[int, str, str]] = []

    def reset(self) -> None:
        """Start a fresh negotiation (turn counter back to zero)."""
        self._turns = 0
        self.decisions = []

    def limit_for(self, product: str) -> Decimal:
        """Price limit from this agent's own mandate for the product being negotiated."""
        return self.mandate.mandate.price_limit_bps[product]

    def _product(self, incoming: Optional[Message]) -> str:
        if self.brief.template is not None:
            return self.brief.template.product
        assert incoming is not None and incoming.terms is not None, "a seller learns the product from the buyer's offer"
        return incoming.terms.product

    def respond(self, negotiation_id: str, incoming: Optional[Message], seq: int) -> Message:
        product = self._product(incoming)
        ctx = DecisionContext(
            side=self.side,
            turn=self._turns,
            max_turns=self.brief.max_turns,
            limit_bps=self.limit_for(product),
            opening_bps=self.brief.opening_bps,
            incoming=incoming,
        )
        action = self.strategy.decide(ctx)
        action = self._sanity(action, incoming, ctx.limit_bps)
        self._turns += 1
        self.decisions.append((ctx.turn, action.kind, str(action.price_bps) if action.price_bps is not None else "-"))
        return self._build(negotiation_id, incoming, seq, action)

    def _sanity(self, action: Action, incoming: Optional[Message], limit_bps: Decimal) -> Action:
        """Agent-side hygiene only (not a security control): a buyer will not
        accept terms that differ from its brief in anything but price."""
        if action.kind == "accept" and self.side == "buy" and self.brief.template and incoming and incoming.terms:
            if not incoming.terms.same_except_price(self.brief.template):
                return Action("counter", limit_bps, "Non-price terms differ from my request.")
        return action

    def _build(self, negotiation_id: str, incoming: Optional[Message], seq: int, action: Action) -> Message:
        now = self.clock.now().isoformat()
        msg_id = f"{negotiation_id}:{seq}:{self.agent_id}"
        terms: Optional[Terms] = None
        ref: Optional[str] = None
        if action.kind == "accept":
            assert incoming is not None and incoming.terms is not None
            terms, ref, kind = incoming.terms, incoming.terms.digest(), "accept"
        elif action.kind == "reject":
            kind = "reject"
        else:
            assert action.price_bps is not None
            base = self.brief.template if self.brief.template else (incoming.terms if incoming else None)
            assert base is not None, "seller cannot open a negotiation"
            terms = base.with_price(action.price_bps)
            kind = "offer" if incoming is None else "counter"
        unsigned = Message(msg_id, negotiation_id, self.agent_id, kind, seq, terms, action.text, ref, now)
        return Message(**{**unsigned.__dict__, "signature": self.keys.sign(unsigned.signing_payload())})
