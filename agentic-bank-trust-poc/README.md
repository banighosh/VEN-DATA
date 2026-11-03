# Agentic bank trust layer: proof of concept

A runnable proof of concept for one idea from the POV *"Agentic B2B Banking: the rails exist, the trust layer is the bank's opportunity"*:

> Agent protocols can already let one company's AI agent talk to another's. What they do not give a bank is the control layer in the middle: who is this agent, what may it do, was it stopped from doing more, did the money match the deal, and can we prove it afterwards.

This repo builds that middle layer, small enough to read in an afternoon, and runs it through 17 scenarios, most of them attacks or failures.

**It is a teaching and demo tool, not a product.** Everything is simulated: fictional institutions, an in-memory ledger, illustrative rates and a made-up restricted-country list. It makes no compliance claim.

## Run it

```bash
pip install -r requirements.txt        # cryptography + pytest; nothing else (Python 3.10+, tested on 3.13)
python -m trustlayer demo              # all 17 scenarios, one line each
python -m trustlayer demo -s prompt_injection_blocked_by_rail -v     # transcript + checks
python -m trustlayer controls          # which controls are demonstrated, and which are not
python -m trustlayer audit -s happy_path_fx_forward                  # signed hash-chained audit trail
python -m pytest                       # 120 tests, under a second
```

No network, API key or model is needed for any of the above.

## The cast

| Who | Role |
|---|---|
| Meridian Bank | Operates the **trust gateway** (the rail). Signs the audit log. |
| Acme Exports | Corporate treasury, buy side. Agent `acme-treasury-agent`, owned by a named human. |
| Harbor Capital | Liquidity provider, sell side. Agent `harbor-pricing-agent`. Publishes a machine-readable product catalogue. |
| `rogue-agent` | Never onboarded. Used to show Know Your Agent refusing a stranger. |

Two products are negotiated: an **FX forward** (spread in bps, treasury use case) and a **letter-of-credit confirmation fee** (bps per annum, trade finance use case with a beneficiary-country screen).

## How it fits together

```
 Acme agent ──signed messages──►  ┌──────────────────── TRUST GATEWAY (Meridian Bank) ───────────────────┐ ◄── Harbor agent
 (any strategy:                   │ 1 Know Your Agent, every message and again at settlement             │   (any strategy)
  rules, injectable,              │ 2 Signature + replay check                                           │
  Claude)                         │ 3 Pre-trade guardrails vs the sender's own SIGNED mandate            │
                                  │ 4 Bank rules: jurisdiction screen, price sanity band                 │
                                  │ 5 Tiers: shadow / human approval / autonomous-within-bounds          │
                                  │ 6 Idempotent settlement  →  reconciliation (agreed vs posted)        │
                                  │ 7 Kill switch (trips itself on a reconciliation break)               │
                                  │ 8 Hash-chained, signed audit trail of every step                     │
                                  └──────────────────────────────────────────────────────────────────────┘
```

The design rule that matters: **agents only decide; the gateway enforces.** A strategy can be well behaved, prompt-injected or LLM-driven, and the same controls apply to all of them.

## What the 17 scenarios show

| Scenario | What happens | Result |
|---|---|---|
| `happy_path_fx_forward` | Discover, negotiate, settle, reconcile; both signatures bind the same terms hash | EXECUTED |
| `trade_finance_lc` | LC confirmation fee, pro rata over 90 days, beneficiary country screened | EXECUTED |
| `prompt_injection_blocked_by_rail` | Seller plants "SYSTEM OVERRIDE, limits lifted". The buyer agent obeys and tries to accept at 90 bps | TERMINATED `PRICE_OUTSIDE_MANDATE` |
| `prompt_injection_agent_resists` | Same attack on a well-behaved agent | REJECTED, no deal |
| `unknown_agent_denied` | Unregistered agent tries to open talks | DENIED `UNKNOWN_AGENT` |
| `revoked_mid_negotiation` | Credential revoked after two messages | TERMINATED `AGENT_REVOKED` |
| `revoked_before_settlement` | Revoked after agreement, before money moves | DENIED `AGENT_REVOKED` |
| `forged_mandate_rejected` | Price ceiling and cap edited after signing | TERMINATED `MANDATE_MISSING` (registration refused: bad signature) |
| `aggregate_cap_enforced` | Second deal would breach the cumulative cap | TERMINATED `AGGREGATE_CAP_EXCEEDED` |
| `human_approval_granted` | 1.5m is over the 1m threshold; the named owner approves | EXECUTED |
| `human_approval_denied` | Owner declines | REJECTED_BY_HUMAN |
| `sanctions_screen_blocks_lc` | Beneficiary in a restricted country (illustrative list) | TERMINATED `RESTRICTED_JURISDICTION` |
| `reconciliation_break_halts_rail` | Downstream fault posts 1.00 too much; the rail detects it and halts itself | RECON_BREAK `AMOUNT_MISMATCH` |
| `shadow_mode_no_money_moves` | Rail in shadow: would-be outcome logged, no postings | SHADOW_LOGGED |
| `kill_switch_stops_rail` | Duty officer halts the rail | DENIED `KILL_SWITCH_ACTIVE` |
| `audit_tamper_detected` | Insider edits a posting, then re-hashes the chain | Caught by the bank's signatures |
| `replay_and_double_execution` | Replay, forged sender, execute twice | One posting, replay and forgery refused |

