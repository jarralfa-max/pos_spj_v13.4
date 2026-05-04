# core/events/event_factory.py — SPJ ERP v13.4  Phase 1
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
        "operation_id":   operation_id,
        # Spanish aliases (legacy handlers & WA bridge)
        "venta_id":       sale_id,
        "sucursal_id":    branch_id,
        "usuario":        user,
        "cliente_id":     client_id,
    }
