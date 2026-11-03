"""The optional AI layer may only rewrite interpretation, never measured facts."""
from __future__ import annotations

import json

from app.config import get_settings
from app.insights import narrator

INSIGHTS = [{
    "id": "revenue_change", "title": "Revenue up", "observation": "Revenue rose 10%.", "severity": "positive",
    "metrics": [{"label": "Change", "value": 0.1, "format": "percent"}],
    "implication": "rule implication", "recommendation": "rule recommendation", "interpretation_source": "rule",
}]


def _enable(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("INSIGHTS_LLM_ENABLED", "true")
    get_settings.cache_clear()
    narrator._cache.clear()


def test_ai_rewrites_only_interpretation(monkeypatch):
    _enable(monkeypatch)
    sent = {}

    def transport(payload, key, timeout):
        sent.update(payload)
        body = {"items": [{"id": "revenue_change", "implication": "AI implication", "recommendation": "AI action"}]}
        return {"content": [{"type": "text", "text": json.dumps(body)}]}

    out, status = narrator.enrich(INSIGHTS, transport=transport)
    assert status["applied"] is True
    assert out[0]["interpretation_source"] == "ai"
    assert out[0]["implication"] == "AI implication"
    assert out[0]["observation"] == INSIGHTS[0]["observation"]  # facts untouched
    assert out[0]["metrics"] == INSIGHTS[0]["metrics"]
    assert "Never state or guess a cause" in sent["system"]
    get_settings.cache_clear()


def test_ai_failure_falls_back_to_rules(monkeypatch):
    _enable(monkeypatch)

    def broken(payload, key, timeout):
        return {"content": [{"type": "text", "text": "not json"}]}

    out, status = narrator.enrich(INSIGHTS, transport=broken)
    assert out[0]["interpretation_source"] == "rule"
    assert status["applied"] is False and "rule-based" in status["error"]
    get_settings.cache_clear()


def test_ai_disabled_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("INSIGHTS_LLM_ENABLED", raising=False)
    get_settings.cache_clear()
    out, status = narrator.enrich(INSIGHTS)
    assert status["enabled"] is False and out == INSIGHTS
