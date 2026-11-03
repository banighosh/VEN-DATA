"""Mutation checks: switch a control off and the scenario that claims to prove it
must fail. If a scenario still passed with its control disabled, it would be
proving nothing."""
import pytest

from trustlayer import crypto
from trustlayer.gateway import TrustGateway
from trustlayer.kya import KYARegistry, KYAResult
from trustlayer.policy import Policy
from trustlayer.scenarios import run_scenario
import trustlayer.gateway as gateway_mod


def _drop_codes(monkeypatch, *codes):
    orig_side, orig_bank = Policy.check_side, Policy.check_bank_rules

    def side(self, **kw):
        res = orig_side(self, **kw)
        res.violations = [v for v in res.violations if v.code not in codes]
        return res

    def bank(self, terms):
        return [v for v in orig_bank(self, terms) if v.code not in codes]

    monkeypatch.setattr(Policy, "check_side", side)
    monkeypatch.setattr(Policy, "check_bank_rules", bank)


@pytest.mark.parametrize("code,scenario", [
    ("PRICE_OUTSIDE_MANDATE", "prompt_injection_blocked_by_rail"),
    ("AGGREGATE_CAP_EXCEEDED", "aggregate_cap_enforced"),
    ("RESTRICTED_JURISDICTION", "sanctions_screen_blocks_lc"),
])
def test_removing_a_policy_check_fails_its_scenario(monkeypatch, code, scenario):
    assert run_scenario(scenario).passed
    _drop_codes(monkeypatch, code)
    assert not run_scenario(scenario).passed


def test_removing_approval_requirements_fails_the_approval_scenarios(monkeypatch):
    orig = Policy.check_side

    def side(self, **kw):
        res = orig(self, **kw)
        res.approvals = []
        return res

    monkeypatch.setattr(Policy, "check_side", side)
    assert not run_scenario("human_approval_granted").passed
    assert not run_scenario("human_approval_denied").passed


def test_accepting_every_agent_fails_the_unknown_agent_scenario(monkeypatch):
    monkeypatch.setattr(KYARegistry, "verify_agent", lambda self, agent_id, now: KYAResult(True))
    assert not run_scenario("unknown_agent_denied").passed


def test_ignoring_revocation_fails_both_revocation_scenarios(monkeypatch):
    orig = KYARegistry.verify_agent

    def lenient(self, agent_id, now):
        res = orig(self, agent_id, now)
        return KYAResult(True) if res.code == "AGENT_REVOKED" else res

    monkeypatch.setattr(KYARegistry, "verify_agent", lenient)
    assert not run_scenario("revoked_mid_negotiation").passed
    assert not run_scenario("revoked_before_settlement").passed


def test_trusting_every_signature_fails_forgery_and_replay_scenarios(monkeypatch):
    monkeypatch.setattr(crypto, "verify", lambda *a, **k: True)
    assert not run_scenario("forged_mandate_rejected").passed
    assert not run_scenario("replay_and_double_execution").passed
    assert not run_scenario("audit_tamper_detected").passed


def test_skipping_reconciliation_fails_the_break_scenario(monkeypatch):
    from trustlayer.reconcile import ReconResult

    def always_matched(deal, src, dst, postings):
        return ReconResult(True, deal.expected_cost(), deal.expected_cost())

    monkeypatch.setattr(gateway_mod, "reconcile", always_matched)
    assert not run_scenario("reconciliation_break_halts_rail").passed


def test_a_dead_kill_switch_fails_its_scenarios(monkeypatch):
    monkeypatch.setattr(TrustGateway, "halt", lambda self, reason, by: None)
    assert not run_scenario("kill_switch_stops_rail").passed
    assert not run_scenario("reconciliation_break_halts_rail").passed


def test_a_shadow_mode_that_settles_fails_its_scenario(monkeypatch):
    monkeypatch.setattr(gateway_mod, "Mode", type("M", (), {"SHADOW": object(), "LIVE": object()}))
    assert not run_scenario("shadow_mode_no_money_moves").passed
