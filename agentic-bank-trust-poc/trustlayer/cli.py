"""Command line: list scenarios, run the demo, print the control matrix, show an audit trail."""
from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import world as world_mod
from .scenarios import CONTROLS, NOT_DEMONSTRATED, SCENARIOS, ScenarioReport, run_all, run_scenario
from .strategies import ClaudeStrategy


def _mark(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def _codes(codes) -> str:
    return ", ".join(codes) if codes else "-"


def _transcript(report: ScenarioReport) -> List[str]:
    neg = report.run.negotiation
    lines: List[str] = []
    if neg is None:
        lines.append("  (no negotiation was opened)")
        return lines
    for m in neg.messages:
        price = f" {m.terms.price_bps} bps" if m.terms else ""
        text = f'  "{m.text[:70]}"' if m.text else ""
        lines.append(f"  #{m.seq} {m.sender:<22}{m.kind:<8}{price}{text}")
    for b in neg.blocked:
        price = f" {b['price_bps']} bps" if b.get("price_bps") else ""
        tag = "BLOCKED+ENDED" if b["terminal"] else "BLOCKED"
        lines.append(f"  !! {b['sender']:<22}{b['kind']:<8}{price}  {tag}: {_codes(b['codes'])}")
    return lines


def _detail(report: ScenarioReport) -> List[str]:
    sc = SCENARIOS[report.name]
    out = [f"  {sc.story}", "  Transcript:"]
    out += _transcript(report)
    d = report.run.negotiation.agreed if report.run.negotiation else None
    if d:
        out.append(f"  Deal {d.deal_id}: {d.terms.product} {d.terms.notional} {d.terms.currency} at {d.terms.price_bps} bps, cost {d.terms.cost()}")
    out.append("  Checks:")
    out += [f"    [{_mark(ok)}] {desc}" for desc, ok in report.checks]
    return out


def _print_report(r: ScenarioReport, verbose: bool) -> None:
    print(f"[{_mark(r.passed)}] {r.name:<36} {r.final_status:<18} {_codes(r.codes)}")
    if verbose or not r.passed:
        print(f"  {r.title}")
        for line in _detail(r):
            print(line)
        print()


def cmd_list(_: argparse.Namespace) -> int:
    for sc in SCENARIOS.values():
        print(f"{sc.name:<36} {sc.title}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    if args.claude:
        if not args.scenario:
            print("--claude needs -s/--scenario: model output varies, so it is limited to one scenario at a time.", file=sys.stderr)
            return 2
        world_mod.set_default_strategy_wrapper(lambda base: ClaudeStrategy(base))
        print("Claude mode: using the Anthropic SDK if installed and ANTHROPIC_API_KEY is set; otherwise the rule-based fallback decides.\n")
    names = [args.scenario] if args.scenario else list(SCENARIOS)
    unknown = [n for n in names if n not in SCENARIOS]
    if unknown:
        print(f"unknown scenario: {unknown[0]} (try `list`)", file=sys.stderr)
        return 2
    reports = [run_scenario(n) for n in names]
    if args.json:
        print(json.dumps([{
            "name": r.name, "passed": r.passed, "expected": r.expected, "final_status": r.final_status,
            "codes": list(r.codes), "checks": [{"check": d, "ok": ok} for d, ok in r.checks],
        } for r in reports], indent=2))
    else:
        print(f"Trust-layer demo: {len(reports)} scenario(s)\n")
        for r in reports:
            _print_report(r, args.verbose)
        passed = sum(r.passed for r in reports)
        print(f"{passed}/{len(reports)} scenarios behaved as specified")
        if args.claude:
            for agent in reports[0].run.world.agents.values():
                if isinstance(agent.strategy, ClaudeStrategy):
                    print(f"  {agent.agent_id}: decisions from Claude={agent.strategy.calls['claude']}, from fallback={agent.strategy.calls['fallback']}")
    return 0 if all(r.passed for r in reports) else 1


def cmd_controls(_: argparse.Namespace) -> int:
    reports = {r.name: r for r in run_all()}
    print("Control coverage (each control is demonstrated only if every backing scenario passes)\n")
    ok_all = True
    for cid, title, names in CONTROLS:
        ok = all(reports[n].passed for n in names)
        ok_all &= ok
        print(f"[{_mark(ok)}] {cid} {title}")
        print(f"       evidence: {', '.join(names)}")
    print("\nNot demonstrated here:")
    for title, why in NOT_DEMONSTRATED:
        print(f"  - {title}: {why}")
    return 0 if ok_all else 1


def cmd_audit(args: argparse.Namespace) -> int:
    if args.scenario not in SCENARIOS:
        print(f"unknown scenario: {args.scenario}", file=sys.stderr)
        return 2
    run = run_scenario(args.scenario).run
    for e in run.world.audit.entries():
        brief = {k: v for k, v in e["data"].items() if k not in ("text",)}
        print(f"{e['seq']:>3} {e['ts'][11:19]} {e['event']:<22} {e['actor']:<22} {json.dumps(brief, default=str)[:150]}")
    v = run.world.audit.verify()
    print(f"\nchain {'verifies' if v.ok else 'FAILS: ' + v.reason}; head {run.world.audit.entries()[-1]['hash'][:16]}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="trustlayer", description="Bank trust-layer PoC for agent-to-agent commerce")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list scenarios").set_defaults(fn=cmd_list)
    d = sub.add_parser("demo", help="run scenarios")
    d.add_argument("-s", "--scenario", help="run one scenario")
    d.add_argument("-v", "--verbose", action="store_true", help="show transcripts and checks")
    d.add_argument("--json", action="store_true", help="machine-readable output")
    d.add_argument("--claude", action="store_true", help="let a Claude model negotiate (needs -s, the SDK and ANTHROPIC_API_KEY)")
    d.set_defaults(fn=cmd_demo)
    sub.add_parser("controls", help="control coverage matrix").set_defaults(fn=cmd_controls)
    a = sub.add_parser("audit", help="print the signed audit trail of a scenario")
    a.add_argument("-s", "--scenario", required=True)
    a.set_defaults(fn=cmd_audit)
    args = parser.parse_args(argv)
    return args.fn(args)
