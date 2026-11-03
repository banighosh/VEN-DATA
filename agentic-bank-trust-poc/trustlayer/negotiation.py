"""Negotiation state held by the gateway, plus the loop that drives two agents."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple

from .models import Deal, Message
from .reconcile import ReconResult

if TYPE_CHECKING:  # pragma: no cover
    from .agents import Agent
    from .gateway import TrustGateway

# Negotiation phase
OPEN = "OPEN"
AGREED = "AGREED"
REJECTED = "REJECTED"  # a party walked away
TERMINATED = "TERMINATED"  # the rail cut it off (authority, identity or policy failure)
EXPIRED = "EXPIRED"  # message budget used up without agreement

# Execution phase (the negotiation's status becomes one of these after execute())
EXECUTED = "EXECUTED"
DENIED = "DENIED"
PENDING_APPROVAL = "PENDING_APPROVAL"
REJECTED_BY_HUMAN = "REJECTED_BY_HUMAN"
SHADOW_LOGGED = "SHADOW_LOGGED"
RECON_BREAK = "RECON_BREAK"
SETTLEMENT_FAILED = "SETTLEMENT_FAILED"

FINAL_EXECUTION_STATUSES = frozenset(
    {EXECUTED, DENIED, REJECTED_BY_HUMAN, SHADOW_LOGGED, RECON_BREAK, SETTLEMENT_FAILED}
)


@dataclass(frozen=True)
class ApprovalRequest:
    deal_id: str
    agent_id: str
    owner: str  # the named human who must approve
    reasons: Tuple[str, ...]
    summary: Dict[str, str]


@dataclass(frozen=True)
class ApprovalDecision:
    approved: bool
    approver_id: str
    note: str = ""


@dataclass
class ExecutionResult:
    status: str
    codes: Tuple[str, ...] = ()
    deal_id: Optional[str] = None
    posting_id: Optional[str] = None
    reconciliation: Optional[ReconResult] = None
    shadow_outcome: Optional[str] = None
    pending_approvals: Tuple[str, ...] = ()


@dataclass
class Negotiation:
    negotiation_id: str
    buyer: str
    seller: str
    product: str
    instrument: str
    max_messages: int
    status: str = OPEN
    messages: List[Message] = field(default_factory=list)
    blocked: List[dict] = field(default_factory=list)
    outstanding: Optional[Message] = None
    agreed: Optional[Deal] = None
    block_codes: Tuple[str, ...] = ()
    approvals: Dict[str, ApprovalDecision] = field(default_factory=dict)
    execution: Optional[ExecutionResult] = None


def run_negotiation(
    gateway: "TrustGateway",
    buyer: "Agent",
    seller: "Agent",
    *,
    hook: Optional[Callable[[Message, Negotiation], None]] = None,
) -> Negotiation:
    """Alternate turns, buyer first, until the rail or a party ends it.

    Raises GatewayDenied if the negotiation cannot even be opened (unknown or
    revoked agent, kill switch). `hook` runs after each delivered message so a
    scenario can inject events (for example, revoke an agent mid-negotiation).
    """
    template = buyer.brief.template
    assert template is not None, "buyer needs a brief with a terms template"
    neg = gateway.open_negotiation(buyer.agent_id, seller.agent_id, template.product, template.instrument)
    speaker, listener = buyer, seller
    incoming: Optional[Message] = None
    guard = 0
    while neg.status == OPEN and guard < neg.max_messages + 2:
        guard += 1
        msg = speaker.respond(neg.negotiation_id, incoming, seq=len(neg.messages))
        result = gateway.relay(msg)
        if not result.delivered:
            break  # blocked: a misbehaving or unauthorised agent does not get a retry loop
        incoming = msg
        if hook is not None:
            hook(msg, neg)
        speaker, listener = listener, speaker
    return neg
