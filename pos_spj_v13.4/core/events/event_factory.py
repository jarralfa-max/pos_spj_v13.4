# core/events/event_factory.py — SPJ ERP v13.4  Phase 1 + FASE 8
"""
Canonical payload factories for domain events.

Rules:
  - Every event that crosses a service boundary uses one of these factories.
  - Factory functions are pure (no side effects, no DB access).
  - Dual-key payloads (sale_id/venta_id, branch_id/sucursal_id) keep backward
    compatibility with legacy handlers that expect Spanish-named keys.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def make_sale_payload(
    *,
    sale_id: int,
    folio: str,
    branch_id: int,
    total: float,
    user: str,
    client_id: Optional[int],
    items: List[Dict[str, Any]],
    payment_method: str,
    operation_id: str,
    amount_paid: float = 0.0,
    payment_breakdown: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build the canonical payload for SALE_ITEMS_PROCESS and VENTA_COMPLETADA events.

    Both Spanish (legacy) and English keys are included so that old handlers
    (wiring.py, WA bridge) and new handlers (inventory_handler, finance_handler)
    can consume the same payload without conversion.
    """
    return {
        # English keys (new handlers)
        "sale_id":        sale_id,
        "folio":          folio,
        "branch_id":      branch_id,
        "total":          total,
        "user":           user,
        "client_id":      client_id,
        "items":          items,
        "payment_method": payment_method,
        "amount_paid":    amount_paid,
        "payment_breakdown": dict(payment_breakdown or {}),
        "operation_id":   operation_id,
        # Spanish aliases (legacy handlers & WA bridge)
        "venta_id":       sale_id,
        "sucursal_id":    branch_id,
        "usuario":        user,
        "cliente_id":     client_id,
    }


def make_produccion_completada_payload(
    *,
    # Identity — at least one must be non-None
    batch_id: Optional[str] = None,
    produccion_id: Optional[int] = None,

    # Reference
    folio: str,
    operation_id: str,

    # Context
    sucursal_id: int,
    usuario: str,
    receta_id: Optional[int] = None,
    receta_nombre: Optional[str] = None,

    # Yield summary
    rendimiento_pct: float = 0.0,
    total_generado: float = 0.0,
    total_consumido: float = 0.0,
    total_merma: float = 0.0,
    waste_pct: float = 0.0,

    # Inventory movement lists
    raw_materials: Optional[List[Dict[str, Any]]] = None,
    outputs: Optional[List[Dict[str, Any]]] = None,

    # Cost data (computed by publisher — handler uses without querying DB)
    raw_material_cost: float = 0.0,
    finished_goods_cost: float = 0.0,
    waste_cost: float = 0.0,
) -> Dict[str, Any]:
    """
    Build the canonical payload for PRODUCCION_COMPLETADA.

    Both production paths (RecipeEngine and GestionarProduccionUC/ProductionEngine)
    use this factory so subscribers always receive a consistent, self-describing
    payload regardless of which path triggered the event.

    Canonical structure:
      batch_id / produccion_id  — identity (one per path)
      folio / operation_id      — human ref and idempotency key
      sucursal_id / branch_id   — dual-key for legacy compatibility
      usuario                   — triggering user
      receta_id / receta_nombre — recipe context (may be None for batch path)
      rendimiento_pct           — usable yield percentage
      yields{}                  — detailed yield breakdown
      raw_materials[]           — list of inputs consumed
      outputs[]                 — list of outputs produced
      costs{}                   — financial summary (zero if not computed)

    ProductionFinanceHandler reads costs.raw_material_cost /
    costs.finished_goods_cost / costs.waste_cost directly from this payload
    before falling back to the DB.
    """
    return {
        # Identity
        "batch_id":       batch_id,
        "produccion_id":  produccion_id,
        # Reference
        "folio":          folio,
        "operation_id":   operation_id,
        # Context (dual-key)
        "sucursal_id":    sucursal_id,
        "branch_id":      sucursal_id,
        "usuario":        usuario,
        "receta_id":      receta_id,
        "receta_nombre":  receta_nombre,
        # Yield
        "rendimiento_pct": rendimiento_pct,
        "yields": {
            "usable_pct":      rendimiento_pct,
            "waste_pct":       waste_pct,
            "total_generado":  total_generado,
            "total_consumido": total_consumido,
            "total_merma":     total_merma,
        },
        # Movements
        "raw_materials": raw_materials or [],
        "outputs":       outputs or [],
        # Costs (zero when publisher did not compute them — handler queries DB)
        "costs": {
            "raw_material_cost":   round(raw_material_cost, 4),
            "finished_goods_cost": round(finished_goods_cost, 4),
            "waste_cost":          round(waste_cost, 4),
        },
    }
