from decimal import Decimal

import pytest

from conftest import fx_terms, make_message
from trustlayer.gateway import GatewayDenied, Mode
from trustlayer.kya import Tier
from trustlayer.negotiation import (
    DENIED, EXECUTED, EXPIRED, OPEN, PENDING_APPROVAL, SETTLEMENT_FAILED, SHADOW_LOGGED, TERMINATED,
    ApprovalDecision, run_negotiation,
)
from trustlayer.strategies import Action
from trustlayer.world import ACME_ACCT, ACME_OWNER, BUYER, ROGUE, SELLER, build_world


def _open(w):
    return w.gateway.open_negotiation(BUYER, SELLER, "fx_forward", "USD/INR")


def _agreed(**kw):
    w = build_world(**kw)
    return w, run_negotiation(w.gateway, w.buyer, w.seller)


# ---- relay protocol
def test_out_of_turn_message_is_refused_without_ending_the_talks():
    w = build_world(); neg = _open(w)
    r = w.gateway.relay(make_message(w, SELLER, neg.negotiation_id, "counter", 0, fx_terms("70")))
    assert r.codes == ("OUT_OF_TURN",) and not r.terminated and neg.status == OPEN


def test_stranger_cannot_inject_or_end_a_negotiation():
    w = build_world(); neg = _open(w)
    r = w.gateway.relay(make_message(w, ROGUE, neg.negotiation_id, "offer", 0, fx_terms()))
    assert r.codes == ("NOT_A_PARTY",) and neg.status == OPEN and not neg.messages


def test_impersonation_with_wrong_key_is_refused_and_harmless():
    w = build_world(); neg = _open(w)
    forged = make_message(w, BUYER, neg.negotiation_id, "offer", 0, fx_terms(), key_of=ROGUE)
    r = w.gateway.relay(forged)
    assert r.codes == ("BAD_SIGNATURE",) and neg.status == OPEN
    # the real buyer can still open: the forged message id was not burned
    ok = make_message(w, BUYER, neg.negotiation_id, "offer", 0, fx_terms())
    assert w.gateway.relay(ok).delivered


def test_replayed_message_refused():
    w = build_world(); neg = _open(w)
    msg = make_message(w, BUYER, neg.negotiation_id, "offer", 0, fx_terms())
    assert w.gateway.relay(msg).delivered
    assert w.gateway.relay(msg).codes == ("REPLAYED_MESSAGE",)
    assert len(neg.messages) == 1


def test_tampered_message_body_fails_signature():
    w = build_world(); neg = _open(w)
    msg = make_message(w, BUYER, neg.negotiation_id, "offer", 0, fx_terms("30"))
    tampered = type(msg)(**{**msg.__dict__, "terms": fx_terms("5")})
    assert w.gateway.relay(tampered).codes == ("BAD_SIGNATURE",)


def test_first_message_must_be_an_offer_and_later_ones_must_not():
    w = build_world(); neg = _open(w)
    assert w.gateway.relay(make_message(w, BUYER, neg.negotiation_id, "counter", 0, fx_terms())).codes == ("BAD_OPENING",)
    assert w.gateway.relay(make_message(w, BUYER, neg.negotiation_id, "offer", 0, fx_terms(), tag="retry")).delivered
    r = w.gateway.relay(make_message(w, SELLER, neg.negotiation_id, "offer", 1, fx_terms("70")))
    assert r.codes == ("UNEXPECTED_OFFER",)


def test_bad_sequence_number_refused():
    w = build_world(); neg = _open(w)
    assert w.gateway.relay(make_message(w, BUYER, neg.negotiation_id, "offer", 5, fx_terms())).codes == ("BAD_SEQUENCE",)


