"""A tiny single-currency-per-account ledger with idempotent transfers.

Stands in for the settlement rail (RTGS, a payments hub, a stablecoin leg).
The optional `fault` hook lets a scenario simulate a downstream bug that posts
the wrong amount, so reconciliation has something real to catch.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Callable, Dict, List, Optional

from .models import money


class LedgerError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass(frozen=True)
class Posting:
    posting_id: str
    idem_key: str
    src: str
    dst: str
    amount: Decimal
    currency: str
    ref: str
    ts: str


class Ledger:
    def __init__(self, fault: Optional[Callable[[Decimal], Decimal]] = None) -> None:
        self._balances: Dict[str, Decimal] = {}
        self._currency: Dict[str, str] = {}
        self._postings: List[Posting] = []
        self._by_idem: Dict[str, Posting] = {}
        self.fault = fault  # test/demo only: distorts the amount actually posted

    def open_account(self, account_id: str, currency: str, opening: Decimal = Decimal("0")) -> None:
        self._balances[account_id] = money(opening)
        self._currency[account_id] = currency

    def balance(self, account_id: str) -> Decimal:
        return self._balances[account_id]

    def postings(self) -> List[Posting]:
        return list(self._postings)

    def postings_for(self, ref: str) -> List[Posting]:
        return [p for p in self._postings if p.ref == ref]

    def transfer(
        self,
        *,
        idem_key: str,
        src: str,
        dst: str,
        amount: Decimal,
        currency: str,
        ref: str,
        ts: datetime,
    ) -> Posting:
        if idem_key in self._by_idem:  # replay-safe: same key never posts twice
            return self._by_idem[idem_key]
        if src not in self._balances or dst not in self._balances:
            raise LedgerError("UNKNOWN_ACCOUNT")
        if self._currency[src] != currency or self._currency[dst] != currency:
            raise LedgerError("CURRENCY_MISMATCH")
        posted = money(self.fault(amount)) if self.fault else money(amount)
        if posted <= 0:
            raise LedgerError("INVALID_AMOUNT")
        if self._balances[src] < posted:
            raise LedgerError("INSUFFICIENT_FUNDS", f"{self._balances[src]} < {posted}")
        self._balances[src] -= posted
        self._balances[dst] += posted
        posting = Posting(
            posting_id=f"PST-{len(self._postings) + 1:04d}",
            idem_key=idem_key,
            src=src,
            dst=dst,
            amount=posted,
            currency=currency,
            ref=ref,
            ts=ts.isoformat(),
        )
        self._postings.append(posting)
        self._by_idem[idem_key] = posting
        return posting
