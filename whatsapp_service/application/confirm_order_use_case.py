from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict


@dataclass
class ConfirmWhatsAppOrderCommand:
    phone: str
    cliente_id: int
    sucursal_id: int
    tipo_entrega: str
    direccion: str
    items: List[Dict]
    pedido_programado: bool = False


@dataclass
class ConfirmWhatsAppOrderResult:
    venta_id: int
    folio: str
    total: float
    anticipo_requerido: bool
    anticipo_monto: float


class ConfirmWhatsAppOrderUseCase:
    """
    Caso de uso de confirmación de pedido WA.
    El flow sólo conversa; las decisiones de negocio viven aquí/ERP.
    """

    def __init__(self, erp, orchestrator=None):
        self.erp = erp
        self.orchestrator = orchestrator

    def execute(self, cmd: ConfirmWhatsAppOrderCommand) -> ConfirmWhatsAppOrderResult:
        order = self.erp.crear_pedido_wa(
            items=cmd.items,
            cliente_id=cmd.cliente_id,
            sucursal_id=cmd.sucursal_id,
            tipo_entrega=cmd.tipo_entrega,
            direccion=cmd.direccion,
        )

        venta_id = int(order["venta_id"])
        folio = str(order["folio"])
        total = float(order["total"])

        anticipo_requerido = False
        anticipo_monto = 0.0

        if self.orchestrator:
            orch = self.orchestrator.procesar_pedido_wa(
                venta_id=venta_id,
                folio=folio,
                total=total,
                cliente_id=cmd.cliente_id,
                items=cmd.items,
                tipo_entrega=cmd.tipo_entrega,
                direccion=cmd.direccion,
            )
            anticipo_requerido = bool(orch.get("anticipo_requerido", False))
            anticipo_monto = float(orch.get("anticipo_monto", 0.0) or 0.0)
        else:
            anticipo_requerido = bool(
                self.erp.requiere_anticipo(cmd.cliente_id, total, cmd.pedido_programado)
            )
            # FASE 5: no hardcodear 50%; usar política ERP cuando no hay orquestador
            rules = self.erp.calcular_anticipo_rules(cmd.cliente_id, total, cmd.items)
            anticipo_monto = float(rules.get("monto", 0.0) or 0.0)

        return ConfirmWhatsAppOrderResult(
            venta_id=venta_id,
            folio=folio,
            total=total,
            anticipo_requerido=anticipo_requerido,
            anticipo_monto=anticipo_monto,
        )

