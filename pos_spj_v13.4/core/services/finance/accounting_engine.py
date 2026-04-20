# core/services/finance/accounting_engine.py — SPJ ERP
"""
AccountingEngine — Motor de Contabilidad de Doble Entrada.

Reacciona a eventos de dominio y crea asientos contables en financial_event_log.
Prioridad 48 (< 50 de _wire_venta_financiero existente) para orden determinístico.

NO controla el flujo — solo reacciona.
Si falla, NO cancela la operación original.

Cuentas SAT:
  Ventas:   1100 (caja/clientes) DEBE  /  4100 (ventas) HABER
  Compras:  5100 (costo mercancía) DEBE  /  2100 (cuentas por pagar) HABER
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.services.enterprise.finance_service import FinanceService

logger = logging.getLogger("spj.accounting_engine")

_PRIORITY = 48


class AccountingEngine:
    """Suscriptor del EventBus que genera asientos de doble entrada."""

    def __init__(self, finance_service: "FinanceService"):
        self._fs = finance_service
        self._subscribed = False

    def wire(self) -> None:
        """Registra los handlers en el EventBus. Idempotente."""
        if self._subscribed:
            return
        from core.events.event_bus import get_bus
        from core.events.domain_events import SALE_CREATED, PURCHASE_CREATED

        bus = get_bus()
        bus.subscribe(SALE_CREATED, self.handle_sale,
                      priority=_PRIORITY, label="accounting.sale")
        bus.subscribe(PURCHASE_CREATED, self.handle_purchase,
                      priority=_PRIORITY, label="accounting.purchase")
        self._subscribed = True
        logger.info("AccountingEngine wired (prio=%d)", _PRIORITY)

    def handle_sale(self, data: dict) -> None:
        """SALE_CREATED → Débito caja (1100) / Crédito ventas (4100)."""
        try:
            total = float(data.get("total", 0))
            if total <= 0:
                return
            self._fs.registrar_asiento(
                debe="1100",
                haber="4100",
                concepto=f"Venta #{data.get('folio', data.get('venta_id', ''))}",
                monto=total,
                modulo="ventas",
                referencia_id=data.get("venta_id"),
                usuario_id=data.get("usuario_id"),
                sucursal_id=int(data.get("sucursal_id", 1)),
                evento="SALE_CREATED",
                metadata={
                    "folio": data.get("folio"),
                    "cliente_id": data.get("cliente_id"),
                    "metodo_pago": data.get("metodo_pago", data.get("forma_pago")),
                },
            )
        except Exception as e:
            logger.warning("handle_sale non-fatal: %s", e)

    def handle_purchase(self, data: dict) -> None:
        """PURCHASE_CREATED → Débito costo (5100) / Crédito CXP (2100)."""
        try:
            total = float(data.get("total", data.get("monto", 0)))
            if total <= 0:
                return
            self._fs.registrar_asiento(
                debe="5100",
                haber="2100",
                concepto=f"Compra #{data.get('compra_id', '')} proveedor {data.get('proveedor_id', '')}",
                monto=total,
                modulo="compras",
                referencia_id=data.get("compra_id"),
                usuario_id=data.get("usuario_id"),
                sucursal_id=int(data.get("sucursal_id", 1)),
                evento="PURCHASE_CREATED",
                metadata={
                    "proveedor_id": data.get("proveedor_id"),
                    "items_count": len(data.get("items", [])),
                },
            )
        except Exception as e:
            logger.warning("handle_purchase non-fatal: %s", e)
