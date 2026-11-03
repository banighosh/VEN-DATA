"""The trust gateway: the cross-company rail the POV argues a bank should own.

Every control lives here, in code, outside any agent:

  1. Know Your Agent on every message and again at settlement
  2. Signed-message check (who really sent this, and is it a replay)
  3. Pre-trade guardrails against the sender's own signed mandate
  4. Bank rules (jurisdiction screen, price sanity band)
  5. Autonomy tiers, named human approval, shadow mode
  6. Idempotent settlement and post-settlement reconciliation
  7. Kill switch, including an automatic trip on a reconciliation break
  8. A hash-chained, signed audit trail of all of the above

Agents (rule-based, injectable or LLM-backed) only ever see messages. They
cannot widen their own mandate, skip a check or write the log.
"""
from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Sequence, Set

from . import crypto
from . import mandate as mandate_mod
from .audit import AuditLog
from .clock import Clock
from .kya import KYARegistry, Status, Tier
from .ledger import Ledger, LedgerError
from .mandate import Mandate, SignedMandate
from .models import Deal, Message
from .negotiation import (
    AGREED,
    DENIED,
    EXECUTED,
    EXPIRED,
    FINAL_EXECUTION_STATUSES,
    OPEN,
    PENDING_APPROVAL,
    RECON_BREAK,
    REJECTED,
    REJECTED_BY_HUMAN,
    SETTLEMENT_FAILED,
    SHADOW_LOGGED,
    TERMINATED,
    ApprovalDecision,
    ApprovalRequest,
    ExecutionResult,
    Negotiation,
)
from .policy import DENY, Policy, PolicyResult, Violation
from .reconcile import reconcile


class Mode(str, Enum):
    LIVE = "live"
    SHADOW = "shadow"  # evaluate and log everything, move no money


class GatewayDenied(Exception):
    def __init__(self, codes: Sequence[str], detail: str = "") -> None:
        self.codes = tuple(dict.fromkeys(codes))
        self.detail = detail
        super().__init__(", ".join(self.codes))


class RelayResult:
    def __init__(self, delivered: bool, terminated: bool = False, codes: Sequence[str] = (), detail: str = "") -> None:
        self.delivered = delivered
        self.terminated = terminated
        self.codes = tuple(codes)
        self.detail = detail


Approver = Callable[[ApprovalRequest], ApprovalDecision]


