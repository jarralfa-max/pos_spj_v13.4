"""
application/purchases/traditional_purchase_uc.py
─────────────────────────────────────────────────
Caso de uso oficial: Compra Tradicional (ruta canónica Phase 2+).

RUTA CANÓNICA POR document_type:

  DIRECT → RegistrarCompraUC → PurchaseService → EventBus (inventario + GL)
  PR     → PurchaseRequestUC.crear_pr()         [Phase 3]
  PO     → PurchaseOrderUC.crear_desde_pr()     [Phase 3, requiere pr_id]

ProcesarCompraUC (core/use_cases/compra.py) queda DEPRECATED.
No llamar ProcesarCompraUC desde código nuevo — usar este UC en su lugar.

Phase 4: recibirá po_id y enrutará al adaptador de recepción.
"""
from __future__ import annotations

import logging
from typing import Any

from application.purchases.commands import RegisterPurchaseCommand
from application.purchases.results import PurchaseResult
from application.purchases.states import DocumentType, PRState

logger = logging.getLogger("spj.purchases.traditional_uc")


class TraditionalPurchaseUC:
    """
    Punto de entrada oficial para compras tradicionales.

    Dependencias inyectadas vía AppContainer:
        uc = TraditionalPurchaseUC(container)
        result = uc.execute(command)
    """

    def __init__(self, container: Any):
        self._container = container

    # ── API pública ───────────────────────────────────────────────────────────

    def execute(self, command: RegisterPurchaseCommand) -> PurchaseResult:
        """Enruta al flujo correcto según document_type."""
        if not command.items:
            return PurchaseResult.error_result("El carrito está vacío.")

        if command.document_type == DocumentType.DIRECT:
            return self._execute_direct(command)
        elif command.document_type == DocumentType.PR:
            return self._execute_pr(command)
        elif command.document_type == DocumentType.PO:
            return self._execute_po(command)
        else:
            return PurchaseResult.error_result(
                f"document_type desconocido: {command.document_type}"
            )

    # ── Ruta DIRECT ───────────────────────────────────────────────────────────

    def _execute_direct(self, command: RegisterPurchaseCommand) -> PurchaseResult:
        """
        Compra directa: delega a RegistrarCompraUC.
        No reimplementa inventario, GL, CxP ni auditoría.
        """
        from application.use_cases.registrar_compra_uc import RegistrarCompraUC
        try:
            datos_dto = command.to_datos_compra_dto()
        except Exception as e:
            logger.error("TraditionalPurchaseUC: conversión de comando fallida: %s", e)
            return PurchaseResult.error_result(f"Error en datos de compra: {e}")
        resultado = RegistrarCompraUC(self._container).execute(datos_dto)
        return PurchaseResult.from_resultado_dto(resultado, document_type=DocumentType.DIRECT)

    # ── Ruta PR ───────────────────────────────────────────────────────────────

    def _execute_pr(self, command: RegisterPurchaseCommand) -> PurchaseResult:
        """
        Crea Purchase Request. NO afecta inventario, GL ni CxP.
        Estado inicial determinado por command.pr_estado_inicial (BORRADOR o PENDIENTE).
        """
        from application.purchases.purchase_request_uc import PurchaseRequestUC
        pr_uc = PurchaseRequestUC(self._container)
        estado_inicial = getattr(command, "pr_estado_inicial", PRState.BORRADOR)
        result = pr_uc.crear_pr(command, estado_inicial=estado_inicial)
        if not result.ok:
            return PurchaseResult.error_result(result.error)
        return PurchaseResult(
            ok=True,
            folio=result.folio,
            document_type=DocumentType.PR,
            audit_after={"pr_id": result.pr_id, "estado": result.estado},
        )

    # ── Ruta PO ───────────────────────────────────────────────────────────────

    def _execute_po(self, command: RegisterPurchaseCommand) -> PurchaseResult:
        """
        Convierte PR aprobada en PO. Requiere command.po_id con el pr_id origen.
        NO afecta inventario, GL ni CxP.
        """
        from application.purchases.purchase_request_uc import PurchaseRequestUC
        pr_uc = PurchaseRequestUC(self._container)

        pr_id = command.po_id  # po_id field re-used as source pr_id for conversion
        if not pr_id:
            return PurchaseResult.error_result(
                "Para crear PO se requiere po_id (id de la PR aprobada)."
            )

        result = pr_uc.convertir_a_po(pr_id=pr_id, usuario=command.usuario)
        if not result.ok:
            return PurchaseResult.error_result(result.error)
        return PurchaseResult(
            ok=True,
            folio=result.po_folio,
            document_type=DocumentType.PO,
            audit_after={"po_id": result.po_id, "pr_id": pr_id},
        )
