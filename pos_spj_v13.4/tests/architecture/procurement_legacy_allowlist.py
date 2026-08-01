"""PUR-13.21 — temporary allowlist of legacy procurement code still in the tree.

Each entry is legacy that could NOT be deleted in a single iteration because it
still has live consumers OR carries business logic not yet migrated to the
canonical bounded context. Every entry states a concrete removal condition.

Rules (enforced by test_procurement_legacy_allowlist_only_shrinks):
- no entry without a justification, owner and removal_condition;
- the allowlist must only SHRINK across iterations (MAX_ENTRIES ratchets down);
- the phase is "done" only when the allowlist is empty.

This file is DATA + a monotonicity guard. It never grants the new bounded
context permission to touch legacy — the reinforcement guardrails scope to the
canonical procurement paths and always apply.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LegacyEntry:
    path: str
    reason: str
    owner: str
    created_at: str
    removal_condition: str
    classification: str  # WRAP_TEMPORARILY | BLOCKED | REWRITE


LEGACY_ALLOWLIST: tuple[LegacyEntry, ...] = (
    LegacyEntry(
        path="modulos/planeacion_compras.py",
        reason="Planeación pertenece a un alcance separado y aún emite necesidades.",
        owner="procurement-team",
        created_at="2026-07-17",
        removal_condition="Reconectar al intake canónico en la fase de Planeación.",
        classification="REWRITE"),
)

MAX_ENTRIES = 1