@pytest.mark.parametrize("accepted_price,ref_price,ref_override", [
    ("55", "45", None),          # accepts different terms than were offered, ref points at the real offer
    ("45", "45", "deadbeef"),    # right terms, wrong hash
])
def test_bait_and_switch_on_acceptance_terminates(accepted_price, ref_price, ref_override):
    w = build_world(); neg = _open(w)
    w.gateway.relay(make_message(w, BUYER, neg.negotiation_id, "offer", 0, fx_terms("45")))
    ref = ref_override or fx_terms(ref_price).digest()
    r = w.gateway.relay(make_message(w, SELLER, neg.negotiation_id, "accept", 1, fx_terms(accepted_price), ref=ref))
    assert r.codes == ("ACCEPT_TERMS_MISMATCH",) and r.terminated
    assert neg.agreed is None and neg.status == TERMINATED


def test_accept_with_nothing_on_the_table():
    w = build_world(); neg = _open(w)
    r = w.gateway.relay(make_message(w, BUYER, neg.negotiation_id, "accept", 0, fx_terms(), ref=fx_terms().digest()))
    assert r.codes == ("BAD_OPENING",)


def test_halt_mid_negotiation_ends_it():
    w = build_world(); neg = _open(w)
    w.gateway.relay(make_message(w, BUYER, neg.negotiation_id, "offer", 0, fx_terms()))
    w.gateway.halt("drill", by="ops")
    r = w.gateway.relay(make_message(w, SELLER, neg.negotiation_id, "counter", 1, fx_terms("70")))
    assert r.codes == ("KILL_SWITCH_ACTIVE",) and neg.status == TERMINATED
    with pytest.raises(GatewayDenied) as exc:
        _open(w)
    assert exc.value.codes == ("KILL_SWITCH_ACTIVE",)
    w.gateway.resume(by="ops")
    assert not w.gateway.halted and _open(w).status == OPEN
    assert [e["event"] for e in w.audit.entries()].count("kill_switch_released") == 1


def test_no_self_dealing():
    w = build_world()
    with pytest.raises(GatewayDenied) as exc:
        w.gateway.open_negotiation(BUYER, BUYER, "fx_forward", "USD/INR")
    assert "SELF_DEALING" in exc.value.codes


def test_message_budget_expires_a_stalemate():
    class Stubborn:
        def __init__(self, p): self.p = Decimal(p)
        def decide(self, ctx): return Action("counter", self.p, "no")
    w = build_world(buyer_strategy=Stubborn("30"), seller_strategy=Stubborn("80"))
    neg = run_negotiation(w.gateway, w.buyer, w.seller)
    assert neg.status == EXPIRED and len(neg.messages) == 10 and neg.agreed is None


# ---- execution
def test_execute_requires_an_agreed_deal():
    w = build_world(); neg = _open(w)
    assert w.gateway.execute(neg.negotiation_id).codes == ("NO_AGREED_DEAL",)
    assert neg.status == OPEN


def test_mandate_expiry_is_checked_at_settlement():
    w, neg = _agreed()
    w.clock.advance(days=31)
    exe = w.gateway.execute(neg.negotiation_id)
    assert exe.status == DENIED and "MANDATE_EXPIRED" in exe.codes


def test_mandate_revocation_is_checked_at_settlement():
    w, neg = _agreed()
    w.gateway.revoke_mandate(w.mandates[BUYER].mandate.mandate_id, "client withdrew authority", by="ops")
    exe = w.gateway.execute(neg.negotiation_id)
    assert exe.status == DENIED and exe.codes == ("MANDATE_REVOKED",)


def test_stored_mandate_tampering_is_caught_at_use():
    w, neg = _agreed()
    from dataclasses import replace
    from trustlayer.mandate import SignedMandate
    stored = w.gateway._mandates[BUYER]
    w.gateway._mandates[BUYER] = SignedMandate(replace(stored.mandate, aggregate_cap=Decimal("1")), stored.signature)
    exe = w.gateway.execute(neg.negotiation_id)
    assert exe.codes == ("MANDATE_SIGNATURE_INVALID",)


def test_credential_expiry_blocks_settlement():
    w, neg = _agreed()
    w.clock.advance(days=91)
    assert "CREDENTIAL_EXPIRED" in w.gateway.execute(neg.negotiation_id).codes


