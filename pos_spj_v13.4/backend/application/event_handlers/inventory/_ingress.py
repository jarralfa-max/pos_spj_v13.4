"""Shared ingress-contract resolution for inventory event handlers (P1-A / §5).

Every context that drives a stock effect (Ventas, Compras, Producción, Merma,
devoluciones) sends its event through the canonical inventory handlers. Those
handlers must resolve the envelope **fail-closed**, honoring the non-negotiable
rules:

* the actor identity comes from the event — never fabricated as ``"system"``;
* the warehouse comes from the event — never defaulted to ``branch_id``
  (a warehouse is not a branch);
* branch and operation_id are mandatory.

When any required field is missing the event is *not* processed with invented
data: ``resolve_ingress`` returns ``(None, reason)`` and the caller skips it
(logging the reason) instead of posting a movement with a fabricated identity.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InventoryIngress:
    operation_id: str
    branch_id: str
    warehouse_id: str
    actor_user_id: str
    document_id: str


def resolve_ingress(payload: dict) -> tuple[InventoryIngress | None, str]:
    """Resolve and validate the inventory ingress envelope from an event payload.

    Returns ``(ingress, "")`` when valid, or ``(None, reason)`` when a required
    field is missing — never fabricating a warehouse (from branch) or an actor
    (``"system"``)."""
    operation_id = str(payload.get("operation_id") or payload.get("event_id") or "").strip()
    branch_id = str(payload.get("branch_id") or "").strip()
    # Sin fallback a branch_id: un almacén no es una sucursal (§5).
    warehouse_id = str(payload.get("warehouse_id") or "").strip()
    # Sin identidad inventada "system": el actor debe venir en el evento (§5.4).
    actor_user_id = str(payload.get("user_id") or payload.get("user")
                        or payload.get("usuario") or "").strip()
    document_id = str(payload.get("document_id") or "").strip()

    missing = [name for name, value in (
        ("operation_id", operation_id), ("branch_id", branch_id),
        ("warehouse_id", warehouse_id), ("actor_user_id", actor_user_id),
    ) if not value]
    if missing:
        return None, "faltan campos obligatorios: " + ", ".join(missing)
    return InventoryIngress(operation_id=operation_id, branch_id=branch_id,
                            warehouse_id=warehouse_id, actor_user_id=actor_user_id,
                            document_id=document_id), ""
