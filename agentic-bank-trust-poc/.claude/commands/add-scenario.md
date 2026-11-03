---
description: Add a new attack or control scenario to the trust-layer PoC, with its mutation test
argument-hint: <short description of the attack or control>
---

Add a scenario for: $ARGUMENTS

Follow the "Adding a control" steps in CLAUDE.md:

1. Say in one sentence what must be true after the scenario runs and which invariant it exercises.
2. Implement or adjust the control in `trustlayer/gateway.py` or `trustlayer/policy.py` only if it does not already exist. Do not put it in an agent or strategy.
3. Add a `@scenario(...)` function in `trustlayer/scenarios.py` using `build_world(...)`. Give it an expected final status and reason codes, plus checks on balances, signatures or the audit trail.
4. Map it into `CONTROLS` in the same file.
5. Add a mutation test to `tests/test_controls_have_teeth.py` that disables the control and asserts the scenario fails.
6. Update the scenario count in `README.md` and in `tests/test_agents_and_scenarios.py` (the `17/17` assertion).
7. Run `python -m pytest -q` and `python -m trustlayer controls`, then invoke the `control-reviewer` subagent on the diff.
