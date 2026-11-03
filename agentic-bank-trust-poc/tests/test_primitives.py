from datetime import timedelta
from decimal import Decimal

import pytest

from trustlayer import crypto
from trustlayer.audit import AuditLog
from trustlayer.clock import Clock
from trustlayer.kya import AgentRecord, KYARegistry, Principal, Status, Tier
from trustlayer.ledger import Ledger, LedgerError, Posting
from trustlayer.models import Deal, Terms
from trustlayer.reconcile import reconcile
from trustlayer.world import ACME_ACCT, HARBOR_ACCT, build_world


# ---- crypto
def test_sign_verify_roundtrip_and_tamper():
    k = crypto.KeyPair.generate()
    payload = {"a": 1, "b": ["x"]}
    sig = k.sign(payload)
    assert crypto.verify(k.public_hex, payload, sig)
    assert not crypto.verify(k.public_hex, {"a": 2, "b": ["x"]}, sig)
    assert not crypto.verify(crypto.KeyPair.generate().public_hex, payload, sig)


@pytest.mark.parametrize("pub,sig", [("zz", "00"), ("00" * 32, "not-hex"), ("", ""), ("00" * 32, "00" * 64)])
def test_verify_rejects_garbage_without_raising(pub, sig):
    assert crypto.verify(pub, {"a": 1}, sig) is False


def test_canonical_encoding_ignores_key_order():
    assert crypto.digest({"a": 1, "b": 2}) == crypto.digest({"b": 2, "a": 1})


# ---- terms
def test_fx_cost_is_one_off_spread():
    assert Terms("fx_forward", "USD/INR", "USD", "500000", "52.5", 90).cost() == Decimal("2625.00")


def test_lc_cost_is_pro_rata_per_annum():
    assert Terms("lc_confirmation", "LC", "USD", "800000", "125", 90, "AE").cost() == Decimal("2500.00")


def test_equal_prices_hash_identically_however_written():
    a = Terms("fx_forward", "USD/INR", "USD", "500000", "52.5", 90)
    b = Terms("fx_forward", "USD/INR", "USD", Decimal("500000.00"), Decimal("52.50"), 90)
    assert a.digest() == b.digest()


@pytest.mark.parametrize("kwargs", [dict(notional="0"), dict(notional="-1"), dict(price="-1"), dict(tenor=0), dict(product="swap")])
def test_invalid_terms_rejected(kwargs):
    base = dict(product="fx_forward", notional="1000", price="10", tenor=30)
    base.update(kwargs)
    with pytest.raises(ValueError):
        Terms(base["product"], "USD/INR", "USD", base["notional"], base["price"], base["tenor"])


# ---- KYA
def _registry():
    clock = Clock()
    now = clock.peek()
    reg = KYARegistry()
    reg.register_principal(Principal("p", "P Ltd", "IN", "k", "ACC", True, now + timedelta(days=10)))
    reg.register_agent(AgentRecord("a", "p", "op", "owner@x", "k", Tier.AUTONOMOUS, now + timedelta(days=5)))
    return reg, now


def test_kya_ok_then_each_failure_mode():
    reg, now = _registry()
    assert reg.verify_agent("a", now).ok
    assert reg.verify_agent("nobody", now).code == "UNKNOWN_AGENT"
    assert reg.verify_agent("a", now + timedelta(days=6)).code == "CREDENTIAL_EXPIRED"
    reg.set_status("a", Status.SUSPENDED)
    assert reg.verify_agent("a", now).code == "AGENT_SUSPENDED"
    reg.set_status("a", Status.REVOKED)
    assert reg.verify_agent("a", now).code == "AGENT_REVOKED"


def test_kya_checks_the_principals_kyb_too():
    reg, now = _registry()
    reg.get_principal("p").kyb_verified = False
    assert reg.verify_agent("a", now).code == "PRINCIPAL_KYB_LAPSED"
    reg.get_principal("p").kyb_verified = True
    reg.get_agent("a").credential_expires = now + timedelta(days=30)
    assert reg.verify_agent("a", now + timedelta(days=11)).code == "PRINCIPAL_KYB_LAPSED"


