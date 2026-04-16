# core/services/sales/unified_sales_service.py — DEPRECADO en v13.1
# Shim de compatibilidad → redirige a ProcesarVentaUC
import warnings, logging
warnings.warn(
    "UnifiedSalesService está deprecado. Usa core.use_cases.ProcesarVentaUC.",
    DeprecationWarning, stacklevel=2
)
logger = logging.getLogger("spj.sales.unified")

# Re-exportar DTOs para compatibilidad con tests y cotizacion_service
from dataclasses import dataclass, field
from typing import Optional


class VentaError(Exception):
    """Error base de venta legacy (compatibilidad con test suite histórica)."""


class CarritoVacioError(VentaError):
    """Se intentó procesar una venta sin ítems."""


class PagoInsuficienteError(VentaError):
    """El monto pagado no cubre el total."""


class StockError(VentaError):
    """No hay stock suficiente para uno o más ítems."""

@dataclass
class ItemVenta:
    producto_id:   int
    cantidad:      float
    precio_unitario: float
    nombre:        str   = ""
    descuento_pct: float = 0.0
    unidad:        str   = "pza"

    @property
    def subtotal(self):
        return round(self.cantidad * self.precio_unitario * (1 - self.descuento_pct/100), 4)

    # Alias for compatibility
    @property
    def precio_unit(self): return self.precio_unitario

@dataclass
class DatosPago:
    forma_pago:       str   = "Efectivo"
    efectivo_recibido: float = 0.0
    cliente_id:       Optional[int] = None
    puntos_usar:      int   = 0
    descuento_global: float = 0.0

@dataclass
class ResultadoVenta:
    venta_id:      int
    folio:         str
    total:         float
    cambio:        float
    puntos_ganados: int  = 0
    ticket_data:   dict  = field(default_factory=dict)


class UnifiedSalesService:
    """DEPRECADO — proxy a ProcesarVentaUC."""

    def __init__(self, conn=None, usuario="cajero", branch_id=1):
        self.conn      = conn
        self.usuario   = usuario
        self.branch_id = branch_id

    def procesar_venta(self, items, datos_pago, usuario=None, **kw):
        from core.use_cases.venta import ProcesarVentaUC, ItemCarrito, DatosPago as DP
        from core.services.inventory_service import InventoryService
        usr = usuario or self.usuario

        items_uc = [ItemCarrito(
            producto_id  = i.producto_id,
            cantidad     = i.cantidad,
            precio_unit  = i.precio_unitario,
            nombre       = i.nombre,
        ) for i in items]

        dp = DP(
            forma_pago       = datos_pago.forma_pago,
            monto_pagado     = datos_pago.efectivo_recibido,
            cliente_id       = datos_pago.cliente_id,
            descuento_global = datos_pago.descuento_global,
        )

        from core.services.sales_service import SalesService
        from core.services.inventory_service import InventoryService
        from repositories.sales_repository import SalesRepository
        sales_svc = SalesService(
            db_conn=self.conn, sales_repo=SalesRepository(self.conn),
            recipe_repo=None,
            inventory_service=InventoryService(self.conn),
            finance_service=None,
            loyalty_service=None, promotion_engine=None, sync_service=None,
            ticket_template_engine=None, whatsapp_service=None,
            config_service=None, feature_flag_service=None,
        )
        inv_svc = InventoryService(self.conn)

        uc = ProcesarVentaUC(
            sales_service=sales_svc, inventory_service=inv_svc,
            finance_service=None, loyalty_service=None,
            ticket_engine=None,
        )
        r = uc.ejecutar(items_uc, dp, self.branch_id, usr)
        if not r.ok:
            msg = (r.error or "").lower()
            if "carrito" in msg and ("vacío" in msg or "vacio" in msg):
                raise CarritoVacioError(r.error)
            if "stock" in msg or "insuficiente" in msg:
                raise StockError(r.error)
            if "monto pagado" in msg or "menor al total" in msg:
                raise PagoInsuficienteError(r.error)
            raise VentaError(r.error or "Error al procesar venta")

        return ResultadoVenta(
            venta_id=r.venta_id, folio=r.folio,
            total=r.total, cambio=r.cambio,
            puntos_ganados=r.puntos_ganados,
        )

    def anular_venta(self, venta_id, motivo=""):
        from core.services.sales_reversal_service import SalesReversalService
        from core.services.sales_reversal_service import (
            VentaNoEncontradaError, VentaYaCanceladaError, ReversalError
        )
        try:
            SalesReversalService(self.conn, self.branch_id).cancel_sale(venta_id, self.usuario)
        except (VentaNoEncontradaError, VentaYaCanceladaError) as exc:
            raise VentaError(str(exc)) from exc
        except ReversalError as exc:
            raise VentaError(str(exc)) from exc
