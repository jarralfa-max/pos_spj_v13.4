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
        path="modulos/compras_pro.py",
        reason="Monolito de Compras (7,362 líneas) cableado en main_window.py y "
               "menu_lateral.py; contiene lógica aún NO migrada (recepción QR, "
               "plantillas de compra, alertas de variación de costo, procesamiento "
               "de recetas) y está protegido por ~20 tests de comportamiento.",
        owner="procurement-team",
        created_at="2026-07-17",
        removal_condition="Migrar recepción QR, plantillas de compra y alertas de "
                          "costo al bounded context; repuntar la navegación COMPRAS "
                          "al módulo enterprise; verificar cero consumidores (13.22); "
                          "reescribir los ~20 tests contra contratos canónicos.",
        classification="BLOCKED"),
    LegacyEntry(
        path="modulos/compras/",
        reason="Widgets de UI (actions_bar, items_table, proveedor_panel, "
               "totals_panel) extraídos de compras_pro.py; sólo se consumen desde "
               "el monolito.",
        owner="procurement-team",
        created_at="2026-07-17",
        removal_condition="Se eliminan junto con compras_pro.py una vez repuntada "
                          "la navegación al módulo enterprise.",
        classification="WRAP_TEMPORARILY"),
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
        reason="Repositorio de lectura legacy consumido por compras_pro.py.",
        owner="procurement-team",
        created_at="2026-07-17",
        removal_condition="Eliminar con compras_pro.py; las lecturas ya existen en "
                          "backend/application/procurement/queries/.",
        classification="WRAP_TEMPORARILY"),
    LegacyEntry(
        path="backend/infrastructure/db/repositories/compras_write_repository.py",
        reason="Repositorio de escritura legacy (mutaciones de compra) consumido "
               "por compras_pro.py.",
        owner="procurement-team",
        created_at="2026-07-17",
        removal_condition="Eliminar con compras_pro.py; las mutaciones ya existen "
                          "como casos de uso en backend/application/procurement/.",
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
MAX_ENTRIES = 8
