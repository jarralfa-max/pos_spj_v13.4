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
    # 2026-10-16: modulos/planeacion_compras.py se borró con modulos/; la lista queda vacía.
)

MAX_ENTRIES = 1