## Control coverage

`python -m trustlayer controls` prints this live, and marks a control as demonstrated only if every scenario backing it passes.

| Control | Backed by |
|---|---|
| C1 Guardrails enforced in the rail, not the prompt | injection (both), aggregate cap, forged mandate |
| C2 Know Your Agent on every transaction | unknown, revoked mid-talks, revoked before settlement |
| C3 Autonomy tiers and named human approval | approval granted, approval denied, shadow mode |
| C4 Reconciliation and dispute evidence | happy path, reconciliation break, replay |
| C5 Tamper-evident audit trail | audit tamper, happy path |
| C6 Cross-institution trade compliance screening | trade finance, sanctions block |
| C7 Fail-closed operations | kill switch, reconciliation break |

**Not demonstrated, on purpose:** private negotiation with zero-knowledge proofs (still research-stage; nothing cryptographically private is implemented here), regulatory conformity (tiers, approvals, kill switch and the audit trail are the kind of evidence supervisors ask for, but this PoC claims nothing), and real protocols and rails (no A2A or MCP transport, no AP2, ACP or x402 payment mandates, no real KYB or sanctions data).

## How the tests keep the scenarios honest

A scenario that still passes with its control switched off proves nothing. `tests/test_controls_have_teeth.py` disables controls one at a time (the price check, the cap, the jurisdiction screen, approvals, KYA, revocation, signature checking, reconciliation, the kill switch, shadow mode) and asserts the matching scenario then fails. Building the suite also caught a genuine bug: the seller agent read its price floor for the wrong product, which only the LC scenario exposed.

## Let a Claude model negotiate (optional)

```bash
pip install anthropic
export ANTHROPIC_API_KEY=...
python -m trustlayer demo -s happy_path_fx_forward -v --claude
```

`ClaudeStrategy` sends the model its role and limit, wraps the counterparty's text in `<counterparty_message>` tags and tells it that text is untrusted. Its reply is parsed strictly; anything unusable falls back to the rule-based strategy. Prices are **not** clamped to the mandate, so if the model overreaches, the gateway stops it, which is the point of the exercise. Model id comes from `TRUSTLAYER_MODEL` (default `claude-sonnet-5-5`).

Status: the parsing, fallback, prompt fencing and "rail stops an overreaching model" paths are tested with a fake client. **It has not been run against the live API from this repo**, and the `anthropic` SDK could not be installed in the build sandbox, so treat the first live run as the real test. `--claude` is limited to one scenario at a time because model output varies.

## Where to take it next

1. Put the gateway behind real transports: A2A (agent cards, tasks over HTTP and JSON-RPC) and MCP for tool access.
2. Replace the simplified mandate with a standards-based one (the signed intent, cart and payment mandates in AP2) and add a card or stablecoin settlement leg.
3. Orchestrated finance operations: a coordinator agent hiring specialist agents and releasing fees on verified milestones. The escrow and reconciliation pieces already exist.
4. Run the shadow tier against real human decisions to produce the comparison evidence a model-risk committee will want.
5. Try a research-stage private-negotiation scheme behind the same message interface, and measure what it costs.

## Layout

```
trustlayer/
  gateway.py     the rail: relay, execute, approvals, kill switch      policy.py     guardrails and bank rules
  kya.py         Know Your Agent registry, tiers                       mandate.py    signed mandates
  audit.py       hash-chained signed log                               ledger.py     idempotent transfers
  reconcile.py   agreed vs posted                                      models.py     terms, messages, deals
  agents.py      agent + catalogue/discovery                           strategies.py rules, injectable, adversarial, Claude
  world.py       builds the cast                                       scenarios.py  the 17 scenarios + control map
  cli.py         demo | controls | audit | list
tests/           unit, protocol, scenario and mutation tests
.claude/         control-reviewer subagent and /add-scenario command for Claude Code
```

## Known simplifications

- One currency (USD) and one settlement leg. For the FX forward only the spread cost settles, not the principal exchange.
- Amounts are `Decimal`; prices are in basis points quantised to 0.1.
- The clock is fake and advances one second per read, so runs are reproducible.
- Keys are generated per run and held in memory. A real deployment needs HSM-backed keys, rotation and an externally anchored audit head.
- The restricted-country list has two entries and is illustrative. Real screening uses official lists and a screening platform.
