"""Append-only, hash-chained, signed audit log.

Each entry commits to the one before it (prev_hash) and is signed by the
operating bank's key. Editing an entry breaks the chain; recomputing the chain
after an edit breaks the signatures, which an attacker without the bank's key
cannot redo. A real deployment would also anchor the head hash somewhere the
operator cannot rewrite (WORM storage, an independent party).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from . import crypto
from .clock import Clock

GENESIS = "0" * 64


@dataclass(frozen=True)
class AuditVerification:
    ok: bool
    broken_at: Optional[int] = None
    reason: str = ""


class AuditLog:
    def __init__(self, keys: crypto.KeyPair, clock: Clock) -> None:
        self._keys = keys
        self._clock = clock
        self._entries: List[Dict[str, Any]] = []

    @property
    def public_hex(self) -> str:
        return self._keys.public_hex

    def append(self, event: str, actor: str, data: Dict[str, Any]) -> Dict[str, Any]:
        prev = self._entries[-1]["hash"] if self._entries else GENESIS
        body = {
            "seq": len(self._entries),
            "ts": self._clock.now().isoformat(),
            "event": event,
            "actor": actor,
            "data": data,
            "prev_hash": prev,
        }
        h = crypto.digest(body)
        entry = dict(body, hash=h, sig=self._keys.sign({"hash": h}))
        self._entries.append(entry)
        return entry

    def entries(self) -> List[Dict[str, Any]]:
        """Read-only copy for display and export."""
        return copy.deepcopy(self._entries)

    def events(self, name: str) -> List[Dict[str, Any]]:
        return [e for e in self.entries() if e["event"] == name]

    def verify(self, public_hex: Optional[str] = None) -> AuditVerification:
        pub = public_hex or self._keys.public_hex
        prev = GENESIS
        for i, e in enumerate(self._entries):
            body = {k: e[k] for k in ("seq", "ts", "event", "actor", "data", "prev_hash")}
            if e["seq"] != i:
                return AuditVerification(False, i, "sequence gap")
            if e["prev_hash"] != prev:
                return AuditVerification(False, i, "chain link broken")
            if crypto.digest(body) != e["hash"]:
                return AuditVerification(False, i, "entry content changed")
            if not crypto.verify(pub, {"hash": e["hash"]}, e["sig"]):
                return AuditVerification(False, i, "signature invalid")
            prev = e["hash"]
        return AuditVerification(True)
