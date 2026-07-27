"""
application/purchases/purchase_request_uc.py
─────────────────────────────────────────────
Casos de uso para Purchase Requests (PR).

Flujo:
  crear_pr()         → BORRADOR
  enviar_aprobacion()→ PENDIENTE_APROBACION
  aprobar()          → APROBADA
  rechazar()         → RECHAZADA
  convertir_a_po()   → CONVERTIDA_A_PO  (delega a PurchaseOrderUC)
  cancelar()         → CANCELADA

Reglas absolutas:
  - PR NO afecta inventario
  - PR NO genera asiento GL
  - PR NO genera CxP
  - Solo roles con permiso 'aprobar_pr' pueden aprobar/rechazar
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from application.purchases.states import PRState

logger = logging.getLogger("spj.purchases.pr_uc")

# Transiciones válidas de estado
_VALID_TRANSITIONS: dict[str, set[str]] = {
    PRState.BORRADOR:             {PRState.PENDIENTE_APROBACION, PRState.CANCELADA},
    PRState.PENDIENTE_APROBACION: {PRState.APROBADA, PRState.RECHAZADA, PRState.CANCELADA},
    PRState.APROBADA:             {PRState.CONVERTIDA_A_PO, PRState.CANCELADA},
    PRState.RECHAZADA:            {PRState.BORRADOR},          # permite re-editar
    PRState.CONVERTIDA_A_PO:      set(),                       # terminal
    PRState.CANCELADA:            set(),                       # terminal
}


@dataclass
class PRResult:
    ok:     bool
    pr_id:  int    = 0
    folio:  str    = ""
    estado: str    = ""
    error:  str    = ""
    po_id:  int    = 0
    po_folio: str  = ""


class PurchaseRequestUC:
    """
    Casos de uso de Purchase Request.
    Inyección de dependencias via AppContainer.
    """

    def __init__(self, container: Any):
        self._container = container

    @property
    def _repo(self):
        return self._container.purchase_request_repo

    # ── Crear PR ──────────────────────────────────────────────────────────────

    def crear_pr(self, command, estado_inicial: str = PRState.BORRADOR) -> PRResult:
        """
        Crea una Purchase Request en estado BORRADOR o PENDIENTE_APROBACION.
        command debe ser RegisterPurchaseCommand.
        NO afecta inventario, GL ni CxP.
        """
        if not command.items:
            return PRResult(ok=False, error="El carrito está vacío.")

        items_dicts = [
            {
                "product_id": i.product_id,
                "qty":        round(float(i.qty), 6),
                "unit_cost":  round(float(i.unit_cost), 6),
                "nombre":     i.nombre,
                "lote":       i.lote,
                "fecha_caducidad": i.fecha_caducidad,
            }
            for i in command.items
        ]

        try:
            pr_id, folio = self._repo.create(
                proveedor_id=command.proveedor_id,
                proveedor_nombre=command.proveedor_nombre,
                sucursal_id=command.sucursal_id,
                usuario=command.usuario,
                items=items_dicts,
                metodo_pago=command.metodo_pago,
                subtotal=command.subtotal,
                iva_monto=command.iva_monto,
                total=command.total,
                condicion_pago=command.condicion_pago,
                plazo_dias=command.plazo_dias,
                moneda=command.moneda,
                notas=command.notas,
                doc_ref=command.doc_ref,
                estado=estado_inicial,
            )
            self._audit("PR_CREADA", folio, command.usuario, command.sucursal_id,
                        after={"pr_id": pr_id, "estado": estado_inicial, "total": command.total})
            return PRResult(ok=True, pr_id=pr_id, folio=folio, estado=estado_inicial)
        except Exception as e:
            logger.error("crear_pr: %s", e)
            return PRResult(ok=False, error=str(e))

    # ── Transiciones de estado ────────────────────────────────────────────────

    def enviar_aprobacion(self, pr_id: int, usuario: str) -> PRResult:
        return self._transicion(pr_id, PRState.PENDIENTE_APROBACION, usuario,
                                accion="PR_ENVIADA_APROBACION")

    def aprobar(self, pr_id: int, aprobador: str) -> PRResult:
        return self._transicion(pr_id, PRState.APROBADA, aprobador,
                                accion="PR_APROBADA")

    def rechazar(self, pr_id: int, aprobador: str, motivo: str) -> PRResult:
        return self._transicion(pr_id, PRState.RECHAZADA, aprobador,
                                motivo=motivo, accion="PR_RECHAZADA")

    def cancelar(self, pr_id: int, usuario: str) -> PRResult:
        return self._transicion(pr_id, PRState.CANCELADA, usuario,
                                accion="PR_CANCELADA")

    def reabrir(self, pr_id: int, usuario: str) -> PRResult:
        """Pasa RECHAZADA → BORRADOR para re-edición."""
        return self._transicion(pr_id, PRState.BORRADOR, usuario,
                                accion="PR_REABIERTA")

    # ── Convertir a PO ────────────────────────────────────────────────────────

    def convertir_a_po(self, pr_id: int, usuario: str) -> PRResult:
        """
        Convierte una PR aprobada en PO.
        Delega la creación de PO a PurchaseOrderUC.
        """
        pr = self._repo.get_by_id(pr_id)
        if not pr:
            return PRResult(ok=False, error=f"PR {pr_id} no encontrada.")
        if pr["estado"] != PRState.APROBADA:
            return PRResult(
                ok=False,
                error=f"Solo se puede convertir una PR en estado APROBADA. "
                      f"Estado actual: {pr['estado']}",
            )

        # Delegar creación de PO
        po_uc = PurchaseOrderUC(self._container)
        po_result = po_uc.crear_desde_pr(pr_id, pr, usuario)
        if not po_result.ok:
            return PRResult(ok=False, error=f"Error al crear PO: {po_result.error}")

        # Marcar PR como convertida
        self._repo.update_estado(pr_id, PRState.CONVERTIDA_A_PO, usuario=usuario)
        self._audit("PR_CONVERTIDA_A_PO", pr["folio"], usuario,
                    pr.get("sucursal_id", 1),
                    after={"po_id": po_result.po_id, "po_folio": po_result.po_folio})

        return PRResult(
            ok=True,
            pr_id=pr_id,
            folio=pr["folio"],
            estado=PRState.CONVERTIDA_A_PO,
            po_id=po_result.po_id,
            po_folio=po_result.po_folio,
        )

    # ── Consultas ─────────────────────────────────────────────────────────────

    def get_pr(self, pr_id: int) -> Optional[dict]:
        return self._repo.get_by_id(pr_id)

    def listar_pendientes(self, sucursal_id: Optional[int] = None) -> list[dict]:
        return self._repo.list_pending(sucursal_id)

    def listar_aprobadas(self, sucursal_id: Optional[int] = None) -> list[dict]:
        return self._repo.list_approved(sucursal_id)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _transicion(self, pr_id: int, nuevo_estado: str, usuario: str,
                    motivo: str = "", accion: str = "PR_ESTADO_CAMBIADO") -> PRResult:
        pr = self._repo.get_by_id(pr_id)
        if not pr:
            return PRResult(ok=False, error=f"PR {pr_id} no encontrada.")

        estado_actual = pr["estado"]
        permitidos = _VALID_TRANSITIONS.get(estado_actual, set())
        if nuevo_estado not in permitidos:
            return PRResult(
                ok=False,
                error=f"Transición inválida: {estado_actual} → {nuevo_estado}. "
                      f"Permitidas: {sorted(permitidos) or 'ninguna (estado terminal)'}",
            )

        try:
            self._repo.update_estado(pr_id, nuevo_estado, usuario=usuario, motivo=motivo)
            self._audit(accion, pr["folio"], usuario,
                        pr.get("sucursal_id", 1),
                        after={"estado": nuevo_estado, "motivo": motivo})
            return PRResult(ok=True, pr_id=pr_id, folio=pr["folio"], estado=nuevo_estado)
        except Exception as e:
            logger.error("_transicion PR %d %s→%s: %s", pr_id, estado_actual, nuevo_estado, e)
            return PRResult(ok=False, error=str(e))

    def _audit(self, accion: str, folio: str, usuario: str, sucursal_id: int,
               after: dict = None) -> None:
        try:
            from core.services.auto_audit import audit_write
            audit_write(
                self._container,
                modulo="COMPRAS_PR",
                accion=accion,
                entidad="purchase_requests",
                entidad_id=folio,
                usuario=usuario,
                detalles=f"{accion} | {folio}",
                before={},
                after=after or {},
                sucursal_id=sucursal_id,
            )
        except Exception as e:
            logger.debug("PR audit_write: %s", e)


# ── PurchaseOrderUC (importado aquí para evitar ciclos) ───────────────────────
from application.purchases.purchase_order_uc import PurchaseOrderUC  # noqa: E402
