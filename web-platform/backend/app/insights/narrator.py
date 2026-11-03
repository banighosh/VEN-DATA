"""Optional AI interpretation layer (Anthropic Messages API).

Only the *interpretation* fields (implication, recommendation) are ever written
by the model. Observations and metrics stay exactly as computed. If the API is
not configured, unreachable or returns anything unexpected, the rule-based
interpretation is kept and the reason is reported to the client.
"""
from __future__ import annotations

import hashlib
import json
import logging
import urllib.error
import urllib.request
from typing import Any

from ..config import get_settings

log = logging.getLogger(__name__)
API_URL = "https://api.anthropic.com/v1/messages"
_cache: dict[str, list[dict[str, str]]] = {}

SYSTEM_PROMPT = """You are a business intelligence analyst writing for executives.
You receive statistical observations computed from a sales dataset. For each one, write:
- "implication": one or two sentences on what the observation means for the business.
- "recommendation": one concrete, proportionate next step.

Strict rules:
- Use ONLY the facts given. Do not introduce numbers that are not in the input.
- Never state or guess a cause for a change or correlation (no marketing campaigns, seasonality, competitors,
  economic conditions, etc.) unless the observation itself states it. If a cause matters, recommend investigating it.
- Keep each field under 45 words. Plain business English, no hype.
Return JSON only: {"items": [{"id": "...", "implication": "...", "recommendation": "..."}]} in the same order."""


def llm_status() -> dict[str, Any]:
    s = get_settings()
    return {"enabled": bool(s.insights_llm_enabled and s.anthropic_api_key), "model": s.insights_llm_model,
            "configured": bool(s.anthropic_api_key)}


def _post(payload: dict[str, Any], api_key: str, timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(API_URL, data=json.dumps(payload).encode(), method="POST", headers={
        "content-type": "application/json", "x-api-key": api_key, "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (fixed https URL)
        return json.loads(resp.read().decode())


def enrich(insights: list[dict[str, Any]], transport=None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return insights with AI interpretations where possible, plus a status dict."""
    s = get_settings()
    status = llm_status()
    if not status["enabled"] or not insights:
        return insights, {**status, "applied": False}
    facts = [{"id": i["id"], "title": i["title"], "observation": i["observation"],
              "metrics": [{"label": m["label"], "value": m["value"], "format": m["format"]} for m in i["metrics"]]}
             for i in insights]
    key = hashlib.sha256(json.dumps(facts, sort_keys=True, default=str).encode()).hexdigest()
    try:
        if key in _cache:
            items = _cache[key]
        else:
            payload = {"model": s.insights_llm_model, "max_tokens": 2000, "system": SYSTEM_PROMPT,
                       "messages": [{"role": "user", "content": json.dumps({"observations": facts}, default=str)}]}
            raw = (transport or _post)(payload, s.anthropic_api_key, s.insights_llm_timeout_s)
            text = "".join(block.get("text", "") for block in raw.get("content", []) if block.get("type") == "text")
            start, end = text.find("{"), text.rfind("}")
            items = json.loads(text[start:end + 1])["items"]
            _cache[key] = items
        by_id = {it["id"]: it for it in items if isinstance(it, dict) and "id" in it}
        out = []
        for ins in insights:
            ai = by_id.get(ins["id"])
            if ai and isinstance(ai.get("implication"), str) and isinstance(ai.get("recommendation"), str):
                out.append({**ins, "implication": ai["implication"].strip(), "recommendation": ai["recommendation"].strip(),
                            "interpretation_source": "ai", "rule_implication": ins["implication"],
                            "rule_recommendation": ins["recommendation"]})
            else:
                out.append(ins)
        return out, {**status, "applied": True}
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
        log.warning("AI interpretation unavailable: %s", exc)
        return insights, {**status, "applied": False, "error": f"AI interpretation unavailable ({type(exc).__name__}); showing rule-based interpretation."}
