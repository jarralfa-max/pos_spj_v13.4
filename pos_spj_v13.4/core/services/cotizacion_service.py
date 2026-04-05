
# core/services/cotizacion_service.py — SPJ POS v10
from __future__ import annotations
import logging, uuid
from datetime import datetime, date, timedelta
from core.db.connection import get_connection, transaction

logger = logging.getLogger("spj.cotizaciones")

class CotizacionService:
    def __init__(self, conn=None, sucursal_id: int = 1, usuario: str = "vendedor", container=None):
        self.conn = conn or get_connection()
        self.sucursal_id = sucursal_id
        self.usuario = usuario
        self.container = container  # AppContainer for full service chain
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS cotizaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT UNIQUE DEFAULT (lower(hex(randomblob(16)))),
                folio TEXT UNIQUE,
                cliente_id INTEGER, cliente_nombre TEXT,
                subtotal DECIMAL(12,2) DEFAULT 0, descuento DECIMAL(12,2) DEFAULT 0,
                total DECIMAL(12,2) DEFAULT 0,
                estado TEXT DEFAULT 'pendiente',  -- pendiente|aprobada|rechazada|vencida|convertida
                notas TEXT, vigencia_dias INTEGER DEFAULT 7,
                fecha_vencimiento DATE,
                venta_id INTEGER,  -- si se convirtio en venta
                usuario TEXT, sucursal_id INTEGER DEFAULT 1,
                fecha DATETIME DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS cotizaciones_detalle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cotizacion_id INTEGER REFERENCES cotizaciones(id) ON DELETE CASCADE,
                producto_id INTEGER, nombre TEXT,
                cantidad DECIMAL(10,3), unidad TEXT DEFAULT 'kg',
                precio_unitario DECIMAL(10,4), descuento_pct DECIMAL(5,2) DEFAULT 0, subtotal DECIMAL(12,2)
            );
        """)
        try: self.conn.commit()
        except Exception: pass

    def crear(self, items: list, cliente_id: int = None, cliente_nombre: str = "",
              notas: str = "", vigencia_dias: int = 7, descuento_global: float = 0) -> dict:
        subtotal = sum(float(i["cantidad"]) * float(i["precio_unitario"]) for i in items)
        total = round(subtotal - descuento_global, 2)
        folio = f"COT-{datetime.now().strftime('%Y%m%d')}-{self.conn.execute('SELECT COUNT(*) FROM cotizaciones').fetchone()[0]+1:04d}"
        venc  = (date.today() + timedelta(days=vigencia_dias)).isoformat()
        with transaction(self.conn) as c:
            cid = c.execute("""INSERT INTO cotizaciones
                (uuid,folio,cliente_id,cliente_nombre,subtotal,descuento,total,notas,
                 vigencia_dias,fecha_vencimiento,usuario,sucursal_id)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()),folio,cliente_id,cliente_nombre,
                 subtotal,descuento_global,total,notas,vigencia_dias,venc,
                 self.usuario,self.sucursal_id)).lastrowid
            for i in items:
                sub = float(i["cantidad"])*float(i["precio_unitario"])*(1-float(i.get("descuento_pct",0))/100)
                c.execute("""INSERT INTO cotizaciones_detalle
                    (cotizacion_id,producto_id,nombre,cantidad,unidad,precio_unitario,descuento_pct,subtotal)
                    VALUES(?,?,?,?,?,?,?,?)""",
                    (cid,i.get("producto_id"),i.get("nombre",""),i["cantidad"],
                     i.get("unidad","kg"),i["precio_unitario"],i.get("descuento_pct",0),sub))
        logger.info("Cotizacion %s creada: total=$%.2f", folio, total)
        return {"cotizacion_id":cid,"folio":folio,"total":total,"vencimiento":venc}

    def convertir_en_venta(self, cotizacion_id: int) -> int:
        """Convierte la cotizacion aprobada en venta real usando ProcesarVentaUC (v13.1)."""
        cot = self.conn.execute(
            "SELECT * FROM cotizaciones WHERE id=?", (cotizacion_id,)
        ).fetchone()
        if not cot: raise ValueError("Cotizacion no encontrada")
        cot = dict(cot)
        if cot["estado"] == "vencida": raise ValueError("Cotizacion vencida")

        items_db = [dict(r) for r in self.conn.execute(
            "SELECT * FROM cotizaciones_detalle WHERE cotizacion_id=?",
            (cotizacion_id,)
        ).fetchall()]

        from core.use_cases.venta import ProcesarVentaUC, ItemCarrito, DatosPago
        from core.services.inventory_service import InventoryService
        from core.services.sales_service import SalesService
        from repositories.sales_repository import SalesRepository

        items_uc = [
            ItemCarrito(
                producto_id = i["producto_id"],
                cantidad    = float(i["cantidad"]),
                precio_unit = float(i["precio_unitario"]),
                nombre      = i.get("nombre", ""),
                descuento   = float(i.get("descuento", 0)),
            )
            for i in items_db
        ]
        datos_pago = DatosPago(
            forma_pago       = "Contado",
            monto_pagado     = float(cot["total"]),  # exact amount due
            cliente_id       = cot.get("cliente_id"),
            descuento_global = float(cot.get("descuento", 0)),
            notas            = f"Convertida de cotización #{cotizacion_id}",
        )
        # Use AppContainer's full SalesService when available
        # (includes GrowthEngine, notifications, WhatsApp, audit trail)
        if self.container and hasattr(self.container, 'sales_service'):
            sales_svc = self.container.sales_service
            inv_svc   = getattr(self.container, 'inventory_service', None) or InventoryService(self.conn)
        else:
            sales_repo = SalesRepository(self.conn)
            inv_svc    = InventoryService(self.conn)
            sales_svc  = SalesService(
                db_conn=self.conn, sales_repo=sales_repo, recipe_repo=None,
                inventory_service=inv_svc, finance_service=None, loyalty_service=None,
                promotion_engine=None, sync_service=None, ticket_template_engine=None,
                whatsapp_service=None, config_service=None, feature_flag_service=None,
            )
        uc = ProcesarVentaUC(
            sales_service=sales_svc, inventory_service=inv_svc,
            finance_service=getattr(self.container, 'finance_service', None) if self.container else None,
            loyalty_service=getattr(self.container, 'loyalty_service', None) if self.container else None,
            ticket_engine=getattr(self.container, 'ticket_template_engine', None) if self.container else None,
        )
        resultado = uc.ejecutar(items_uc, datos_pago, self.sucursal_id, self.usuario)
        if not resultado.ok:
            raise RuntimeError(f"Error al convertir cotización: {resultado.error}")

        self.conn.execute(
            "UPDATE cotizaciones SET estado='convertida',venta_id=? WHERE id=?",
            (resultado.venta_id, cotizacion_id)
        )
        try: self.conn.commit()
        except Exception: pass
        return resultado.venta_id

    def vencer_expiradas(self) -> int:
        hoy = date.today().isoformat()
        n = self.conn.execute(
            "UPDATE cotizaciones SET estado='vencida' WHERE estado='pendiente' AND fecha_vencimiento < ?",
            (hoy,)).rowcount
        try: self.conn.commit()
        except Exception: pass
        return n

    def get_cotizaciones(self, estado: str = None, limit: int = 50) -> list:
        sql = "SELECT * FROM cotizaciones WHERE 1=1"
        params = []
        if estado: sql += " AND estado=?"; params.append(estado)
        sql += " ORDER BY fecha DESC LIMIT ?"; params.append(limit)
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]
