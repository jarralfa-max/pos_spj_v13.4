# core/services/ventas_facade.py — DEPRECADO en v13.1
# Shim de compatibilidad → delega a ProcesarVentaUC
import warnings, logging
logger = logging.getLogger("spj.ventas_facade")

class VentasFacade:
    """
    DEPRECADO: Usar container.uc_venta directamente.
    Mantenido para compatibilidad con código externo.
    """
    def __init__(self, conn=None, sucursal_id=1, usuario="cajero"):
        warnings.warn(
            "VentasFacade está deprecado. Usa container.uc_venta.",
            DeprecationWarning, stacklevel=2
        )
        self.conn = conn
        self.sucursal_id = sucursal_id
        self.usuario = usuario
        self.on_venta_ok = None
        self.on_error    = None

    def procesar(self, items, datos_pago, **kw):
        try:
            from core.use_cases.venta import ProcesarVentaUC, ItemCarrito, DatosPago
            from core.services.inventory_service import InventoryService
            inv = InventoryService(self.conn)
            uc  = ProcesarVentaUC(
                sales_service     = self._make_sales_svc(),
                inventory_service = inv,
                finance_service   = None,
                loyalty_service   = self._make_loyalty_svc(),
                ticket_engine     = self._make_ticket_engine(),
            )
            items_uc = [ItemCarrito(
                producto_id  = i.producto_id if hasattr(i,'producto_id') else i.get('product_id',0),
                cantidad     = i.cantidad    if hasattr(i,'cantidad')    else float(i.get('qty',0)),
                precio_unit  = i.precio_unitario if hasattr(i,'precio_unitario') else float(i.get('unit_price',0)),
                nombre       = i.nombre if hasattr(i,'nombre') else i.get('name',''),
                es_compuesto = i.es_compuesto if hasattr(i,'es_compuesto') else i.get('es_compuesto',0),
            ) for i in items]
            dp = DatosPago(
                forma_pago   = getattr(datos_pago,'forma_pago','Efectivo'),
                monto_pagado = getattr(datos_pago,'efectivo_recibido',0) or getattr(datos_pago,'monto_pagado',0),
                cliente_id   = getattr(datos_pago,'cliente_id',None),
                descuento_global = getattr(datos_pago,'descuento_global',0),
            )
            r = uc.ejecutar(items_uc, dp, self.sucursal_id, self.usuario)
            if r.ok and self.on_venta_ok: self.on_venta_ok(r)
            elif not r.ok and self.on_error: self.on_error(Exception(r.error))
        except Exception as exc:
            logger.error("VentasFacade.procesar: %s", exc)
            if self.on_error: self.on_error(exc)

    def verificar_stock(self, producto_id, cantidad):
        from core.services.inventory_service import InventoryService
        return InventoryService(self.conn).get_stock(producto_id)

    def buscar_cliente(self, termino):
        rows = self.conn.execute(
            "SELECT id,nombre,COALESCE(apellido,''),COALESCE(telefono,''),COALESCE(puntos,0) "
            "FROM clientes WHERE nombre LIKE ? OR telefono LIKE ? LIMIT 10",
            (f"%{termino}%", f"%{termino}%")
        ).fetchall()
        return [dict(r) for r in rows]

    def _make_sales_svc(self):
        from core.services.sales_service import SalesService
        from repositories.sales_repository import SalesRepository
        from core.services.inventory_service import InventoryService
        return SalesService(
            db_conn=self.conn,
            sales_repo=SalesRepository(self.conn),
            recipe_repo=None,
            inventory_service=InventoryService(self.conn),
            finance_service=None,
            loyalty_service=None,
            promotion_engine=None,
            sync_service=None,
            ticket_template_engine=None,
            whatsapp_service=None,
            config_service=None,
            feature_flag_service=None,
        )

    def _make_loyalty_svc(self):
        try:
            from core.services.loyalty_service import LoyaltyService
            return LoyaltyService(self.conn)
        except Exception:
            return None

    def _make_ticket_engine(self):
        try:
            from core.engines.template_engine import TicketTemplateEngine
            return TicketTemplateEngine(self.conn)
        except Exception:
            return None