def test_every_agent_needs_a_named_owner_and_a_known_principal():
    reg, now = _registry()
    with pytest.raises(ValueError):
        reg.register_agent(AgentRecord("b", "p", "op", "  ", "k", Tier.SHADOW, now))
    with pytest.raises(ValueError):
        reg.register_agent(AgentRecord("c", "ghost", "op", "o@x", "k", Tier.SHADOW, now))


# ---- audit
def _log(n=4):
    log = AuditLog(crypto.KeyPair.generate(), Clock())
    for i in range(n):
        log.append("e", "actor", {"i": i})
    return log


def test_audit_intact_then_detects_edit_delete_and_wrong_key():
    log = _log()
    assert log.verify().ok
    assert not log.verify(crypto.KeyPair.generate().public_hex).ok
    log._entries[1]["data"]["i"] = 99
    assert log.verify().reason == "entry content changed"
    log = _log()
    del log._entries[1]
    assert not log.verify().ok


def test_audit_reads_are_copies():
    log = _log()
    log.entries()[0]["data"]["i"] = 99
    assert log.verify().ok


# ---- ledger and reconciliation
def _ledger():
    led = Ledger()
    led.open_account("A", "USD", Decimal("100"))
    led.open_account("B", "USD", Decimal("0"))
    return led, Clock().peek()


def test_ledger_transfer_is_idempotent():
    led, ts = _ledger()
    p1 = led.transfer(idem_key="k", src="A", dst="B", amount=Decimal("10"), currency="USD", ref="r", ts=ts)
    p2 = led.transfer(idem_key="k", src="A", dst="B", amount=Decimal("10"), currency="USD", ref="r", ts=ts)
    assert p1 is p2 and led.balance("A") == Decimal("90.00") and len(led.postings()) == 1


@pytest.mark.parametrize("amount,ccy,code", [("500", "USD", "INSUFFICIENT_FUNDS"), ("5", "EUR", "CURRENCY_MISMATCH"), ("0", "USD", "INVALID_AMOUNT")])
def test_ledger_refusals(amount, ccy, code):
    led, ts = _ledger()
    with pytest.raises(LedgerError) as exc:
        led.transfer(idem_key="k", src="A", dst="B", amount=Decimal(amount), currency=ccy, ref="r", ts=ts)
    assert exc.value.code == code
    assert led.balance("A") == Decimal("100.00")


def _deal():
    w = build_world()
    from trustlayer.negotiation import run_negotiation
    neg = run_negotiation(w.gateway, w.buyer, w.seller)
    return neg.agreed


def _posting(deal, **kw):
    base = dict(posting_id="P1", idem_key="k", src=ACME_ACCT, dst=HARBOR_ACCT, amount=deal.expected_cost(),
                currency="USD", ref=deal.deal_id, ts="t")
    base.update(kw)
    return Posting(**base)


def test_reconcile_matches_and_flags_each_break():
    d = _deal()
    ok = reconcile(d, ACME_ACCT, HARBOR_ACCT, [_posting(d)])
    assert ok.matched and not ok.breaks
    assert reconcile(d, ACME_ACCT, HARBOR_ACCT, []).breaks[0].code == "MISSING_SETTLEMENT"
    assert reconcile(d, ACME_ACCT, HARBOR_ACCT, [_posting(d, amount=Decimal("1.00"))]).breaks[0].code == "AMOUNT_MISMATCH"
    assert reconcile(d, ACME_ACCT, HARBOR_ACCT, [_posting(d, currency="EUR")]).breaks[0].code == "CURRENCY_MISMATCH"
    assert reconcile(d, ACME_ACCT, HARBOR_ACCT, [_posting(d, dst="EVIL")]).breaks[0].code == "WRONG_PARTY"
    dup = reconcile(d, ACME_ACCT, HARBOR_ACCT, [_posting(d), _posting(d, posting_id="P2", idem_key="k2")])
    assert [b.code for b in dup.breaks] == ["DUPLICATE_SETTLEMENT"]