def _j(value: Any) -> Any:
    """Make audit payloads JSON-safe."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _j(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_j(v) for v in value]
    return value


def _unique(codes: Sequence[str]) -> List[str]:
    return list(dict.fromkeys(codes))


class TrustGateway:
    def __init__(
        self,
        *,
        operator: str,
        registry: KYARegistry,
        ledger: Ledger,
        audit: AuditLog,
        policy: Policy,
        clock: Clock,
        mode: Mode = Mode.LIVE,
        approver: Optional[Approver] = None,
        max_turns: int = 5,
    ) -> None:
        self.operator = operator
        self.registry = registry
        self.ledger = ledger
        self.audit = audit
        self.policy = policy
        self.clock = clock
        self.mode = mode
        self.approver = approver
        self.max_turns = max_turns
        self.halted = False
        self.halt_reason = ""
        self._negotiations: Dict[str, Negotiation] = {}
        self._mandates: Dict[str, SignedMandate] = {}
        self._revoked_mandates: Set[str] = set()
        self._usage: Dict[str, Decimal] = {}
        self._seen: Set[str] = set()

    # ------------------------------------------------------------------ audit
    def _log(self, event: str, actor: str, **data: Any) -> None:
        self.audit.append(event, actor, _j(data))

    # --------------------------------------------------------------- accessors
    def get_negotiation(self, negotiation_id: str) -> Negotiation:
        return self._negotiations[negotiation_id]

    def usage(self, mandate_id: str) -> Decimal:
        return self._usage.get(mandate_id, Decimal("0"))

    # --------------------------------------------------------------- operations
    def halt(self, reason: str, by: str) -> None:
        self.halted = True
        self.halt_reason = reason
        self._log("kill_switch_engaged", by, reason=reason)

    def resume(self, by: str) -> None:
        self.halted = False
        self._log("kill_switch_released", by, previous_reason=self.halt_reason)
        self.halt_reason = ""

    def revoke_agent(self, agent_id: str, reason: str, by: str) -> None:
        self.registry.set_status(agent_id, Status.REVOKED)
        self._log("agent_revoked", by, agent_id=agent_id, reason=reason)

    def suspend_agent(self, agent_id: str, reason: str, by: str) -> None:
        self.registry.set_status(agent_id, Status.SUSPENDED)
        self._log("agent_suspended", by, agent_id=agent_id, reason=reason)

    def revoke_mandate(self, mandate_id: str, reason: str, by: str) -> None:
        self._revoked_mandates.add(mandate_id)
        self._log("mandate_revoked", by, mandate_id=mandate_id, reason=reason)

    # ---------------------------------------------------------------- mandates
    def register_mandate(self, signed: SignedMandate) -> None:
        m = signed.mandate
        rec = self.registry.get_agent(m.agent_id)
        principal = self.registry.get_principal(m.principal_id)
        codes: List[str] = []
        if rec is None:
            codes.append("UNKNOWN_AGENT")
        elif rec.principal_id != m.principal_id:
            codes.append("MANDATE_PRINCIPAL_MISMATCH")
        if principal is None:
            codes.append("PRINCIPAL_UNKNOWN")
        elif not mandate_mod.verify_signature(signed, principal.public_key):
            codes.append("MANDATE_SIGNATURE_INVALID")
        if codes:
            self._log("mandate_rejected", m.principal_id, mandate_id=m.mandate_id, agent_id=m.agent_id, codes=codes)
            raise GatewayDenied(codes)
        self._mandates[m.agent_id] = signed
        self._log(
            "mandate_registered",
            m.principal_id,
            mandate_id=m.mandate_id,
            agent_id=m.agent_id,
            side=m.side,
            mandate_hash=crypto.digest(m.payload()),
        )

    def _mandate_for(self, agent_id: str) -> "tuple[Optional[Mandate], List[str]]":
        """Fetch and re-verify the agent's mandate. Done on every use, so a
        tampered or revoked mandate is caught even after registration."""
        signed = self._mandates.get(agent_id)
        if signed is None:
            return None, ["MANDATE_MISSING"]
        if signed.mandate.mandate_id in self._revoked_mandates:
            return None, ["MANDATE_REVOKED"]
        principal = self.registry.get_principal(signed.mandate.principal_id)
        if principal is None or not mandate_mod.verify_signature(signed, principal.public_key):
            return None, ["MANDATE_SIGNATURE_INVALID"]
        return signed.mandate, []

    # ------------------------------------------------------------- negotiation
    def open_negotiation(self, buyer_id: str, seller_id: str, product: str, instrument: str) -> Negotiation:
        now = self.clock.now()
        codes: List[str] = []
        if self.halted:
            codes.append("KILL_SWITCH_ACTIVE")
        if buyer_id == seller_id:
            codes.append("SELF_DEALING")
        for aid in (buyer_id, seller_id):
            res = self.registry.verify_agent(aid, now)
            if not res.ok:
                codes.append(res.code)
        if codes:
            self._log("negotiation_refused", self.operator, buyer=buyer_id, seller=seller_id, codes=_unique(codes))
            raise GatewayDenied(codes)
        neg_id = f"NEG-{len(self._negotiations) + 1:03d}"
        neg = Negotiation(neg_id, buyer_id, seller_id, product, instrument, max_messages=2 * self.max_turns)
        self._negotiations[neg_id] = neg
        self._log("negotiation_opened", self.operator, negotiation_id=neg_id, buyer=buyer_id, seller=seller_id,
                  product=product, instrument=instrument)
        return neg

    def relay(self, msg: Message) -> RelayResult:
        now = self.clock.now()
        neg = self._negotiations.get(msg.negotiation_id)
        if neg is None:
            return RelayResult(False, False, ["UNKNOWN_NEGOTIATION"])

        def reject(codes: Sequence[str], terminal: bool = False, detail: str = "") -> RelayResult:
            codes = _unique(codes)
            self._log("message_blocked", msg.sender, negotiation_id=neg.negotiation_id, msg_id=msg.msg_id,
                      kind=msg.kind, codes=codes, terminal=terminal, detail=detail)
            neg.blocked.append({"msg_id": msg.msg_id, "sender": msg.sender, "kind": msg.kind,
                                "codes": codes, "terminal": terminal,
                                "price_bps": str(msg.terms.price_bps) if msg.terms else None})
            if terminal and neg.status == OPEN:
                neg.status = TERMINATED
                neg.block_codes = tuple(codes)
            return RelayResult(False, terminal, codes, detail)

        # 1. Authenticate before changing any state. Unauthenticated input never
        #    consumes message ids or ends someone else's negotiation.
        if msg.sender not in (neg.buyer, neg.seller):
            return reject(["NOT_A_PARTY"])
        rec = self.registry.get_agent(msg.sender)
        if rec is None or not crypto.verify(rec.public_key, msg.signing_payload(), msg.signature):
            return reject(["BAD_SIGNATURE"])
        if msg.msg_id in self._seen:
            return reject(["REPLAYED_MESSAGE"])
        self._seen.add(msg.msg_id)

        # 2. Rail-level state
        if neg.status != OPEN:
            return reject(["NEGOTIATION_CLOSED"])
        if self.halted:
            return reject(["KILL_SWITCH_ACTIVE"], terminal=True, detail=self.halt_reason)
        for aid in (neg.buyer, neg.seller):  # both parties, every message
            kya = self.registry.verify_agent(aid, now)
            if not kya.ok:
                return reject([kya.code], terminal=True, detail=aid)

        # 3. Protocol shape
        expected = neg.buyer if len(neg.messages) % 2 == 0 else neg.seller
        if msg.sender != expected:
            return reject(["OUT_OF_TURN"])
        if msg.seq != len(neg.messages):
            return reject(["BAD_SEQUENCE"])
        if msg.kind not in ("offer", "counter", "accept", "reject"):
            return reject(["BAD_KIND"])
        if (not neg.messages) != (msg.kind == "offer"):
            return reject(["BAD_OPENING" if not neg.messages else "UNEXPECTED_OFFER"])

        if msg.kind == "reject":
            neg.messages.append(msg)
            neg.status = REJECTED
            self._log("message_relayed", msg.sender, negotiation_id=neg.negotiation_id, msg_id=msg.msg_id,
                      kind="reject", text=msg.text[:200])
            return RelayResult(True)

        terms = msg.terms
        if terms is None:
            return reject(["MISSING_TERMS"])
        if terms.product != neg.product or terms.instrument != neg.instrument:
            return reject(["TERMS_MISMATCH"])
        if msg.kind == "accept":
            out = neg.outstanding
            if out is None or out.sender == msg.sender or out.terms is None:
                return reject(["NOTHING_TO_ACCEPT"])
            if msg.ref_terms_hash != out.terms.digest() or terms.digest() != out.terms.digest():
                return reject(["ACCEPT_TERMS_MISMATCH"], terminal=True)

        # 4. Pre-trade guardrails: the sender's own signed mandate plus bank rules
        side = "buy" if msg.sender == neg.buyer else "sell"
        counterparty = neg.seller if side == "buy" else neg.buyer
        mandate, mcodes = self._mandate_for(msg.sender)
        codes: List[str] = list(mcodes)
        if mandate is not None:
            res = self.policy.check_side(
                agent_id=msg.sender, side=side, mandate=mandate, terms=terms, counterparty_id=counterparty,
                used=self.usage(mandate.mandate_id), now=now, tier=rec.tier,
            )
            codes += list(res.codes)
        codes += [v.code for v in self.policy.check_bank_rules(terms)]
        if codes:
            return reject(codes, terminal=True)

        # 5. Deliver
        neg.messages.append(msg)
        if msg.kind in ("offer", "counter"):
            neg.outstanding = msg
        self._log("message_relayed", msg.sender, negotiation_id=neg.negotiation_id, msg_id=msg.msg_id,
                  kind=msg.kind, price_bps=terms.price_bps, terms_hash=terms.digest(), text=msg.text[:200])
        if msg.kind == "accept":
            offer = neg.outstanding
            assert offer is not None
            deal_id = "DL-" + crypto.digest({"n": neg.negotiation_id, "t": terms.digest()})[:10].upper()
            neg.agreed = Deal(deal_id, neg.negotiation_id, neg.buyer, neg.seller, terms, offer, msg, now.isoformat())
            neg.status = AGREED
            self._log("deal_agreed", self.operator, negotiation_id=neg.negotiation_id, deal_id=deal_id,
                      terms_hash=terms.digest(), offer_msg=offer.msg_id, accept_msg=msg.msg_id)
        elif len(neg.messages) >= neg.max_messages:
            neg.status = EXPIRED
            self._log("negotiation_expired", self.operator, negotiation_id=neg.negotiation_id)
        return RelayResult(True)

    # --------------------------------------------------------------- evidence
    def verify_deal_evidence(self, deal: Deal) -> bool:
        """Both signatures verify against the registered keys and bind the same terms."""
        for m in (deal.offer, deal.accept):
            rec = self.registry.get_agent(m.sender)
            if rec is None or not crypto.verify(rec.public_key, m.signing_payload(), m.signature):
                return False
        if deal.offer.terms is None:
            return False
        h = deal.offer.terms.digest()
        return deal.accept.ref_terms_hash == h == deal.terms.digest() and deal.offer.sender != deal.accept.sender

    # --------------------------------------------------------------- execution
    def _finish(self, neg: Negotiation, status: str, codes: Sequence[str] = (), **kw: Any) -> ExecutionResult:
        res = ExecutionResult(status=status, codes=tuple(_unique(codes)),
                              deal_id=neg.agreed.deal_id if neg.agreed else None, **kw)
        neg.execution = res
        neg.status = status
        self._log("execution_result", self.operator, negotiation_id=neg.negotiation_id, deal_id=res.deal_id,
                  status=status, codes=list(res.codes), posting_id=res.posting_id, shadow_outcome=res.shadow_outcome,
                  pending=list(res.pending_approvals))
        return res

    def _evaluate_deal(self, neg: Negotiation, now) -> PolicyResult:
        deal = neg.agreed
        assert deal is not None
        result = PolicyResult()
        for agent_id, side, cp in ((deal.buyer, "buy", deal.seller), (deal.seller, "sell", deal.buyer)):
            mandate, mcodes = self._mandate_for(agent_id)
            if mandate is None:
                result.violations += [Violation(c, agent_id) for c in mcodes]
                continue
            rec = self.registry.get_agent(agent_id)
            assert rec is not None
            result.extend(self.policy.check_side(
                agent_id=agent_id, side=side, mandate=mandate, terms=deal.terms, counterparty_id=cp,
                used=self.usage(mandate.mandate_id), now=now, tier=rec.tier,
            ))
        result.violations += self.policy.check_bank_rules(deal.terms)
        return result

    def _record_approval(self, neg: Negotiation, agent_id: str, decision: ApprovalDecision) -> Optional[str]:
        rec = self.registry.get_agent(agent_id)
        if rec is None or decision.approver_id != rec.human_owner:
            self._log("approval_refused", decision.approver_id, negotiation_id=neg.negotiation_id,
                      agent_id=agent_id, reason="APPROVER_NOT_AUTHORISED")
            return "APPROVER_NOT_AUTHORISED"
        neg.approvals[agent_id] = decision
        self._log("approval_recorded", decision.approver_id, negotiation_id=neg.negotiation_id,
                  agent_id=agent_id, approved=decision.approved, note=decision.note)
        return None

    def resolve_approval(self, negotiation_id: str, agent_id: str, decision: ApprovalDecision) -> ExecutionResult:
        """Deliver a human decision for a pending approval, then re-run execution
        in full so every other control is checked again at the moment of release."""
        neg = self._negotiations[negotiation_id]
        if neg.status != PENDING_APPROVAL:
            return neg.execution or self._finish(neg, DENIED, ["NO_PENDING_APPROVAL"])
        code = self._record_approval(neg, agent_id, decision)
        if code:
            # An unauthorised person cannot approve, and cannot kill the deal either:
            # it stays pending for the real owner.
            current = neg.execution
            assert current is not None
            return ExecutionResult(PENDING_APPROVAL, (code,), current.deal_id,
                                   pending_approvals=current.pending_approvals)
        return self.execute(negotiation_id)

    def execute(self, negotiation_id: str) -> ExecutionResult:
        neg = self._negotiations[negotiation_id]
        if neg.execution is not None and neg.status in FINAL_EXECUTION_STATUSES:
            return neg.execution  # idempotent: executing twice never settles twice
        if neg.status not in (AGREED, PENDING_APPROVAL) or neg.agreed is None:
            self._log("execution_refused", self.operator, negotiation_id=negotiation_id, status=neg.status,
                      codes=["NO_AGREED_DEAL"])
            return ExecutionResult(DENIED, ("NO_AGREED_DEAL",))
        deal = neg.agreed
        now = self.clock.now()

        if self.halted:
            return self._finish(neg, DENIED, ["KILL_SWITCH_ACTIVE"])

        kya_codes = [r.code for r in (self.registry.verify_agent(a, now) for a in (deal.buyer, deal.seller)) if not r.ok]
        if kya_codes:
            return self._finish(neg, DENIED, kya_codes)

        policy_result = self._evaluate_deal(neg, now)
        buyer_rec = self.registry.get_agent(deal.buyer)
        seller_rec = self.registry.get_agent(deal.seller)
        assert buyer_rec and seller_rec

        shadow = self.mode is Mode.SHADOW or Tier.SHADOW in (buyer_rec.tier, seller_rec.tier)
        if shadow:
            return self._finish(neg, SHADOW_LOGGED, policy_result.codes, shadow_outcome=policy_result.outcome)
        if policy_result.outcome == DENY:
            return self._finish(neg, DENIED, policy_result.codes)

        # Named human approval (per agent, by that agent's own owner)
        required: Dict[str, List[str]] = {}
        for req in policy_result.approvals:
            required.setdefault(req.agent_id, []).append(req.reason)
        pending: List[str] = []
        for agent_id, reasons in required.items():
            if agent_id in neg.approvals:
                continue
            if self.approver is None:
                pending.append(agent_id)
                continue
            owner = self.registry.get_agent(agent_id).human_owner  # type: ignore[union-attr]
            request = ApprovalRequest(
                deal_id=deal.deal_id, agent_id=agent_id, owner=owner, reasons=tuple(reasons),
                summary={"product": deal.terms.product, "notional": f"{deal.terms.notional} {deal.terms.currency}",
                         "price_bps": str(deal.terms.price_bps), "cost": str(deal.terms.cost())},
            )
            self._log("approval_requested", self.operator, negotiation_id=neg.negotiation_id, agent_id=agent_id,
                      owner=owner, reasons=reasons)
            code = self._record_approval(neg, agent_id, self.approver(request))
            if code:
                return self._finish(neg, DENIED, [code])
        if pending:
            for agent_id in pending:
                self._log("approval_requested", self.operator, negotiation_id=neg.negotiation_id, agent_id=agent_id,
                          owner=self.registry.get_agent(agent_id).human_owner, reasons=required[agent_id])  # type: ignore[union-attr]
            return self._finish(neg, PENDING_APPROVAL, ["HUMAN_APPROVAL_REQUIRED"], pending_approvals=tuple(pending))
        if any(not d.approved for d in neg.approvals.values()):
            return self._finish(neg, REJECTED_BY_HUMAN, ["HUMAN_REJECTED"])

        # Settlement
        buyer_p = self.registry.get_principal(buyer_rec.principal_id)
        seller_p = self.registry.get_principal(seller_rec.principal_id)
        assert buyer_p and seller_p
        src, dst, cost = buyer_p.settlement_account, seller_p.settlement_account, deal.terms.cost()
        self._log("settlement_instruction", self.operator, negotiation_id=neg.negotiation_id, deal_id=deal.deal_id,
                  src=src, dst=dst, amount=cost, currency=deal.terms.currency)
        try:
            posting = self.ledger.transfer(idem_key=deal.deal_id, src=src, dst=dst, amount=cost,
                                           currency=deal.terms.currency, ref=deal.deal_id, ts=self.clock.now())
        except LedgerError as exc:
            return self._finish(neg, SETTLEMENT_FAILED, [exc.code])
        for aid in (deal.buyer, deal.seller):
            mandate, _ = self._mandate_for(aid)
            if mandate is not None:
                self._usage[mandate.mandate_id] = self.usage(mandate.mandate_id) + deal.terms.notional
        self._log("settlement_posted", self.operator, deal_id=deal.deal_id, posting_id=posting.posting_id,
                  amount=posting.amount)

        recon = reconcile(deal, src, dst, self.ledger.postings_for(deal.deal_id))
        self._log("reconciliation", self.operator, deal_id=deal.deal_id, matched=recon.matched,
                  expected=recon.expected, actual=recon.actual, breaks=[b.code for b in recon.breaks])
        if not recon.matched:
            self.halt(f"RECON_BREAK {deal.deal_id}: " + ", ".join(b.code for b in recon.breaks), by="gateway:auto")
            return self._finish(neg, RECON_BREAK, [b.code for b in recon.breaks], posting_id=posting.posting_id,
                                reconciliation=recon)
        return self._finish(neg, EXECUTED, [], posting_id=posting.posting_id, reconciliation=recon)