def test_pending_approval_then_wrong_person_then_owner():
    w, neg = _agreed(notional="1500000")
    exe = w.gateway.execute(neg.negotiation_id)
    assert exe.status == PENDING_APPROVAL and exe.pending_approvals == (BUYER,)
    assert w.ledger.balance(ACME_ACCT) == Decimal("5000000.00")
    wrong = w.gateway.resolve_approval(neg.negotiation_id, BUYER, ApprovalDecision(True, "intern@acme.example"))
    assert wrong.status == PENDING_APPROVAL and wrong.codes == ("APPROVER_NOT_AUTHORISED",)
    assert neg.status == PENDING_APPROVAL and not w.ledger.postings()
    done = w.gateway.resolve_approval(neg.negotiation_id, BUYER, ApprovalDecision(True, ACME_OWNER, "ok"))
    assert done.status == EXECUTED and len(w.ledger.postings()) == 1


def test_inline_approver_must_be_the_named_owner():
    w, neg = _agreed(notional="1500000", approver=lambda r: ApprovalDecision(True, "someone.else@acme.example"))
    exe = w.gateway.execute(neg.negotiation_id)
    assert exe.status == DENIED and exe.codes == ("APPROVER_NOT_AUTHORISED",) and not w.ledger.postings()


def test_approval_does_not_bypass_other_controls():
    w, neg = _agreed(notional="1500000")
    assert w.gateway.execute(neg.negotiation_id).status == PENDING_APPROVAL
    w.gateway.revoke_agent(SELLER, "compromise", by="ops")  # between approval request and release
    res = w.gateway.resolve_approval(neg.negotiation_id, BUYER, ApprovalDecision(True, ACME_OWNER))
    assert res.status == DENIED and "AGENT_REVOKED" in res.codes and not w.ledger.postings()


def test_approval_tier_forces_a_human_even_for_small_deals():
    seen = []
    def approver(req):
        seen.append(req.reasons)
        return ApprovalDecision(True, ACME_OWNER)
    w, neg = _agreed(buyer_tier=Tier.APPROVAL, approver=approver)
    assert w.gateway.execute(neg.negotiation_id).status == EXECUTED
    assert seen == [("TIER_REQUIRES_APPROVAL",)]


def test_shadow_tier_agent_never_settles_even_in_live_mode():
    w, neg = _agreed(buyer_tier=Tier.SHADOW)
    exe = w.gateway.execute(neg.negotiation_id)
    assert exe.status == SHADOW_LOGGED and exe.shadow_outcome == "ALLOW" and not w.ledger.postings()


def test_shadow_mode_records_a_would_be_denial():
    w, neg = _agreed(mode=Mode.SHADOW)
    w.gateway.revoke_mandate(w.mandates[SELLER].mandate.mandate_id, "test", by="ops")
    exe = w.gateway.execute(neg.negotiation_id)
    assert exe.status == SHADOW_LOGGED and exe.shadow_outcome == "DENY" and "MANDATE_REVOKED" in exe.codes


def test_insufficient_funds_fails_settlement_cleanly():
    w = build_world()
    w.ledger.open_account(ACME_ACCT, "USD", Decimal("100"))
    neg = run_negotiation(w.gateway, w.buyer, w.seller)
    exe = w.gateway.execute(neg.negotiation_id)
    assert exe.status == SETTLEMENT_FAILED and exe.codes == ("INSUFFICIENT_FUNDS",)
    assert w.gateway.usage(w.mandates[BUYER].mandate.mandate_id) == 0 and w.audit.verify().ok


def test_exposure_is_counted_only_after_settlement():
    w, neg = _agreed()
    mid = w.mandates[BUYER].mandate.mandate_id
    assert w.gateway.usage(mid) == 0
    w.gateway.execute(neg.negotiation_id)
    assert w.gateway.usage(mid) == Decimal("500000.00")


def test_every_state_change_is_audited_and_chain_verifies():
    w, neg = _agreed()
    w.gateway.execute(neg.negotiation_id)
    events = [e["event"] for e in w.audit.entries()]
    for needed in ("mandate_registered", "negotiation_opened", "message_relayed", "deal_agreed",
                   "settlement_instruction", "settlement_posted", "reconciliation", "execution_result"):
        assert needed in events
    assert w.audit.verify().ok
