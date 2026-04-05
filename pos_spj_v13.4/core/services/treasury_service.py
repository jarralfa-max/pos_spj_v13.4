# core/services/treasury_service.py — SPJ POS v13.30 — FASE 3
"""
TreasuryService — Tesorería Central (CAPEX).

Rastrea TODO el dinero real del negocio:
  Capital (inyecciones/retiros) → Ingresos (ventas) → Egresos (TODOS)

EGRESOS contemplados:
  1. Compras de inventario (pollo, abarrotes, insumos)
  2. Gastos fijos (renta, luz, agua, gas, internet, seguros)
  3. Gastos operativos (limpieza, mantenimiento, papelería, empaque)
  4. Nómina / RRHH (salarios, bonos, IMSS)
  5. Activos fijos (equipo) + depreciación mensual
  6. Fidelización (pasivo por estrellas emitidas)
  7. Comisiones (MercadoPago 3.6%, delivery)
  8. Merma (pérdida de inventario por caducidad, daño)
  9. CXP (pagos a proveedores)
"""
from __future__ import annotations
import logging
from datetime import date, datetime
from typing import Dict, List, Any

logger = logging.getLogger("spj.treasury")


class TreasuryService:

    def __init__(self, db_conn, module_config=None):
        self.db = db_conn
        self._module_config = module_config
        self._bus = None
        try:
            from core.events.event_bus import get_bus
            self._bus = get_bus()
        except Exception:
            pass
        self._ensure_tables()

    @property
    def enabled(self) -> bool:
        if self._module_config:
            return self._module_config.is_enabled('treasury_central')
        return True

    def _ensure_tables(self):
        try:
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS treasury_capital (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha TEXT DEFAULT (datetime('now')),
                    tipo TEXT NOT NULL,
                    monto REAL NOT NULL,
                    descripcion TEXT DEFAULT '',
                    usuario TEXT DEFAULT '',
                    sucursal_id INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS treasury_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fecha TEXT DEFAULT (datetime('now')),
                    tipo TEXT NOT NULL,
                    categoria TEXT NOT NULL,
                    concepto TEXT DEFAULT '',
                    ingreso REAL DEFAULT 0,
                    egreso REAL DEFAULT 0,
                    sucursal_id INTEGER DEFAULT 1,
                    referencia TEXT DEFAULT '',
                    usuario TEXT DEFAULT ''
                );
                CREATE INDEX IF NOT EXISTS idx_tl_fecha ON treasury_ledger(fecha);
                CREATE INDEX IF NOT EXISTS idx_tl_cat ON treasury_ledger(categoria);
                CREATE TABLE IF NOT EXISTS treasury_gastos_fijos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    categoria TEXT NOT NULL,
                    nombre TEXT NOT NULL,
                    monto_mensual REAL NOT NULL,
                    dia_pago INTEGER DEFAULT 1,
                    sucursal_id INTEGER DEFAULT 0,
                    activo INTEGER DEFAULT 1
                );
            """)
        except Exception as e:
            logger.debug("_ensure_tables: %s", e)

    # ══════════════════════════════════════════════════════════════════════════
    #  Capital — inyecciones y retiros
    # ══════════════════════════════════════════════════════════════════════════

    def inyectar_capital(self, monto: float, descripcion: str = "",
                         usuario: str = "") -> int:
        cur = self.db.execute(
            "INSERT INTO treasury_capital(tipo,monto,descripcion,usuario) "
            "VALUES('inyeccion',?,?,?)", (monto, descripcion, usuario))
        self.db.execute(
            "INSERT INTO treasury_ledger(tipo,categoria,concepto,ingreso,usuario) "
            "VALUES('ingreso','capital:inyeccion',?,?,?)",
            (descripcion, monto, usuario))
        self.db.commit()
        logger.info("Capital inyectado: $%.2f", monto)
        return cur.lastrowid

    def retirar_capital(self, monto: float, descripcion: str = "",
                         usuario: str = "") -> int:
        cur = self.db.execute(
            "INSERT INTO treasury_capital(tipo,monto,descripcion,usuario) "
            "VALUES('retiro',?,?,?)", (-abs(monto), descripcion, usuario))
        self.db.execute(
            "INSERT INTO treasury_ledger(tipo,categoria,concepto,egreso,usuario) "
            "VALUES('egreso','capital:retiro',?,?,?)",
            (descripcion, abs(monto), usuario))
        self.db.commit()
        return cur.lastrowid

    def capital_total(self) -> float:
        return self._q("SELECT COALESCE(SUM(monto),0) FROM treasury_capital")

    # ══════════════════════════════════════════════════════════════════════════
    #  Registrar movimientos
    # ══════════════════════════════════════════════════════════════════════════

    def registrar_ingreso(self, categoria: str, concepto: str, monto: float,
                          sucursal_id: int = 1, referencia: str = "",
                          usuario: str = ""):
        self.db.execute(
            "INSERT INTO treasury_ledger(tipo,categoria,concepto,ingreso,"
            "sucursal_id,referencia,usuario) VALUES('ingreso',?,?,?,?,?,?)",
            (categoria, concepto, monto, sucursal_id, referencia, usuario))
        try:
            self.db.commit()
        except Exception:
            pass
        self._publish_movimiento("ingreso", categoria, concepto, monto,
                                  sucursal_id, referencia, usuario)

    def registrar_egreso(self, categoria: str, concepto: str, monto: float,
                         sucursal_id: int = 1, referencia: str = "",
                         usuario: str = ""):
        self.db.execute(
            "INSERT INTO treasury_ledger(tipo,categoria,concepto,egreso,"
            "sucursal_id,referencia,usuario) VALUES('egreso',?,?,?,?,?,?)",
            (categoria, concepto, abs(monto), sucursal_id, referencia, usuario))
        try:
            self.db.commit()
        except Exception:
            pass
        self._publish_movimiento("egreso", categoria, concepto, abs(monto),
                                  sucursal_id, referencia, usuario)

    def _publish_movimiento(self, tipo: str, categoria: str, concepto: str,
                             monto: float, sucursal_id: int,
                             referencia: str, usuario: str) -> None:
        """Publica MOVIMIENTO_FINANCIERO al EventBus (async, no bloquea)."""
        if not self._bus:
            return
        try:
            from core.events.event_bus import MOVIMIENTO_FINANCIERO
            self._bus.publish(MOVIMIENTO_FINANCIERO, {
                "tipo":        tipo,          # "ingreso" | "egreso"
                "categoria":   categoria,
                "concepto":    concepto,
                "monto":       monto,
                "sucursal_id": sucursal_id,
                "referencia":  referencia,
                "usuario":     usuario,
            }, async_=True)
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  KPIs — lee de TODAS las tablas del ERP
    # ══════════════════════════════════════════════════════════════════════════

    def kpis_financieros(self, fecha_desde: str = "", fecha_hasta: str = "",
                          sucursal_id: int = 0) -> Dict[str, Any]:
        hoy = date.today()
        df = fecha_desde or date(hoy.year, hoy.month, 1).isoformat()
        dt = fecha_hasta or hoy.isoformat()
        sf = " AND sucursal_id=?" if sucursal_id else ""
        sp = [sucursal_id] if sucursal_id else []

        # ── INGRESOS ──────────────────────────────────────────────────────
        ingresos = self._q(
            f"SELECT COALESCE(SUM(total),0) FROM ventas "
            f"WHERE estado='completada' AND DATE(fecha) BETWEEN ? AND ?{sf}",
            [df, dt] + sp)

        # ── COSTO DE LO VENDIDO ───────────────────────────────────────────
        costo_venta = self._q(
            f"SELECT COALESCE(SUM(dv.cantidad * COALESCE(dv.costo_unitario_real,"
            f"p.precio_compra,p.costo,0)),0) "
            f"FROM detalles_venta dv "
            f"JOIN ventas v ON v.id=dv.venta_id "
            f"LEFT JOIN productos p ON p.id=dv.producto_id "
            f"WHERE v.estado='completada' AND DATE(v.fecha) BETWEEN ? AND ?{sf}",
            [df, dt] + sp)

        # ── COMPRAS DE INVENTARIO ─────────────────────────────────────────
        compras_inv = self._q(
            f"SELECT COALESCE(SUM(costo_total),0) FROM compras_inventariables "
            f"WHERE DATE(fecha) BETWEEN ? AND ?{sf}", [df, dt] + sp)
        compras_pollo = self._q(
            "SELECT COALESCE(SUM(total),0) FROM compras_pollo "
            "WHERE DATE(fecha) BETWEEN ? AND ?", [df, dt])
        compras_ord = self._q(
            "SELECT COALESCE(SUM(total),0) FROM compras "
            "WHERE DATE(fecha) BETWEEN ? AND ? AND estado='recibida'", [df, dt])
        total_compras = compras_inv + compras_pollo + compras_ord

        # ── GASTOS FIJOS (renta, luz, agua, gas, internet, seguros) ───────
        gastos_fijos = self._q(
            "SELECT COALESCE(SUM(monto),0) FROM gastos "
            "WHERE DATE(fecha) BETWEEN ? AND ? AND ("
            "LOWER(categoria) LIKE '%fijo%' OR LOWER(categoria) LIKE '%renta%' "
            "OR LOWER(categoria) LIKE '%luz%' OR LOWER(categoria) LIKE '%agua%' "
            "OR LOWER(categoria) LIKE '%gas %' OR LOWER(categoria) LIKE '%internet%' "
            "OR LOWER(categoria) LIKE '%seguro%' OR LOWER(categoria) LIKE '%licencia%' "
            "OR LOWER(categoria) LIKE '%contabil%' OR LOWER(categoria) LIKE '%telefono%')",
            [df, dt])

        # ── GASTOS OPERATIVOS (insumos, limpieza, mantenimiento, etc.) ────
        gastos_op = self._q(
            "SELECT COALESCE(SUM(monto),0) FROM gastos "
            "WHERE DATE(fecha) BETWEEN ? AND ? AND ("
            "LOWER(categoria) LIKE '%operativ%' OR LOWER(categoria) LIKE '%insumo%' "
            "OR LOWER(categoria) LIKE '%mantenimiento%' OR LOWER(categoria) LIKE '%limpieza%' "
            "OR LOWER(categoria) LIKE '%publicidad%' OR LOWER(categoria) LIKE '%transporte%' "
            "OR LOWER(categoria) LIKE '%empaque%' OR LOWER(categoria) LIKE '%uniforme%' "
            "OR LOWER(categoria) LIKE '%papeleria%')",
            [df, dt])

        # ── GASTOS OTROS (todo lo registrado menos los ya clasificados) ───
        gastos_total_bd = self._q(
            "SELECT COALESCE(SUM(monto),0) FROM gastos "
            "WHERE DATE(fecha) BETWEEN ? AND ?", [df, dt])
        gastos_otros = max(0, gastos_total_bd - gastos_fijos - gastos_op)

        # ── NÓMINA / RRHH ────────────────────────────────────────────────
        nomina = self._q(
            "SELECT COALESCE(SUM(total),0) FROM nomina_pagos "
            "WHERE estado='pagado' AND DATE(fecha) BETWEEN ? AND ?", [df, dt])

        # ── MERMA (pérdida de inventario) ─────────────────────────────────
        merma = self._q(
            "SELECT COALESCE(SUM(cantidad * COALESCE(costo_unitario,0)),0) "
            "FROM merma WHERE DATE(fecha) BETWEEN ? AND ?", [df, dt])

        # ── DEPRECIACIÓN DE ACTIVOS (mensual prorrateada) ─────────────────
        depreciacion = self._q(
            "SELECT COALESCE(SUM(depreciacion_anual/12),0) FROM activos "
            "WHERE estado='activo'", [])

        # ── COMISIONES (MercadoPago 3.6%, delivery) ───────────────────────
        comision_mp = self._q(
            "SELECT COALESCE(SUM(total*0.036),0) FROM ventas "
            "WHERE estado='completada' AND forma_pago='Mercado Pago' "
            "AND DATE(fecha) BETWEEN ? AND ?", [df, dt])
        comision_delivery = self._q(
            "SELECT COALESCE(SUM(COALESCE(comision,0)),0) FROM delivery_orders "
            "WHERE DATE(fecha) BETWEEN ? AND ?", [df, dt])

        # ── PASIVO FIDELIZACIÓN ───────────────────────────────────────────
        pasivo_loyalty = self._q(
            "SELECT COALESCE(SUM(monto_total),0) FROM loyalty_pasivo_log", [])

        # ── CXP pendiente ─────────────────────────────────────────────────
        cxp_pendiente = self._q(
            "SELECT COALESCE(SUM(balance),0) FROM accounts_payable "
            "WHERE status IN ('pendiente','parcial')", [])

        # ── CXC pendiente ─────────────────────────────────────────────────
        cxc_pendiente = self._q(
            "SELECT COALESCE(SUM(balance),0) FROM accounts_receivable "
            "WHERE status IN ('pendiente','parcial')", [])

        # ── CAPITAL ───────────────────────────────────────────────────────
        capital = self.capital_total()

        # ── CÁLCULOS ──────────────────────────────────────────────────────
        utilidad_bruta = ingresos - costo_venta
        total_egresos = (total_compras + gastos_fijos + gastos_op +
                         max(0, gastos_otros) + nomina + merma +
                         depreciacion + comision_mp + comision_delivery)
        utilidad_neta = ingresos - total_egresos
        capital_disponible = capital + utilidad_neta - pasivo_loyalty
        margen_bruto = (utilidad_bruta / ingresos * 100) if ingresos else 0
        margen_neto = (utilidad_neta / ingresos * 100) if ingresos else 0
        roi = (utilidad_neta / capital * 100) if capital > 0 else 0
        burn = (capital_disponible / (total_egresos or 1))
        equilibrio = total_egresos

        return {
            "periodo": {"desde": df, "hasta": dt},
            # Ingresos
            "ingresos": r2(ingresos),
            "costo_venta": r2(costo_venta),
            "utilidad_bruta": r2(utilidad_bruta),
            "margen_bruto_pct": r1(margen_bruto),
            # Egresos detallados
            "egresos": {
                "compras_inventario": r2(total_compras),
                "  inventariables": r2(compras_inv),
                "  pollo": r2(compras_pollo),
                "  ordenes_compra": r2(compras_ord),
                "gastos_fijos": r2(gastos_fijos),
                "gastos_operativos": r2(gastos_op),
                "gastos_otros": r2(gastos_otros),
                "nomina_rrhh": r2(nomina),
                "merma": r2(merma),
                "depreciacion_activos": r2(depreciacion),
                "comisiones": r2(comision_mp + comision_delivery),
                "  mercadopago": r2(comision_mp),
                "  delivery": r2(comision_delivery),
                "total_egresos": r2(total_egresos),
            },
            # Resultado
            "utilidad_neta": r2(utilidad_neta),
            "margen_neto_pct": r1(margen_neto),
            # Capital / CAPEX
            "capital_invertido": r2(capital),
            "capital_disponible": r2(capital_disponible),
            "roi_pct": r1(roi),
            "burn_rate_meses": r1(max(0, burn)),
            "punto_equilibrio": r2(equilibrio),
            # Pasivos y cuentas
            "pasivo_fidelizacion": r2(pasivo_loyalty),
            "cxp_pendiente": r2(cxp_pendiente),
            "cxc_pendiente": r2(cxc_pendiente),
            # Activos
            "valor_inventario": r2(self._q(
                "SELECT COALESCE(SUM(existencia*COALESCE(precio_compra,costo,0)),0) "
                "FROM productos WHERE activo=1", [])),
            "valor_activos_fijos": r2(self._q(
                "SELECT COALESCE(SUM(valor_actual),0) FROM activos "
                "WHERE estado='activo'", [])),
        }

    # ══════════════════════════════════════════════════════════════════════════
    #  Estado de cuenta ejecutivo
    # ══════════════════════════════════════════════════════════════════════════

    def estado_cuenta(self) -> Dict:
        k = self.kpis_financieros()
        return {
            "capital_invertido": k["capital_invertido"],
            "capital_disponible": k["capital_disponible"],
            "ingresos_mes": k["ingresos"],
            "egresos_mes": k["egresos"]["total_egresos"],
            "utilidad_neta": k["utilidad_neta"],
            "roi_pct": k["roi_pct"],
            "burn_rate_meses": k["burn_rate_meses"],
            "salud": self._salud(k),
        }

    def _salud(self, k: Dict) -> str:
        if k["utilidad_neta"] < 0:
            return "🔴 CRÍTICO — operando con pérdida"
        if k["margen_neto_pct"] < 5:
            return "🟡 PRECAUCIÓN — margen bajo"
        if k["burn_rate_meses"] < 2:
            return "🟠 ALERTA — capital bajo"
        if k["margen_neto_pct"] >= 15:
            return "🟢 SALUDABLE"
        return "🔵 ESTABLE"

    # ══════════════════════════════════════════════════════════════════════════
    #  Gastos fijos recurrentes
    # ══════════════════════════════════════════════════════════════════════════

    def registrar_gasto_fijo(self, categoria: str, nombre: str,
                              monto: float, dia_pago: int = 1,
                              sucursal_id: int = 0) -> int:
        cur = self.db.execute(
            "INSERT INTO treasury_gastos_fijos(categoria,nombre,monto_mensual,"
            "dia_pago,sucursal_id) VALUES(?,?,?,?,?)",
            (categoria, nombre, monto, dia_pago, sucursal_id))
        self.db.commit()
        return cur.lastrowid

    def get_gastos_fijos(self) -> List[Dict]:
        try:
            rows = self.db.execute(
                "SELECT id,categoria,nombre,monto_mensual,dia_pago,sucursal_id "
                "FROM treasury_gastos_fijos WHERE activo=1").fetchall()
            return [{"id": r[0], "categoria": r[1], "nombre": r[2],
                     "monto": r[3], "dia_pago": r[4], "sucursal_id": r[5]}
                    for r in rows]
        except Exception:
            return []

    def total_gastos_fijos_mensual(self) -> float:
        return self._q("SELECT COALESCE(SUM(monto_mensual),0) "
                        "FROM treasury_gastos_fijos WHERE activo=1")

    # ══════════════════════════════════════════════════════════════════════════
    #  Desglose por sucursal
    # ══════════════════════════════════════════════════════════════════════════

    def kpis_por_sucursal(self, df: str = "", dt: str = "") -> List[Dict]:
        rows = self.db.execute(
            "SELECT id, nombre FROM sucursales WHERE activa=1").fetchall()
        return [{**self.kpis_financieros(df, dt, r[0]),
                 "sucursal_id": r[0], "sucursal": r[1]}
                for r in (rows or [])]

    # ══════════════════════════════════════════════════════════════════════════
    #  Gastos operativos (usado por modulos/tesoreria.py)
    # ══════════════════════════════════════════════════════════════════════════

    def registrar_gasto_opex(self, categoria: str = "", concepto: str = "",
                              monto: float = 0, metodo_pago: str = "efectivo",
                              usuario: str = "", sucursal_id: int = 1):
        """Registra un gasto operativo en la tabla gastos."""
        self.db.execute(
            "INSERT INTO gastos (fecha, categoria, concepto, monto, metodo_pago, "
            "usuario, fecha_registro) VALUES (datetime('now'),?,?,?,?,?,datetime('now'))",
            (categoria, concepto, monto, metodo_pago, usuario))
        self.registrar_egreso("gasto_operativo:" + categoria, concepto, monto,
                              sucursal_id, usuario=usuario)
        try:
            self.db.commit()
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  Cuentas por Pagar (CXP) — usado por modulos/tesoreria.py
    # ══════════════════════════════════════════════════════════════════════════

    def get_cuentas_por_pagar(self, sucursal_id: int = 0) -> List[Dict]:
        """Retorna CXP pendientes como lista de dicts."""
        try:
            sf = " AND ap.sucursal_id=?" if sucursal_id else ""
            sp = [sucursal_id] if sucursal_id else []
            rows = self.db.execute(f"""
                SELECT ap.id, ap.fecha, COALESCE(ap.folio,'') as folio,
                       COALESCE(s.nombre, 'Varios') as proveedor,
                       ap.concepto, ap.balance as saldo,
                       ap.amount as monto_original, ap.status
                FROM accounts_payable ap
                LEFT JOIN proveedores s ON s.id = ap.supplier_id
                WHERE ap.status IN ('pendiente','parcial'){sf}
                ORDER BY ap.fecha DESC
            """, sp).fetchall()
            return [{"id": r[0], "fecha": r[1], "folio": r[2],
                     "proveedor": r[3], "concepto": r[4], "saldo": float(r[5]),
                     "monto_original": float(r[6]), "status": r[7]}
                    for r in rows]
        except Exception:
            return []

    def abonar_cuenta_por_pagar(self, ap_id: int, monto: float,
                                 metodo: str = "efectivo", usuario: str = ""):
        """Registra un abono a una cuenta por pagar."""
        row = self.db.execute(
            "SELECT balance FROM accounts_payable WHERE id=?", (ap_id,)).fetchone()
        if not row:
            raise ValueError(f"CXP #{ap_id} no encontrada")
        balance = float(row[0])
        nuevo = max(0, balance - monto)
        status = "pagada" if nuevo <= 0.01 else "parcial"
        self.db.execute(
            "UPDATE accounts_payable SET balance=?, status=? WHERE id=?",
            (nuevo, status, ap_id))
        self.db.execute(
            "INSERT INTO cxp_payments (ap_id, monto, metodo_pago, usuario, fecha) "
            "VALUES (?,?,?,?,datetime('now'))",
            (ap_id, monto, metodo, usuario))
        self.registrar_egreso("cxp:abono", f"Abono CXP #{ap_id}", monto,
                              usuario=usuario)
        try:
            self.db.commit()
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  Cuentas por Cobrar (CXC) — usado por modulos/tesoreria.py
    # ══════════════════════════════════════════════════════════════════════════

    def get_cuentas_por_cobrar(self, sucursal_id: int = 0) -> List[Dict]:
        """Retorna CXC pendientes como lista de dicts."""
        try:
            sf = " AND ar.sucursal_id=?" if sucursal_id else ""
            sp = [sucursal_id] if sucursal_id else []
            rows = self.db.execute(f"""
                SELECT ar.id, ar.fecha, COALESCE(ar.folio,'') as folio,
                       COALESCE(c.nombre, 'Público') as cliente,
                       ar.concepto, ar.balance as saldo,
                       ar.amount as monto_original, ar.status
                FROM accounts_receivable ar
                LEFT JOIN clientes c ON c.id = ar.cliente_id
                WHERE ar.status IN ('pendiente','parcial'){sf}
                ORDER BY ar.fecha DESC
            """, sp).fetchall()
            return [{"id": r[0], "fecha": r[1], "folio": r[2],
                     "cliente": r[3], "concepto": r[4], "saldo": float(r[5]),
                     "monto_original": float(r[6]), "status": r[7]}
                    for r in rows]
        except Exception:
            return []

    def abonar_cuenta_por_cobrar(self, ar_id: int, monto: float,
                                  metodo: str = "efectivo", usuario: str = ""):
        """Registra un cobro a una cuenta por cobrar."""
        row = self.db.execute(
            "SELECT balance FROM accounts_receivable WHERE id=?", (ar_id,)).fetchone()
        if not row:
            raise ValueError(f"CXC #{ar_id} no encontrada")
        balance = float(row[0])
        nuevo = max(0, balance - monto)
        status = "cobrada" if nuevo <= 0.01 else "parcial"
        self.db.execute(
            "UPDATE accounts_receivable SET balance=?, status=? WHERE id=?",
            (nuevo, status, ar_id))
        self.db.execute(
            "INSERT INTO cxc_payments (ar_id, monto, metodo_pago, usuario, fecha) "
            "VALUES (?,?,?,?,datetime('now'))",
            (ar_id, monto, metodo, usuario))
        self.registrar_ingreso("cxc:cobro", f"Cobro CXC #{ar_id}", monto,
                               usuario=usuario)
        try:
            self.db.commit()
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  Helper
    # ══════════════════════════════════════════════════════════════════════════

    def _q(self, sql: str, params: list = None) -> float:
        try:
            row = self.db.execute(sql, params or []).fetchone()
            return float(row[0]) if row and row[0] else 0.0
        except Exception:
            return 0.0


def r2(v): return round(v, 2)
def r1(v): return round(v, 1)
