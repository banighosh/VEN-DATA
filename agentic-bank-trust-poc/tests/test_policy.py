from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from trustlayer.kya import Tier
from trustlayer.models import Terms
from trustlayer.policy import ALLOW, DENY, REQUIRE_APPROVAL, Policy
from trustlayer.world import BUYER, SELLER, build_world

POLICY = Policy()


def _mandate(side="buy", **overrides):
    w = build_world(buyer_overrides=overrides if side == "buy" else None, seller_overrides=overrides if side == "sell" else None)
    return w.mandates[BUYER if side == "buy" else SELLER].mandate, w.clock.peek()


def _check(side="buy", terms=None, used="0", tier=Tier.AUTONOMOUS, **overrides):
    m, now = _mandate(side, **overrides)
    terms = terms or Terms("fx_forward", "USD/INR", "USD", "500000", "50", 90)
    agent, cp = (BUYER, SELLER) if side == "buy" else (SELLER, BUYER)
    return POLICY.check_side(agent_id=agent, side=side, mandate=m, terms=terms, counterparty_id=cp,
                             used=Decimal(used), now=now, tier=tier)


def test_clean_deal_is_allowed():
    assert _check().outcome == ALLOW


@pytest.mark.parametrize("terms,code", [
    (Terms("fx_forward", "USD/INR", "USD", "500000", "61", 90), "PRICE_OUTSIDE_MANDATE"),
    (Terms("fx_forward", "USD/INR", "USD", "2000001", "50", 90), "NOTIONAL_ABOVE_MANDATE"),
    (Terms("fx_forward", "USD/INR", "USD", "500000", "50", 181), "TENOR_ABOVE_MANDATE"),
    (Terms("fx_forward", "EUR/INR", "USD", "500000", "50", 90), "INSTRUMENT_NOT_PERMITTED"),
    (Terms("fx_forward", "USD/INR", "EUR", "500000", "50", 90), "CURRENCY_NOT_PERMITTED"),
])
def test_buy_side_violations(terms, code):
    res = _check(terms=terms)
    assert res.outcome == DENY and code in res.codes


def test_price_boundary_is_inclusive_for_a_buyer():
    assert _check(terms=Terms("fx_forward", "USD/INR", "USD", "500000", "60", 90)).outcome == ALLOW


def test_sell_side_price_is_a_floor():
    assert _check("sell", Terms("fx_forward", "USD/INR", "USD", "500000", "39.9", 90)).codes == ("PRICE_OUTSIDE_MANDATE",)
    assert _check("sell", Terms("fx_forward", "USD/INR", "USD", "500000", "40", 90)).outcome == ALLOW


def test_aggregate_cap_counts_prior_usage():
    assert _check(used="4500000").outcome == ALLOW
    assert "AGGREGATE_CAP_EXCEEDED" in _check(used="4500001").codes


def test_approval_required_over_threshold_or_by_tier():
    over = _check(terms=Terms("fx_forward", "USD/INR", "USD", "1500000", "50", 90))
    assert over.outcome == REQUIRE_APPROVAL and over.approvals[0].reason == "NOTIONAL_ABOVE_APPROVAL_THRESHOLD"
    tier = _check(tier=Tier.APPROVAL)
    assert tier.outcome == REQUIRE_APPROVAL and tier.approvals[0].reason == "TIER_REQUIRES_APPROVAL"


def test_violations_win_over_approvals():
    res = _check(terms=Terms("fx_forward", "USD/INR", "USD", "1500000", "99", 90))
    assert res.outcome == DENY and res.approvals


def test_mandate_time_window():
    m, now = _mandate()
    kw = dict(agent_id=BUYER, side="buy", terms=Terms("fx_forward", "USD/INR", "USD", "1000", "50", 30),
              counterparty_id=SELLER, used=Decimal("0"), tier=Tier.AUTONOMOUS, mandate=m)
    assert "MANDATE_EXPIRED" in POLICY.check_side(now=now + timedelta(days=31), **kw).codes
    assert "MANDATE_NOT_YET_VALID" in POLICY.check_side(now=now - timedelta(days=2), **kw).codes


def test_mandate_must_belong_to_this_agent_and_side_and_counterparty():
    m, now = _mandate()
    kw = dict(terms=Terms("fx_forward", "USD/INR", "USD", "1000", "50", 30), used=Decimal("0"), now=now, tier=Tier.AUTONOMOUS, mandate=m)
    assert "MANDATE_AGENT_MISMATCH" in POLICY.check_side(agent_id="someone-else", side="buy", counterparty_id=SELLER, **kw).codes
    assert "MANDATE_SIDE_MISMATCH" in POLICY.check_side(agent_id=BUYER, side="sell", counterparty_id=SELLER, **kw).codes
    assert "COUNTERPARTY_NOT_PERMITTED" in POLICY.check_side(agent_id=BUYER, side="buy", counterparty_id="stranger", **kw).codes


def test_missing_price_limit_is_a_violation_not_a_free_pass():
    res = _check(price_limit_bps={})
    assert "PRICE_LIMIT_UNDEFINED" in res.codes


@pytest.mark.parametrize("terms,code", [
    (Terms("fx_forward", "USD/INR", "USD", "1000", "101", 30), "PRICE_OUTSIDE_SANITY_BAND"),
    (Terms("lc_confirmation", "LC", "USD", "1000", "10", 30, "KP"), "RESTRICTED_JURISDICTION"),
    (Terms("lc_confirmation", "LC", "USD", "1000", "10", 30, "ir"), "RESTRICTED_JURISDICTION"),
    (Terms("lc_confirmation", "LC", "USD", "1000", "10", 30, None), "BENEFICIARY_COUNTRY_MISSING"),
])
def test_bank_rules(terms, code):
    assert code in [v.code for v in POLICY.check_bank_rules(terms)]


def test_bank_rules_pass_clean_terms():
    assert POLICY.check_bank_rules(Terms("lc_confirmation", "LC", "USD", "1000", "10", 30, "AE")) == []
