"""Post-settlement reconciliation: what was agreed vs what actually moved.

The agreed side comes from the signed deal (both parties' signatures over the
same terms hash). The actual side comes from the ledger. Any difference is a
break, and the gateway fails closed when it sees one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional

from .ledger import Posting
from .models import Deal


@dataclass(frozen=True)
class Break:
    code: str
    detail: str = ""


@dataclass
class ReconResult:
    matched: bool
    expected: Decimal
    actual: Optional[Decimal]
    breaks: List[Break] = field(default_factory=list)


def reconcile(deal: Deal, src: str, dst: str, postings: List[Posting]) -> ReconResult:
    expected = deal.expected_cost()
    mine = [p for p in postings if p.ref == deal.deal_id]
    if not mine:
        return ReconResult(False, expected, None, [Break("MISSING_SETTLEMENT", deal.deal_id)])
    breaks: List[Break] = []
    if len(mine) > 1:
        breaks.append(Break("DUPLICATE_SETTLEMENT", f"{len(mine)} postings"))
    p = mine[0]
    if p.amount != expected:
        breaks.append(Break("AMOUNT_MISMATCH", f"expected {expected}, posted {p.amount}"))
    if p.currency != deal.terms.currency:
        breaks.append(Break("CURRENCY_MISMATCH", f"{p.currency} != {deal.terms.currency}"))
    if p.src != src or p.dst != dst:
        breaks.append(Break("WRONG_PARTY", f"{p.src}->{p.dst}, expected {src}->{dst}"))
    return ReconResult(not breaks, expected, p.amount, breaks)
