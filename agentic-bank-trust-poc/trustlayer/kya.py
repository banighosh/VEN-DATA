"""Know Your Agent (KYA): who operates an agent, whom it acts for, which human
owns it, and whether its credential is still good *right now*.

KYC/KYB answers "who is the company". KYA adds "is this software agent really
that company's, is it still authorised, and who answers for it". The gateway
calls verify_agent on every message and again at settlement, not once at
onboarding.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Tuple


class Status(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class Tier(str, Enum):
    """How much autonomy the bank has granted this agent."""

    SHADOW = "shadow"  # decisions evaluated and logged, never executed
    APPROVAL = "execute_with_approval"  # a named human approves every deal
    AUTONOMOUS = "autonomous_within_bounds"  # acts alone inside its mandate


@dataclass
class Principal:
    """The legal entity an agent acts for (the KYB'd company)."""

    principal_id: str
    legal_name: str
    jurisdiction: str
    public_key: str  # verifies the mandates this principal signs
    settlement_account: str
    kyb_verified: bool
    kyb_valid_until: datetime


@dataclass
class AgentRecord:
    agent_id: str
    principal_id: str
    operator: str  # who runs the software (vendor or in-house platform)
    human_owner: str  # named person accountable for this agent
    public_key: str  # verifies messages this agent signs
    tier: Tier
    credential_expires: datetime
    capabilities: Tuple[str, ...] = ()
    status: Status = Status.ACTIVE


@dataclass(frozen=True)
class KYAResult:
    ok: bool
    code: str = "OK"
    detail: str = ""


class KYARegistry:
    def __init__(self) -> None:
        self._principals: Dict[str, Principal] = {}
        self._agents: Dict[str, AgentRecord] = {}

    def register_principal(self, principal: Principal) -> None:
        self._principals[principal.principal_id] = principal

    def register_agent(self, record: AgentRecord) -> None:
        if not record.human_owner.strip():
            raise ValueError("every agent needs a named human owner")
        if record.principal_id not in self._principals:
            raise ValueError(f"unknown principal: {record.principal_id}")
        self._agents[record.agent_id] = record

    def get_agent(self, agent_id: str) -> Optional[AgentRecord]:
        return self._agents.get(agent_id)

    def get_principal(self, principal_id: str) -> Optional[Principal]:
        return self._principals.get(principal_id)

    def set_status(self, agent_id: str, status: Status) -> None:
        self._agents[agent_id].status = status

    def verify_agent(self, agent_id: str, now: datetime) -> KYAResult:
        rec = self._agents.get(agent_id)
        if rec is None:
            return KYAResult(False, "UNKNOWN_AGENT", f"{agent_id} is not registered")
        if rec.status is Status.REVOKED:
            return KYAResult(False, "AGENT_REVOKED", f"{agent_id} credential revoked")
        if rec.status is Status.SUSPENDED:
            return KYAResult(False, "AGENT_SUSPENDED", f"{agent_id} is suspended")
        if now >= rec.credential_expires:
            return KYAResult(False, "CREDENTIAL_EXPIRED", f"{agent_id} credential expired")
        principal = self._principals.get(rec.principal_id)
        if principal is None:
            return KYAResult(False, "PRINCIPAL_UNKNOWN", rec.principal_id)
        if not principal.kyb_verified or now >= principal.kyb_valid_until:
            return KYAResult(False, "PRINCIPAL_KYB_LAPSED", principal.legal_name)
        return KYAResult(True)
