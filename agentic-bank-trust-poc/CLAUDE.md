# CLAUDE.md

Proof of concept of a bank-operated trust layer for cross-company agent-to-agent commerce. Read `README.md` first.

## Commands

```bash
python -m pytest                          # whole suite, under a second
python -m trustlayer demo                 # 17 scenarios
python -m trustlayer demo -s NAME -v      # one scenario with transcript and checks
python -m trustlayer controls             # control coverage matrix
python -m trustlayer audit -s NAME        # audit trail for a scenario
```

## Invariants (do not break these)

1. **Agents decide, the gateway enforces.** Never move a limit, check or approval into a strategy, prompt or agent. Anything an agent could skip belongs in `gateway.py` or `policy.py`.
2. **Fail closed.** An unknown, missing or unverifiable input is a denial with a reason code, never a pass. Add a code to the denial, not a silent default.
3. **Authenticate before changing state.** In `TrustGateway.relay`, signature and replay checks come before anything that mutates a negotiation. Unauthenticated input must not consume message ids or end someone else's talks.
4. **Re-check at the moment of release.** KYA, mandate signature, expiry, revocation, usage and policy are re-evaluated in `execute`, including after a human approval.
5. **Every state change is audited** through `TrustGateway._log`, with JSON-safe data (`Decimal` becomes `str`).
6. **Money is `Decimal`, never float.** Prices are bps quantised to 0.1 via `q_bps`; cash via `money`.
7. **Default path stays dependency-light.** Only `cryptography` is required. The Claude strategy must stay optional and must fall back to the rule-based strategy on any failure.
8. **Do not overclaim.** No statements of regulatory compliance, no claims of A2A, AP2, ACP or x402 support, no claims that the live Claude path has been verified unless it has.

## Adding a control

1. Implement it in the gateway or policy.
2. Add a scenario in `scenarios.py` (`@scenario(...)`) with an expected status, reason codes and checks that look at balances, signatures or the audit trail, not only the status.
3. Add a mutation test in `tests/test_controls_have_teeth.py` proving the scenario fails when the control is disabled.
4. Map it to a control in `CONTROLS` (or add it to `NOT_DEMONSTRATED` if it is out of scope).
5. Run `python -m pytest`.

Use the `control-reviewer` subagent on any change to `gateway.py`, `policy.py`, `kya.py`, `mandate.py`, `audit.py` or `reconcile.py`.

## Conventions

- Python 3.10+, type hints, small modules. Fictional names only (Meridian Bank, Acme Exports, Harbor Capital).
- Tests that build messages by hand use `tests/conftest.py::make_message`; pass a different `tag` to avoid message-id collisions, because an authenticated message that is refused still consumes its id.
- `scenarios.py` scenarios may reach into internals (for example `audit._entries`) only to simulate an attacker; mark it with a comment.
