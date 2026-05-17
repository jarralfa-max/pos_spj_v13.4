"""
application/purchases/purchase_order_uc.py
────────────────────────────────────────────
Casos de uso para Purchase Orders (PO).

Flujo:
  crear_desde_pr() → PO ABIERTA (desde PR aprobada)
  enviar_a_recepcion() → PO disponible para recepción en Tab QR
  cancelar() → PO CANCELADA

Reglas absolutas:
  - PO NO afecta inventario
  - PO NO genera asiento GL
  - PO NO genera CxP
  - La recepción (que SÍ afecta inventario) se maneja en Phase 4 via ReceivePOAdapter
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from application.purchases.states import POState

logger = logging.getLogger("spj.purchases.po_uc")

_VALID_TRANSITIONS: dict[str, set[str]] = {
    POState.ABIERTA:   {POState.PARCIAL, POState.RECIBIDA, POState.CANCELADA},
    POState.PARCIAL:   {POState.RECIBIDA, POState.CANCELADA},
    POState.RECIBIDA:  {POState.CERRADA},
    POState.CERRADA:   set(),
    POState.CANCELADA: set(),
}


@dataclass
class POResult:
    ok:       bool
    po_id:    int  = 0
    po_folio: str  = ""
    estado:   str  = ""
    error:    str  = ""


class PurchaseOrderUC:
    """
    Casos de uso de Purchase Order.
    Inyección de dependencias via AppContainer.
    """

    def __init__(self, container: Any):
        self._container = container

    @property
    def _repo(self):
        return self._container.purchase_order_repo

    # ── Crear PO desde PR ─────────────────────────────────────────────────────

    def crear_desde_pr(self, pr_id: int, pr_data: dict, usuario: str) -> POResult:
        """
        Crea una PO a partir de una PR aprobada.
        NO afecta inventario, GL ni CxP.
        """
        try:
            po_id, folio = self._repo.create_from_pr(pr_id, pr_data, usuario)
            self._audit("PO_CREADA", folio, usuario, pr_data.get("sucursal_id", 1),
                        after={"po_id": po_id, "pr_id": pr_id,
                               "total": pr_data.get("total", 0)})
            return POResult(ok=True, po_id=po_id, po_folio=folio, estado=POState.ABIERTA)
        except Exception as e:
            logger.error("crear_desde_pr PR=%d: %s", pr_id, e)
            return POResult(ok=False, error=str(e))

    # ── Enviar a recepción ────────────────────────────────────────────────────

    def enviar_a_recepcion(self, po_id: int, usuario: str) -> POResult:
        """
        Marca la PO como lista para recepción física.
        Estado sigue ABIERTA — la recepción real se ejecuta desde Tab QR (Phase 4).
        """
        po = self._repo.get_by_id(po_id)
        if not po:
            return POResult(ok=False, error=f"PO {po_id} no encontrada.")
        if po["estado"] not in (POState.ABIERTA, "borrador", "pendiente"):
            return POResult(
                ok=False,
                error=f"PO {po_id} no está en estado ABIERTA. Estado: {po['estado']}",
            )
        self._audit("PO_ENVIADA_A_RECEPCION", po["folio"], usuario,
                    po.get("sucursal_id", 1),
                    after={"po_id": po_id, "estado": "ABIERTA_PARA_RECEPCION"})
        return POResult(ok=True, po_id=po_id, po_folio=po["folio"], estado=POState.ABIERTA)

    # ── Cancelar PO ───────────────────────────────────────────────────────────

    def cancelar(self, po_id: int, usuario: str) -> POResult:
        """
        Cancela una PO. Solo si no ha sido recibida.
        NO revierte inventario porque la PO nunca lo afectó.
        """
        po = self._repo.get_by_id(po_id)
        if not po:
            return POResult(ok=False, error=f"PO {po_id} no encontrada.")
        if po["estado"] in (POState.RECIBIDA, POState.CERRADA):
            return POResult(
                ok=False,
                error=f"No se puede cancelar una PO en estado {po['estado']}.",
            )
        try:
            self._repo.update_estado(po_id, POState.CANCELADA)
            self._audit("PO_CANCELADA", po["folio"], usuario,
                        po.get("sucursal_id", 1),
                        after={"po_id": po_id, "estado": POState.CANCELADA})
            return POResult(ok=True, po_id=po_id, po_folio=po["folio"],
                            estado=POState.CANCELADA)
        except Exception as e:
            logger.error("cancelar PO %d: %s", po_id, e)
            return POResult(ok=False, error=str(e))

    # ── Consultas ─────────────────────────────────────────────────────────────

    def get_po(self, po_id: int) -> Optional[dict]:
        return self._repo.get_by_id(po_id)

    def listar_abiertas(self, sucursal_id: Optional[int] = None) -> list[dict]:
        return self._repo.list_open(sucursal_id)

    def get_lineas_esperadas(self, po_id: int) -> list[dict]:
        """Expone las líneas de PO para la recepción (Phase 4 / ReceivePOAdapter)."""
        po = self._repo.get_by_id(po_id)
        if not po:
            return []
        return po.get("items", [])

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _audit(self, accion: str, folio: str, usuario: str, sucursal_id: int,
               after: dict = None) -> None:
        try:
            from core.services.auto_audit import audit_write
            audit_write(
                self._container,
                modulo="COMPRAS_PO",
                accion=accion,
                entidad="ordenes_compra",
                entidad_id=folio,
                usuario=usuario,
                detalles=f"{accion} | {folio}",
                before={},
                after=after or {},
                sucursal_id=sucursal_id,
            )
        except Exception as e:
            logger.debug("PO audit_write: %s", e)
