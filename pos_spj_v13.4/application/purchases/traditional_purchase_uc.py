"""
application/purchases/traditional_purchase_uc.py
─────────────────────────────────────────────────
Caso de uso oficial: Compra Tradicional (ruta canónica Phase 2+).

RUTA CANÓNICA:
    UI → TraditionalPurchaseUC.execute(RegisterPurchaseCommand)
           → RegistrarCompraUC.execute(DatosCompraDTO)   [delegado]
             → PurchaseService.register_purchase()
               → PURCHASE_ITEMS_PROCESS  (inventario, sync, priority=100)
               → PURCHASE_CREATED        (finanzas GL, async, priority=80)

ProcesarCompraUC (core/use_cases/compra.py) queda DEPRECATED.
No llamar ProcesarCompraUC desde código nuevo — usar este UC en su lugar.

Phase 3: este UC recibirá document_type=PR|PO y enrutará al servicio documental.
Phase 4: recibirá po_id y enrutará al adaptador de recepción.
"""
from __future__ import annotations

import logging
from typing import Any

from application.purchases.commands import RegisterPurchaseCommand
from application.purchases.results import PurchaseResult
from application.purchases.states import DocumentType

logger = logging.getLogger("spj.purchases.traditional_uc")


class TraditionalPurchaseUC:
    """
    Punto de entrada oficial para compras tradicionales.

    Dependencias inyectadas vía AppContainer:
        uc = TraditionalPurchaseUC(container)
        result = uc.execute(command)

    Phase 2: solo soporta document_type=DIRECT.
    Phase 3: enrutará PR/PO al servicio documental.
    """

    def __init__(self, container: Any):
        self._container = container

    # ── API pública ───────────────────────────────────────────────────────────

    def execute(self, command: RegisterPurchaseCommand) -> PurchaseResult:
        """
        Ejecuta el flujo de compra tradicional según el tipo de documento.

        Phase 2: document_type=DIRECT → delega a RegistrarCompraUC.
        Phase 3: document_type=PR|PO → enruta al servicio documental (pendiente).
        """
        if not command.items:
            return PurchaseResult.error_result("El carrito está vacío.")

        if command.document_type != DocumentType.DIRECT:
            return PurchaseResult.error_result(
                f"document_type={command.document_type} no está implementado aún "
                f"(disponible en Phase 3). Use DIRECT para compras actuales."
            )

        return self._execute_direct(command)

    # ── Rutas internas ────────────────────────────────────────────────────────

    def _execute_direct(self, command: RegisterPurchaseCommand) -> PurchaseResult:
        """
        Compra directa: delega a RegistrarCompraUC (ruta canónica actual).
        No reimplementa lógica de inventario, GL, CxP ni auditoría.
        """
        from application.use_cases.registrar_compra_uc import RegistrarCompraUC

        try:
            datos_dto = command.to_datos_compra_dto()
        except Exception as e:
            logger.error("TraditionalPurchaseUC: conversión de comando fallida: %s", e)
            return PurchaseResult.error_result(f"Error en datos de compra: {e}")

        resultado = RegistrarCompraUC(self._container).execute(datos_dto)
        return PurchaseResult.from_resultado_dto(resultado, document_type=DocumentType.DIRECT)
