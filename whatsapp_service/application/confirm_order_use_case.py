from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List

logger = logging.getLogger("wa.confirm_order")


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
    Caso de uso de confirmación de pedido WhatsApp.

    Responsabilidad:
    - El flow conversa y recolecta intención.
    - El caso de uso confirma el pedido contra el ERP.
    - La política de anticipo se consulta en el motor oficial del ERP.

    Nota arquitectónica:
    No se debe hardcodear 50% ni consultar columnas inventadas en WhatsApp.
    La migración v13 define `anticipo_reglas.pct_anticipo`, `monto_desde`
    y `monto_hasta`; por eso se delega a AnticipoCotizacionService cuando está
    disponible.
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
            policy = self._evaluate_advance_policy(cmd, total)
            anticipo_requerido = bool(policy.get("requiere", False))
            anticipo_monto = float(policy.get("monto", 0.0) or 0.0)

        return ConfirmWhatsAppOrderResult(
            venta_id=venta_id,
            folio=folio,
            total=total,
            anticipo_requerido=anticipo_requerido,
            anticipo_monto=anticipo_monto,
        )

    def _evaluate_advance_policy(self, cmd: ConfirmWhatsAppOrderCommand, total: float) -> Dict[str, Any]:
        """Evalúa anticipo con el servicio oficial del ERP y fallbacks seguros.

        Orden:
        1. Respetar `requiere_anticipo` si existe en ERPBridge.
        2. Usar `core.services.anticipo_service.AnticipoCotizacionService`.
        3. Usar método legacy `erp.calcular_anticipo_rules` si es compatible.
        4. Fallback defensivo usando `anticipo_config.pct_default`.
        """
        try:
            if hasattr(self.erp, "requiere_anticipo"):
                requiere = bool(self.erp.requiere_anticipo(
                    cmd.cliente_id, total, cmd.pedido_programado
                ))
                if not requiere:
                    return {"requiere": False, "monto": 0.0, "razon": "politica_erp_exenta"}
        except Exception as exc:
            logger.warning("No se pudo evaluar requiere_anticipo; se usará política completa: %s", exc)

        # Camino profesional: motor oficial de anticipos del ERP v13.
        try:
            from core.services.anticipo_service import AnticipoCotizacionService

            items = self._items_for_advance_policy(cmd.items)
            info = AnticipoCotizacionService(self.erp.db).calcular(
                total=total,
                items=items,
                cliente_id=cmd.cliente_id,
            )
            if isinstance(info, dict):
                return info
        except Exception as exc:
            logger.warning("AnticipoCotizacionService no disponible/compatible: %s", exc)

        # Compatibilidad temporal con implementaciones antiguas del bridge.
        try:
            if hasattr(self.erp, "calcular_anticipo_rules"):
                info = self.erp.calcular_anticipo_rules(cmd.cliente_id, total, cmd.items)
                if isinstance(info, dict):
                    return info
        except Exception as exc:
            logger.warning("calcular_anticipo_rules legacy falló; se usará fallback defensivo: %s", exc)

        pct = self._get_default_advance_pct(default=30.0)
        return {
            "requiere": pct > 0,
            "pct": pct,
            "monto": round(total * pct / 100.0, 2),
            "razon": "fallback_pct_default",
            "exento": pct <= 0,
        }

    def _items_for_advance_policy(self, items: List[Dict]) -> List[Dict]:
        """Enriquece items para AnticipoCotizacionService sin cambiar el flow."""
        enriched: List[Dict] = []
        for item in items:
            row = dict(item)
            cantidad = float(row.get("cantidad", 0) or 0)
            precio = float(row.get("precio_unitario", 0) or 0)
            row.setdefault("subtotal", round(cantidad * precio, 2))

            if not row.get("categoria") and row.get("producto_id"):
                try:
                    prod = self.erp.db.execute(
                        "SELECT COALESCE(categoria, '') FROM productos WHERE id=?",
                        (row.get("producto_id"),),
                    ).fetchone()
                    if prod:
                        row["categoria"] = prod[0] or ""
                except Exception:
                    row.setdefault("categoria", "")
            enriched.append(row)
        return enriched

    def _get_default_advance_pct(self, default: float = 30.0) -> float:
        try:
            row = self.erp.db.execute(
                "SELECT valor FROM anticipo_config WHERE clave='pct_default' LIMIT 1"
            ).fetchone()
            if row and row[0] is not None:
                return float(row[0])
        except Exception:
            pass
        return float(default)
