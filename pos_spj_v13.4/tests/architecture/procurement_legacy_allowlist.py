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
        reason="Planeación/forecast de compras cableada en main_window.py "
               "(PLANEACION_COMPRAS); emite necesidades pero aún no usa el intake "
               "canónico de reabasto.",
        owner="procurement-team",
        created_at="2026-07-17",
        removal_condition="Reconectar su salida al ReplenishmentIntakeHandler "
                          "(PUR-11) y mover la UI al módulo enterprise; luego borrar.",
        classification="REWRITE"),
    LegacyEntry(
        path="backend/infrastructure/db/repositories/compras_read_repository.py",
        reason="Repositorio de lectura legacy. El monolito (compras_pro.py) ya se "
               "borró; sólo lo consumen tests (test_catalog_hot_refresh, "
               "tests/unit/test_compras_read_repository) que aún cubren catálogo/"
               "sucursales legacy.",
        owner="procurement-team",
        created_at="2026-07-17",
        removal_condition="Migrar esos tests a los read services canónicos de "
                          "backend/application/procurement/queries/ y borrar el repo.",
        classification="WRAP_TEMPORARILY"),
    LegacyEntry(
        path="backend/infrastructure/db/repositories/compras_write_repository.py",
        reason="Repositorio de escritura legacy (mutaciones de compra). El monolito "
               "(compras_pro.py) ya se borró; sólo lo consume "
               "tests/unit/test_compras_write_repository.",
        owner="procurement-team",
        created_at="2026-07-17",
        removal_condition="Migrar ese test a los casos de uso canónicos de "
                          "backend/application/procurement/ y borrar el repo.",
        classification="WRAP_TEMPORARILY"),
    LegacyEntry(
        path="repositories/purchase_repository.py",
        reason="Repositorio de compras legacy (IDs enteros) consumido por flujos "
               "antiguos.",
        owner="procurement-team",
        created_at="2026-07-17",
        removal_condition="Verificar cero consumidores fuera del monolito y borrar.",
        classification="BLOCKED"),
    LegacyEntry(
        path="repositories/purchase_order_repository.py",
        reason="Repositorio de órdenes legacy; reemplazado por "
               "PurchaseOrderRepository canónico.",
        owner="procurement-team",
        created_at="2026-07-17",
        removal_condition="Verificar cero consumidores y borrar.",
        classification="BLOCKED"),
    LegacyEntry(
        path="repositories/purchase_request_repository.py",
        reason="Repositorio de solicitudes legacy; reemplazado por "
               "PurchaseRequisitionRepository canónico.",
        owner="procurement-team",
        created_at="2026-07-17",
        removal_condition="Verificar cero consumidores y borrar.",
        classification="BLOCKED"),
)

#: Monotonic ratchet: the allowlist may only shrink. Lower this as entries go.
MAX_ENTRIES = 6
