
# core/services/enterprise/finance_service.py
# ── FinanceService — Motor Financiero Enterprise SPJ POS ─────────────────────
#
# Centraliza TODAS las consultas financieras del sistema.
# NINGUNA ventana UI ejecuta SQL directamente.
#
# Métodos públicos:
#   balance_general()         — Activos / Pasivos / Patrimonio
#   flujo_caja()              — Entradas y salidas por período
#   cuentas_por_pagar()       — CXP con vencimiento y aging
#   cuentas_por_cobrar()      — CXC con días vencidos
#   dashboard_kpis()          — KPIs financieros ejecutivos
#   get_suppliers()           — Catálogo de proveedores
#   get_personal()            — Plantilla laboral
#   get_nomina_pagos()        — Historial de nómina
#   crear_cxp()               — Crear cuenta por pagar manual
#   abonar_cxp()              — Registrar pago parcial o total CXP
#   crear_cxc()               — Crear cuenta por cobrar manual
#   cobrar_cxc()              — Registrar cobro CXC
#   pagar_nomina()            — Registrar pago de nómina
#   sync_cxp_from_compras()   — Sincronizar CXP desde compras_inventariables
#   sync_cxc_from_ventas()    — Sincronizar CXC desde ventas a crédito
from __future__ import annotations

import logging
import json
import re
import csv
from io import StringIO
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.finance_service")

# ── Tipos de aging ────────────────────────────────────────────────────────────
AGING_CORRIENTE = "corriente"   # no vencido
AGING_30        = "1-30d"
AGING_60        = "31-60d"
AGING_90        = "61-90d"
AGING_MAS       = "+90d"


def _aging(due_date_str: Optional[str]) -> str:
    if not due_date_str:
        return AGING_CORRIENTE
    try:
        due = date.fromisoformat(str(due_date_str)[:10])
        days = (date.today() - due).days
        if days <= 0:   return AGING_CORRIENTE
        if days <= 30:  return AGING_30
        if days <= 60:  return AGING_60
        if days <= 90:  return AGING_90
        return AGING_MAS
    except Exception:
        return AGING_CORRIENTE


_RFC_RE = re.compile(r"^[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}$")


def _normalize_rfc(rfc: Optional[str]) -> Optional[str]:
    if not rfc:
        return None
    r = re.sub(r"[^A-Za-z0-9&Ññ]", "", str(rfc)).upper().strip()
    return r or None


def _validate_supplier_payload(data: Dict) -> Dict:
    nombre = (data.get("nombre") or "").strip()
    if not nombre:
        raise ValueError("El nombre del proveedor es obligatorio.")

    rfc = _normalize_rfc(data.get("rfc"))
    if rfc and not _RFC_RE.match(rfc):
        raise ValueError("RFC de proveedor inválido (formato SAT).")

    limite = float(data.get("limite_credito", 0) or 0)
    if limite < 0:
        raise ValueError("El límite de crédito no puede ser negativo.")

    condiciones = int(data.get("condiciones_pago", 30) or 30)
    if condiciones < 0:
        raise ValueError("Las condiciones de pago no pueden ser negativas.")

    clean = dict(data)
    clean["nombre"] = nombre
    clean["rfc"] = rfc
    clean["limite_credito"] = limite
    clean["condiciones_pago"] = condiciones
    return clean


class FinanceService:

    def __init__(self, db):
        """
        db: sqlite3.Connection o DatabaseWrapper — se envuelve automáticamente.

        Sub-servicios (FASE 5):
          _gl  — GeneralLedgerService  (asientos contables)
          _aps — AccountsPayableService (CxP)
          _ars — AccountsReceivableService (CxC)

        Los métodos públicos de esta clase se conservan como fachada legacy.
        El código nuevo debe usar los sub-servicios directamente.
        """
        from core.db.connection import wrap
        self.db = wrap(db)
        # Sub-servicios inyectados en __init__ para evitar imports circulares
        try:
            from core.services.finance.general_ledger_service import GeneralLedgerService
            self._gl = GeneralLedgerService(db)
        except Exception:
            self._gl = None
        try:
            from core.services.finance.accounts_payable_service import AccountsPayableService
            self._aps = AccountsPayableService(db, ledger_service=self)
        except Exception:
            self._aps = None
        try:
            from core.services.finance.accounts_receivable_service import AccountsReceivableService
            self._ars = AccountsReceivableService(db, ledger_service=self)
        except Exception:
            self._ars = None

    def _has_column(self, table: str, column: str) -> bool:
        """Compatibilidad de esquema SQLite (instalaciones legacy)."""
        try:
            rows = self.db.fetchall(f"PRAGMA table_info({table})")
            for r in rows:
                # sqlite Row puede exponer por índice o por clave
                name = r["name"] if "name" in r.keys() else r[1]
                if str(name).lower() == column.lower():
                    return True
        except Exception:
            pass
        return False

    def _productos_inventory_expr(self) -> str:
        """
        Expresión de valuación inventario compatible con columnas legacy.
        Prioridad: precio_compra -> costo -> precio_costo -> 0
        """
        opts = []
        for col in ("precio_compra", "costo", "precio_costo"):
            if self._has_column("productos", col):
                opts.append(col)
        if not opts:
            return "0"
        return "COALESCE(" + ", ".join(opts + ["0"]) + ")"

    def _resolve_column(self, table: str, *candidates: str) -> Optional[str]:
        """Retorna la primera columna existente de `candidates` para `table`."""
        for col in candidates:
            if self._has_column(table, col):
                return col
        return None

    # ═════════════════════════════════════════════════════════════════════════
    # DASHBOARD KPIs
    # ═════════════════════════════════════════════════════════════════════════

    def dashboard_kpis(
        self,
        branch_id: Optional[int] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict:
        """KPIs financieros ejecutivos para el dashboard."""
        df = date_from or date(date.today().year, date.today().month, 1).isoformat()
        dt = date_to   or date.today().isoformat()
        bf = "AND v.sucursal_id = ?" if branch_id else ""
        bp = ([branch_id] if branch_id else [])

        # Ingresos del período
        rev_row = self.db.fetchone(f"""
            SELECT
                COALESCE(SUM(v.total), 0)    AS ingresos,
                COUNT(DISTINCT v.id)          AS tickets,
                COALESCE(SUM(dv.costo_unitario_real * dv.cantidad), 0) AS costo_venta
            FROM ventas v
            LEFT JOIN detalles_venta dv ON dv.venta_id = v.id
            WHERE v.estado = 'completada' {bf}
              AND DATE(v.fecha) BETWEEN DATE(?) AND DATE(?)
        """, bp + [df, dt])

        ingresos    = float(rev_row["ingresos"]    or 0)
        costo_venta = float(rev_row["costo_venta"] or 0)
        tickets     = int  (rev_row["tickets"]     or 0)

        # Gastos del período
        gasto_activo = "AND activo = 1" if self._has_column("gastos", "activo") else ""
        gasto_row = self.db.fetchone(f"""
            SELECT COALESCE(SUM(monto), 0) AS gastos
            FROM gastos
            WHERE DATE(fecha) BETWEEN DATE(?) AND DATE(?)
              {gasto_activo}
        """, (df, dt))
        gastos = float(gasto_row["gastos"] or 0) if gasto_row else 0

        # CXP total pendiente
        cxp_row = self.db.fetchone("""
            SELECT COALESCE(SUM(balance), 0) AS cxp_total,
                   COUNT(*) AS cxp_count
            FROM accounts_payable
            WHERE status IN ('pendiente','parcial')
        """)
        cxp_total = float(cxp_row["cxp_total"] or 0) if cxp_row else 0
        cxp_count = int  (cxp_row["cxp_count"] or 0) if cxp_row else 0

        # CXC total pendiente
        cxc_row = self.db.fetchone("""
            SELECT COALESCE(SUM(balance), 0) AS cxc_total,
                   COUNT(*) AS cxc_count
            FROM accounts_receivable
            WHERE status IN ('pendiente','parcial')
        """)
        cxc_total = float(cxc_row["cxc_total"] or 0) if cxc_row else 0
        cxc_count = int  (cxc_row["cxc_count"] or 0) if cxc_row else 0

        # Nómina del período
        nomina_date_col = self._resolve_column("nomina_pagos", "created_at", "fecha", "fecha_registro")
        nom_filter = f"DATE({nomina_date_col}) BETWEEN DATE(?) AND DATE(?)" if nomina_date_col else "1=1"
        nom_row = self.db.fetchone(f"""
            SELECT COALESCE(SUM(total), 0) AS nomina
            FROM nomina_pagos
            WHERE {nom_filter}
              AND estado = 'pagado'
        """, (df, dt) if nomina_date_col else ())
        nomina = float(nom_row["nomina"] or 0) if nom_row else 0

        # Valor inventario
        prod_activo = "AND activo = 1" if self._has_column("productos", "activo") else ""
        inv_expr = self._productos_inventory_expr()
        inv_row = self.db.fetchone(f"""
            SELECT COALESCE(SUM(existencia * {inv_expr}), 0) AS inv_val
            FROM productos WHERE 1=1 {prod_activo}
        """)
        inv_val = float(inv_row["inv_val"] or 0) if inv_row else 0

        # Activos fijos
        assets_activo = "AND activo=1" if self._has_column("assets", "activo") else ""
        assets_row = self.db.fetchone(f"""
            SELECT COALESCE(SUM(valor_actual), 0) AS activos_total
            FROM assets WHERE estado != 'dado_baja' {assets_activo}
        """)
        activos_val = float(assets_row["activos_total"] or 0) if assets_row else 0

        # Alertas CXP vencidas
        venc_row = self.db.fetchone("""
            SELECT COUNT(*) AS vencidas FROM accounts_payable
            WHERE status IN ('pendiente','parcial')
              AND due_date IS NOT NULL AND due_date < date('now')
        """)
        cxp_vencidas = int(venc_row["vencidas"] or 0) if venc_row else 0

        utilidad_bruta = ingresos - costo_venta
        utilidad_neta  = ingresos - costo_venta - gastos - nomina
        margen_bruto   = (utilidad_bruta / ingresos * 100) if ingresos else 0
        margen_neto    = (utilidad_neta  / ingresos * 100) if ingresos else 0

        return {
            "date_from":        df,
            "date_to":          dt,
            "ingresos":         round(ingresos, 2),
            "costo_venta":      round(costo_venta, 2),
            "utilidad_bruta":   round(utilidad_bruta, 2),
            "margen_bruto":     round(margen_bruto, 2),
            "gastos":           round(gastos, 2),
            "nomina":           round(nomina, 2),
            "utilidad_neta":    round(utilidad_neta, 2),
            "margen_neto":      round(margen_neto, 2),
            "tickets":          tickets,
            "cxp_total":        round(cxp_total, 2),
            "cxp_count":        cxp_count,
            "cxp_vencidas":     cxp_vencidas,
            "cxc_total":        round(cxc_total, 2),
            "cxc_count":        cxc_count,
            "inv_val":          round(inv_val, 2),
            "activos_val":      round(activos_val, 2),
        }

    # ═════════════════════════════════════════════════════════════════════════
    # BALANCE GENERAL
    # ═════════════════════════════════════════════════════════════════════════

    def balance_general(
        self, branch_id: Optional[int] = None, as_of: Optional[str] = None
    ) -> Dict:
        """
        Balance General simplificado:
          ACTIVOS = inventario + activos_fijos + CXC
          PASIVOS = CXP + gastos_por_pagar
          PATRIMONIO = ACTIVOS - PASIVOS
        """
        fecha = as_of or date.today().isoformat()

        prod_activo = "AND activo = 1" if self._has_column("productos", "activo") else ""
        inv_expr = self._productos_inventory_expr()
        inv_row = self.db.fetchone(f"""
            SELECT COALESCE(SUM(existencia * {inv_expr}), 0) AS v
            FROM productos WHERE 1=1 {prod_activo}
        """)
        inventario = float(inv_row["v"] or 0) if inv_row else 0

        assets_activo = "AND activo=1" if self._has_column("assets", "activo") else ""
        af_row = self.db.fetchone(f"""
            SELECT COALESCE(SUM(valor_actual), 0) AS v
            FROM assets WHERE estado != 'dado_baja' {assets_activo}
        """)
        activos_fijos = float(af_row["v"] or 0) if af_row else 0

        cxc_row = self.db.fetchone("""
            SELECT COALESCE(SUM(balance), 0) AS v FROM accounts_receivable
            WHERE status IN ('pendiente','parcial')
        """)
        cxc = float(cxc_row["v"] or 0) if cxc_row else 0

        caja_row = self.db.fetchone("""
            SELECT COALESCE(SUM(
                CASE WHEN tipo IN ('venta','ingreso','apertura') THEN monto
                     ELSE -monto END
            ), 0) AS v FROM movimientos_caja
        """)
        caja = float(caja_row["v"] or 0) if caja_row else 0

        cxp_row = self.db.fetchone("""
            SELECT COALESCE(SUM(balance), 0) AS v FROM accounts_payable
            WHERE status IN ('pendiente','parcial')
        """)
        cxp = float(cxp_row["v"] or 0) if cxp_row else 0

        gasto_activo = "AND activo = 1" if self._has_column("gastos", "activo") else ""
        gastos_pagado_expr = "COALESCE(monto_pagado,0)" if self._has_column("gastos", "monto_pagado") else "0"
        gastos_pend_row = self.db.fetchone(f"""
            SELECT COALESCE(SUM(monto - {gastos_pagado_expr}), 0) AS v
            FROM gastos WHERE estado != 'pagado' {gasto_activo}
        """)
        gastos_pend = float(gastos_pend_row["v"] or 0) if gastos_pend_row else 0

        activos_corrientes  = round(inventario + cxc + max(caja, 0), 2)
        activos_no_corr     = round(activos_fijos, 2)
        total_activos       = round(activos_corrientes + activos_no_corr, 2)

        pasivos_corrientes  = round(cxp + gastos_pend, 2)
        total_pasivos       = round(pasivos_corrientes, 2)
        patrimonio          = round(total_activos - total_pasivos, 2)

        return {
            "as_of": fecha,
            "activos": {
                "corrientes": {
                    "inventario":   round(inventario, 2),
                    "cxc":          round(cxc, 2),
                    "caja":         round(max(caja, 0), 2),
                    "total":        activos_corrientes,
                },
                "no_corrientes": {
                    "activos_fijos": round(activos_fijos, 2),
                    "total":         activos_no_corr,
                },
                "total": total_activos,
            },
            "pasivos": {
                "corrientes": {
                    "cxp":          round(cxp, 2),
                    "gastos_pend":  round(gastos_pend, 2),
                    "total":        pasivos_corrientes,
                },
                "total": total_pasivos,
            },
            "patrimonio": patrimonio,
        }

    # ═════════════════════════════════════════════════════════════════════════
    # FLUJO DE CAJA
    # ═════════════════════════════════════════════════════════════════════════

    def flujo_caja(
        self,
        date_from: str,
        date_to: str,
        branch_id: Optional[int] = None,
    ) -> Dict:
        """Flujo de caja del período (entradas y salidas)."""
        bf = "AND v.sucursal_id = ?" if branch_id else ""
        bp = ([branch_id] if branch_id else [])

        # Entradas — ventas completadas
        ventas_row = self.db.fetchone(f"""
            SELECT COALESCE(SUM(total), 0) AS total
            FROM ventas v
            WHERE estado='completada' {bf}
              AND DATE(fecha) BETWEEN DATE(?) AND DATE(?)
        """, bp + [date_from, date_to])
        ventas_tot = float(ventas_row["total"] or 0)

        # Cobros de CXC
        cobros_row = self.db.fetchone("""
            SELECT COALESCE(SUM(monto), 0) AS total
            FROM ar_payments
            WHERE DATE(fecha) BETWEEN DATE(?) AND DATE(?)
        """, (date_from, date_to))
        cobros_cxc = float(cobros_row["total"] or 0) if cobros_row else 0

        # Salidas — gastos pagados
        gasto_activo = "AND activo = 1" if self._has_column("gastos", "activo") else ""
        gastos_row = self.db.fetchone(f"""
            SELECT COALESCE(SUM(monto), 0) AS total
            FROM gastos
            WHERE DATE(fecha) BETWEEN DATE(?) AND DATE(?)
              AND estado = 'pagado' {gasto_activo}
        """, (date_from, date_to))
        gastos_tot = float(gastos_row["total"] or 0) if gastos_row else 0

        # Pagos a proveedores (CXP abonos)
        pagos_prov_row = self.db.fetchone("""
            SELECT COALESCE(SUM(monto), 0) AS total FROM ap_payments
            WHERE DATE(fecha) BETWEEN DATE(?) AND DATE(?)
        """, (date_from, date_to))
        pagos_prov = float(pagos_prov_row["total"] or 0) if pagos_prov_row else 0

        # Nómina pagada
        nomina_date_col = self._resolve_column("nomina_pagos", "created_at", "fecha", "fecha_registro")
        nom_filter = f"DATE({nomina_date_col}) BETWEEN DATE(?) AND DATE(?)" if nomina_date_col else "1=1"
        nomina_row = self.db.fetchone(f"""
            SELECT COALESCE(SUM(total), 0) AS total FROM nomina_pagos
            WHERE {nom_filter}
              AND estado = 'pagado'
        """, (date_from, date_to) if nomina_date_col else ())
        nomina_tot = float(nomina_row["total"] or 0) if nomina_row else 0

        entradas = round(ventas_tot + cobros_cxc, 2)
        salidas  = round(gastos_tot + pagos_prov + nomina_tot, 2)
        neto     = round(entradas - salidas, 2)

        # Serie diaria para gráfica
        daily_rows = self.db.fetchall(f"""
            SELECT DATE(fecha) AS dia,
                   COALESCE(SUM(total), 0) AS ingresos
            FROM ventas v
            WHERE estado='completada' {bf}
              AND DATE(fecha) BETWEEN DATE(?) AND DATE(?)
            GROUP BY DATE(fecha) ORDER BY DATE(fecha)
        """, bp + [date_from, date_to])

        daily_gastos = self.db.fetchall(f"""
        SELECT DATE(fecha) AS dia,
                   COALESCE(SUM(monto), 0) AS egresos
            FROM gastos
            WHERE DATE(fecha) BETWEEN DATE(?) AND DATE(?)
              {gasto_activo}
            GROUP BY DATE(fecha) ORDER BY DATE(fecha)
        """, (date_from, date_to))

        return {
            "date_from": date_from,
            "date_to":   date_to,
            "entradas": {
                "ventas":       round(ventas_tot, 2),
                "cobros_cxc":   round(cobros_cxc, 2),
                "total":        entradas,
            },
            "salidas": {
                "gastos":       round(gastos_tot, 2),
                "pagos_prov":   round(pagos_prov, 2),
                "nomina":       round(nomina_tot, 2),
                "total":        salidas,
            },
            "flujo_neto": neto,
            "daily_ingresos": [dict(r) for r in daily_rows],
            "daily_egresos":  [dict(r) for r in daily_gastos],
        }

    # ═════════════════════════════════════════════════════════════════════════
    # CUENTAS POR PAGAR (CXP)
    # ═════════════════════════════════════════════════════════════════════════

    # ── CXP — delegación a AccountsPayableService ─────────────────────────────
    # DEPRECATED: usar AccountsPayableService directamente para código nuevo.

    def cuentas_por_pagar(
        self,
        status_filter: Optional[str] = None,
        supplier_id: Optional[int] = None,
    ) -> List[Dict]:
        # DEPRECATED: usar AccountsPayableService.listar()
        if self._aps:
            return self._aps.listar(status_filter=status_filter, supplier_id=supplier_id)
        return []

    def cxp_summary(self) -> Dict:
        # DEPRECATED: usar AccountsPayableService.summary()
        if self._aps:
            return self._aps.summary()
        return {}

    def crear_cxp(
        self,
        supplier_id: Optional[int],
        concepto: str,
        amount: float,
        due_date: Optional[str] = None,
        tipo: str = "factura",
        referencia: Optional[str] = None,
        ref_type: str = "manual",
        usuario: str = "Sistema",
        notas: Optional[str] = None,
    ) -> int:
        # DEPRECATED: usar AccountsPayableService.crear_cxp()
        if self._aps:
            return self._aps.crear_cxp(
                supplier_id=supplier_id, concepto=concepto, amount=amount,
                due_date=due_date, tipo=tipo, referencia=referencia,
                ref_type=ref_type, usuario=usuario, notas=notas,
            )
        return 0

    def abonar_cxp(
        self,
        ap_id: int,
        monto: float,
        metodo_pago: str = "efectivo",
        usuario: str = "Sistema",
        notas: Optional[str] = None,
    ) -> Dict:
        # DEPRECATED: usar AccountsPayableService.abonar_cxp()
        if self._aps:
            return self._aps.abonar_cxp(
                ap_id=ap_id, monto=monto, metodo_pago=metodo_pago,
                usuario=usuario, notas=notas,
            )
        return {}

    def historial_pagos_cxp(self, ap_id: int) -> List[Dict]:
        # DEPRECATED: usar AccountsPayableService.historial_pagos()
        if self._aps:
            return self._aps.historial_pagos(ap_id)
        return []

    # ═════════════════════════════════════════════════════════════════════════
    # CUENTAS POR COBRAR (CXC)
    # ═════════════════════════════════════════════════════════════════════════

    # ── CXC — delegación a AccountsReceivableService ──────────────────────────
    # DEPRECATED: usar AccountsReceivableService directamente para código nuevo.

    def cuentas_por_cobrar(self, status_filter: Optional[str] = None) -> List[Dict]:
        # DEPRECATED: usar AccountsReceivableService.listar()
        if self._ars:
            return self._ars.listar(status_filter=status_filter)
        return []

    def cxc_summary(self) -> Dict:
        # DEPRECATED: usar AccountsReceivableService.summary()
        if self._ars:
            return self._ars.summary()
        return {}

    def crear_cxc(
        self,
        cliente_id: Optional[int],
        concepto: str,
        amount: float,
        due_date: Optional[str] = None,
        venta_id: Optional[int] = None,
        usuario: str = "Sistema",
    ) -> int:
        # DEPRECATED: usar AccountsReceivableService.crear_cxc()
        if self._ars:
            return self._ars.crear_cxc(
                cliente_id=cliente_id, concepto=concepto, amount=amount,
                due_date=due_date, venta_id=venta_id, usuario=usuario,
            )
        return 0

    def cobrar_cxc(
        self,
        ar_id: int,
        monto: float,
        metodo_pago: str = "efectivo",
        usuario: str = "Sistema",
        notas: Optional[str] = None,
    ) -> Dict:
        # DEPRECATED: usar AccountsReceivableService.cobrar_cxc()
        if self._ars:
            return self._ars.cobrar_cxc(
                ar_id=ar_id, monto=monto, metodo_pago=metodo_pago,
                usuario=usuario, notas=notas,
            )
        return {}

    # ═════════════════════════════════════════════════════════════════════════
    # PROVEEDORES
    # ═════════════════════════════════════════════════════════════════════════

    def get_suppliers(
        self, activo_only: bool = True, buscar: Optional[str] = None
    ) -> List[Dict]:
        conds = ["1=1"]
        params = []
        if activo_only:
            conds.append("s.activo=1")
        if buscar:
            conds.append("(s.nombre LIKE ? OR s.rfc LIKE ?)")
            params += [f"%{buscar}%", f"%{buscar}%"]

        rows = self.db.fetchall(f"""
            SELECT s.*,
                   COUNT(DISTINCT ap.id) AS facturas_abiertas,
                   COALESCE(SUM(ap.balance),0) AS saldo_total
            FROM suppliers s
            LEFT JOIN accounts_payable ap
                ON ap.supplier_id = s.id AND ap.status IN ('pendiente','parcial')
            WHERE {' AND '.join(conds)}
            GROUP BY s.id ORDER BY s.nombre
        """, params)
        return [dict(r) for r in rows]

    def upsert_supplier(self, data: Dict) -> int:
        data = _validate_supplier_payload(data)
        sid = data.get("id")
        if sid:
            self.db.execute("""
                UPDATE suppliers
                SET nombre=?, rfc=?, telefono=?, email=?, direccion=?,
                    tipo=?, condiciones_pago=?, limite_credito=?,
                    banco=?, cuenta_bancaria=?, contacto=?, notas=?, activo=?
                WHERE id=?
            """, (data.get("nombre"), data.get("rfc"), data.get("telefono"),
                  data.get("email"), data.get("direccion"), data.get("tipo","general"),
                  data.get("condiciones_pago",30), data.get("limite_credito",0),
                  data.get("banco"), data.get("cuenta_bancaria"), data.get("contacto"),
                  data.get("notas"), int(data.get("activo",1)), sid))
        else:
            sid = new_uuid()  # identidad UUIDv7 (sin rowid implícito)
            self.db.execute("""
                INSERT INTO suppliers
                    (id, nombre, rfc, telefono, email, direccion, tipo,
                     condiciones_pago, limite_credito, banco, cuenta_bancaria,
                     contacto, notas, activo)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (sid, data.get("nombre",""), data.get("rfc"), data.get("telefono"),
                  data.get("email"), data.get("direccion"), data.get("tipo","general"),
                  data.get("condiciones_pago",30), data.get("limite_credito",0),
                  data.get("banco"), data.get("cuenta_bancaria"), data.get("contacto"),
                  data.get("notas"), 1))
        self.db.commit()
        return sid

    # ═════════════════════════════════════════════════════════════════════════
    # RECURSOS HUMANOS
    # ═════════════════════════════════════════════════════════════════════════

    def get_personal(
        self, activo: Optional[int] = None, buscar: Optional[str] = None
    ) -> List[Dict]:
        conds = ["1=1"]
        params = []
        if activo is not None:
            conds.append("activo=?"); params.append(activo)
        if buscar:
            conds.append("(nombre LIKE ? OR apellidos LIKE ? OR puesto LIKE ?)")
            params += [f"%{buscar}%", f"%{buscar}%", f"%{buscar}%"]
        rows = self.db.fetchall(f"""
            SELECT p.*,
                   (SELECT COALESCE(SUM(total),0) FROM nomina_pagos np
                    WHERE np.empleado_id = p.id AND np.estado='pagado') AS total_pagado
            FROM personal p
            WHERE {' AND '.join(conds)}
            ORDER BY p.nombre
        """, params)
        return [dict(r) for r in rows]

    def get_nomina_pagos(
        self, empleado_id: Optional[int] = None,
        date_from: Optional[str] = None, date_to: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        conds = ["1=1"]
        params = []
        if empleado_id:
            conds.append("np.empleado_id=?"); params.append(empleado_id)
        nomina_date_col = self._resolve_column("nomina_pagos", "created_at", "fecha", "fecha_registro")
        if date_from and nomina_date_col:
            conds.append(f"DATE(np.{nomina_date_col}) >= DATE(?)"); params.append(date_from)
        if date_to and nomina_date_col:
            conds.append(f"DATE(np.{nomina_date_col}) <= DATE(?)"); params.append(date_to)
        params.append(limit)
        order_col = nomina_date_col or "id"
        rows = self.db.fetchall(f"""
            SELECT np.*,
                   COALESCE(p.nombre,'?') || ' ' || COALESCE(p.apellidos,'') AS empleado_nombre,
                   COALESCE(p.puesto,'') AS puesto
            FROM nomina_pagos np
            LEFT JOIN personal p ON p.id = np.empleado_id
            WHERE {' AND '.join(conds)}
            ORDER BY np.{order_col} DESC LIMIT ?
        """, params)
        return [dict(r) for r in rows]

    def pagar_nomina(
        self,
        empleado_id: int,
        periodo_inicio: str,
        periodo_fin: str,
        salario_base: float,
        bonos: float = 0,
        deducciones: float = 0,
        metodo_pago: str = "efectivo",
        usuario: str = "Sistema",
        notas: Optional[str] = None,
    ) -> int:
        from backend.shared.ids import new_uuid
        total = round(salario_base + bonos - deducciones, 2)
        np_id = new_uuid()  # identidad UUIDv7 explícita (REGLA CERO)
        self.db.execute("""
            INSERT INTO nomina_pagos
                (id, empleado_id, periodo_inicio, periodo_fin, salario_base,
                 bonos, deducciones, total, metodo_pago, estado, usuario, notas)
            VALUES (?,?,?,?,?,?,?,?,?,'pagado',?,?)
        """, (np_id, empleado_id, periodo_inicio, periodo_fin, salario_base,
              bonos, deducciones, total, metodo_pago, usuario, notas))
        self.registrar_asiento(
            debe="gasto_nomina",
            haber="caja_bancos",
            concepto=f"Pago nómina empleado #{empleado_id}",
            monto=float(total or 0),
            modulo="rrhh",
            referencia_id=np_id,
            evento="NOMINA_PAGADA",
            metadata={
                "empleado_id": empleado_id,
                "periodo_inicio": periodo_inicio,
                "periodo_fin": periodo_fin,
            },
        )
        # FASE 9: commit extraído al caller para no romper SAVEPOINTs activos.
        # Callers que usan esta función directamente desde UI deben hacer commit.
        try:
            self.db.commit()
        except Exception:
            pass
        return np_id

    def costo_nomina_mes(self, date_from: str, date_to: str) -> float:
        nomina_date_col = self._resolve_column("nomina_pagos", "created_at", "fecha", "fecha_registro")
        nom_filter = f"DATE({nomina_date_col}) BETWEEN DATE(?) AND DATE(?)" if nomina_date_col else "1=1"
        row = self.db.fetchone(f"""
        SELECT COALESCE(SUM(total),0) AS total FROM nomina_pagos
            WHERE {nom_filter}
              AND estado='pagado'
        """, (date_from, date_to) if nomina_date_col else ())
        return float(row["total"] or 0) if row else 0

    # ═════════════════════════════════════════════════════════════════════════
    # SINCRONIZACIÓN AUTOMÁTICA
    # ═════════════════════════════════════════════════════════════════════════

    def sync_cxp_from_compras(self) -> int:
        """
        Genera CXP desde compras_inventariables con saldo > 0 que no estén ya.
        Toda la sincronización corre dentro de un SAVEPOINT para que un fallo
        parcial no deje CXPs a medias.
        """
        import uuid as _uuid
        sp = f"sp_sync_cxp_{_uuid.uuid4().hex[:6]}"
        try:
            self.db.execute(f"SAVEPOINT {sp}")
        except Exception:
            pass

        rows = self.db.fetchall("""
            SELECT ci.*, COALESCE(p.nombre, ci.proveedor) AS prod_nombre
            FROM compras_inventariables ci
            LEFT JOIN productos p ON p.id = ci.producto_id
            WHERE ci.saldo_pendiente > 0
              AND NOT EXISTS (
                  SELECT 1 FROM accounts_payable ap
                  WHERE ap.referencia = CAST(ci.id AS TEXT) AND ap.ref_type='compra_inv'
              )
        """)
        count = 0
        try:
            for r in rows:
                sup = self.db.fetchone(
                    "SELECT id FROM suppliers WHERE nombre=?", (r["proveedor"],)
                )
                sup_id = sup["id"] if sup else None
                self.crear_cxp(
                    supplier_id=sup_id,
                    concepto=f"Compra: {r['prod_nombre']}",
                    amount=float(r["costo_total"] or 0),
                    due_date=r["fecha_vencimiento"],
                    tipo="compra_inventario",
                    referencia=str(r["id"]),
                    ref_type="compra_inv",
                    usuario=r["usuario"] or "Sistema",
                )
                count += 1
            self.db.execute(f"RELEASE SAVEPOINT {sp}")
        except Exception:
            try:
                self.db.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            except Exception:
                pass
            raise
        return count

    def sync_cxc_from_ventas(self) -> int:
        """
        Genera CXC desde ventas a crédito que no estén ya.
        Toda la sincronización corre dentro de un SAVEPOINT para que un fallo
        parcial no deje CXCs a medias.
        """
        import uuid as _uuid
        sp = f"sp_sync_cxc_{_uuid.uuid4().hex[:6]}"
        try:
            self.db.execute(f"SAVEPOINT {sp}")
        except Exception:
            pass

        rows = self.db.fetchall("""
            SELECT v.*,
                   COALESCE(c.nombre,'') || ' ' || COALESCE(c.apellido_paterno,'') AS cliente_nombre
            FROM ventas v
            LEFT JOIN clientes c ON c.id = v.cliente_id
            WHERE v.credit_approved=1 AND v.estado='completada'
              AND NOT EXISTS (
                  SELECT 1 FROM accounts_receivable ar
                  WHERE ar.venta_id = v.id
              )
        """)
        count = 0
        try:
            for r in rows:
                fecha_val = r["fecha"] if "fecha" in r.keys() else None
                self.crear_cxc(
                    cliente_id=r["cliente_id"],
                    concepto=f"Venta {r['folio']} — {r['cliente_nombre']}",
                    amount=float(r["total"] or 0),
                    venta_id=r["id"],
                    due_date=(
                        (datetime.strptime(str(fecha_val)[:10], "%Y-%m-%d") +
                         timedelta(days=30)).strftime("%Y-%m-%d")
                        if fecha_val else None
                    ),
                    usuario="Sistema",
                )
                count += 1
            self.db.execute(f"RELEASE SAVEPOINT {sp}")
        except Exception:
            try:
                self.db.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            except Exception:
                pass
            raise
        return count

    # ── Módulo Caja ───────────────────────────────────────────────────────────

    def get_estado_turno(self, sucursal_id: int, usuario: str):
        """Retorna el turno abierto actual o None si la caja está cerrada.

        El ``id`` se devuelve como str (identidad UUIDv7-ready): el corte 200
        lo convertirá a TEXT y los callers no cambian (afinidad SQLite)."""
        try:
            row = self.db.execute(
                """SELECT id, fondo_inicial, fecha_apertura
                   FROM turnos_caja
                   WHERE sucursal_id=? AND cajero=? AND estado='abierto'
                   ORDER BY fecha_apertura DESC LIMIT 1""",
                (sucursal_id, usuario)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("id") is not None:
                d["id"] = str(d["id"])
            return d
        except Exception:
            return None

    def abrir_turno(self, sucursal_id: int, usuario: str, fondo_inicial: float) -> str:
        """Abre un nuevo turno de caja. Lanza si ya hay uno abierto.

        UUID-native (REGLA CERO): el turno_id es un UUIDv7 acuñado con
        ``new_uuid()`` e insertado explícitamente en ``turnos_caja.id`` (identidad
        acuñada, nunca el rowid implícito). El esquema born-clean define
        ``turnos_caja.id`` como TEXT.
        """
        existing = self.get_estado_turno(sucursal_id, usuario)
        if existing:
            raise ValueError("Ya hay un turno abierto para este cajero.")
        turno_id = new_uuid()
        self.db.execute(
            """INSERT INTO turnos_caja
               (id, sucursal_id, cajero, fondo_inicial, estado, fecha_apertura)
               VALUES (?,?,?,?,'abierto', datetime('now'))""",
            (turno_id, sucursal_id, usuario, fondo_inicial)
        )
        try: self.db.commit()
        except Exception: pass
        return turno_id

    def registrar_movimiento_manual(
        self, turno_id: str, sucursal_id: int,
        usuario: str, tipo: str, monto: float, concepto: str
    ) -> None:
        """Registra entrada o retiro manual en caja."""
        self.db.execute(
            """INSERT INTO movimientos_caja
               (id, turno_id, sucursal_id, tipo, monto, concepto, usuario, fecha)
               VALUES (?,?,?,?,?,?,?, datetime('now'))""",
            (new_uuid(), str(turno_id), sucursal_id, tipo, monto, concepto, usuario)
        )
        # FASE 9: no commit aquí — PurchaseService llama este método dentro
        # de un SAVEPOINT; el commit lo hace PurchaseService al hacer RELEASE.

    def generar_corte_z(
        self, turno_id: str, sucursal_id: str,
        usuario: str, efectivo_fisico: float
    ) -> dict:
        """Cierra el turno y calcula diferencias.

        La diferencia compara el efectivo contado contra el efectivo ESPERADO:
        solo ventas en efectivo (y la porción en efectivo de pagos mixtos).
        Tarjeta, transferencia y crédito NO forman parte del efectivo esperado.
        """
        turno_id = str(turno_id)
        sucursal_id = str(sucursal_id)
        # Total de ventas del turno (informativo, todos los medios de pago)
        row_v = self.db.execute(
            """SELECT COALESCE(SUM(total),0) FROM ventas
               WHERE sucursal_id=? AND usuario=?
               AND fecha >= (SELECT fecha_apertura FROM turnos_caja WHERE id=?)""",
            (sucursal_id, usuario, turno_id)
        ).fetchone()
        total_ventas = float(row_v[0]) if row_v else 0.0

        # Ventas en EFECTIVO del turno (lo único comparable contra lo contado)
        try:
            ventas_cols = {r[1] for r in self.db.execute("PRAGMA table_info(ventas)").fetchall()}
        except Exception:
            ventas_cols = set()
        if {"efectivo_recibido", "cambio"} <= ventas_cols:
            mixto_expr = "MAX(0, COALESCE(efectivo_recibido,0) - COALESCE(cambio,0))"
        else:
            mixto_expr = "0"
        row_ve = self.db.execute(
            f"""SELECT COALESCE(SUM(CASE
                     WHEN lower(COALESCE(forma_pago,'efectivo')) = 'efectivo'
                          THEN total
                     WHEN lower(COALESCE(forma_pago,'')) IN ('pago mixto','mixto')
                          THEN {mixto_expr}
                     ELSE 0 END), 0)
               FROM ventas
               WHERE sucursal_id=? AND usuario=?
               AND lower(COALESCE(estado,'completada')) NOT IN ('cancelada','anulada')
               AND fecha >= (SELECT fecha_apertura FROM turnos_caja WHERE id=?)""",
            (sucursal_id, usuario, turno_id)
        ).fetchone()
        ventas_efectivo = float(row_ve[0]) if row_ve else 0.0

        # Sumar movimientos
        row_m = self.db.execute(
            """SELECT
                 COALESCE(SUM(CASE WHEN tipo='INGRESO' THEN monto ELSE 0 END),0) as ingresos,
                 COALESCE(SUM(CASE WHEN tipo='RETIRO'  THEN monto ELSE 0 END),0) as retiros
               FROM movimientos_caja WHERE turno_id=?""",
            (turno_id,)
        ).fetchone()
        otros_ingresos = float(row_m['ingresos']) if row_m else 0.0
        retiros        = float(row_m['retiros'])  if row_m else 0.0

        row_t = self.db.execute(
            "SELECT fondo_inicial FROM turnos_caja WHERE id=?", (turno_id,)
        ).fetchone()
        fondo = float(row_t['fondo_inicial']) if row_t else 0.0

        esperado   = round(fondo + ventas_efectivo + otros_ingresos - retiros, 2)
        diferencia = round(efectivo_fisico - esperado, 2)

        # Cerrar turno
        self.db.execute(
            """UPDATE turnos_caja SET
               estado='cerrado', fecha_cierre=datetime('now'),
               total_ventas=?, efectivo_esperado=?,
               efectivo_contado=?, diferencia=?
               WHERE id=?""",
            (total_ventas, esperado, efectivo_fisico, diferencia, turno_id)
        )
        try: self.db.commit()
        except Exception: pass

        # Breakdown by forma_pago
        ventas_por_pago = {}
        try:
            rows_fp = self.db.execute("""
                SELECT COALESCE(forma_pago,'Efectivo') as fp,
                       COALESCE(SUM(total),0) as total_fp,
                       COUNT(*) as num_ventas
                FROM ventas
                WHERE sucursal_id=? AND estado='completada'
                  AND fecha >= (SELECT COALESCE(fecha_apertura, DATE('now'))
                                FROM turnos_caja WHERE id=?)
                GROUP BY fp
                ORDER BY total_fp DESC
            """, (sucursal_id, turno_id)).fetchall()
            for r in rows_fp:
                ventas_por_pago[r[0]] = {'total': float(r[1]), 'count': int(r[2])}
        except Exception:
            pass

        return {
            "turno_id":      turno_id,
            "fondo_inicial": fondo,
            "total_ventas":  total_ventas,
            "ventas_efectivo": ventas_efectivo,
            "otros_ingresos":otros_ingresos,
            "retiros":       retiros,
            "efectivo_esperado": esperado,
            "efectivo_contado":  efectivo_fisico,
            "diferencia":    diferencia,
            "ventas_por_pago": ventas_por_pago,
        }

    def get_movimientos_turno(self, turno_id: str) -> list:
        """Retorna los movimientos manuales del turno."""
        try:
            rows = self.db.execute(
                """SELECT tipo, monto, concepto, usuario, fecha
                   FROM movimientos_caja WHERE turno_id=? ORDER BY fecha""",
                (str(turno_id),)
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def register_income(self, amount: float, category: str, description: str,
                        payment_method: str, branch_id: int, user: str,
                        operation_id: str = "", reference_id: int = None) -> None:
        """Registra ingreso en movimientos_caja (llamado por SalesService)."""
        try:
            # Get open turno
            row = self.db.execute(
                "SELECT id FROM turnos_caja WHERE sucursal_id=? AND cajero=? AND estado='abierto' LIMIT 1",
                (branch_id, user)
            ).fetchone()
            turno_id = str(row['id']) if row else None
            self.db.execute(
                """INSERT INTO movimientos_caja
                   (id, turno_id, sucursal_id, tipo, monto, concepto, usuario, fecha)
                   VALUES (?,?,?,?,?,?,?,datetime('now'))""",
                (new_uuid(), turno_id, branch_id, 'VENTA', amount,
                 f"{category}: {description}", user)
            )
            # No commit here — caller (SalesService SAVEPOINT) owns the transaction
        except Exception as _ri_e:
            import logging as _lg
            _lg.getLogger(__name__).warning("register_income non-fatal: %s", _ri_e)
            # Non-fatal: the sale itself is still committed by the outer SAVEPOINT

    # ─── v13.4 spec methods ──────────────────────────────────────────────────

    def registrar_asiento(self, debe: str, haber: str, concepto: str,
                          monto: float, modulo: str = "",
                          referencia_id: int = None,
                          usuario_id: int = None,
                          sucursal_id: int = 1,
                          evento: str = "ASIENTO_MANUAL",
                          metadata: dict = None) -> int:
        """
        Fachada legacy de GeneralLedgerService.registrar_asiento().
        NO hace commit — el caller es responsable.
        """
        # DEPRECATED: usar GeneralLedgerService.registrar_asiento()
        _gl = getattr(self, "_gl", None)
        if _gl:
            return _gl.registrar_asiento(
                debe=debe, haber=haber, concepto=concepto, monto=monto,
                modulo=modulo, referencia_id=referencia_id, usuario_id=usuario_id,
                sucursal_id=sucursal_id, evento=evento, metadata=metadata,
            )
        # Fallback si GeneralLedgerService no está disponible (o __init__ bypass)
        import json as _json
        try:
            event_id = new_uuid()  # identidad UUIDv7 explícita (REGLA CERO)
            self.db.execute(
                """INSERT INTO financial_event_log
                   (id, evento, modulo, referencia_id, monto, cuenta_debe, cuenta_haber,
                    usuario_id, sucursal_id, metadata)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    event_id, evento, modulo or concepto, referencia_id,
                    monto, debe, haber,
                    usuario_id, sucursal_id,
                    _json.dumps({"concepto": concepto, **(metadata or {})},
                                ensure_ascii=False),
                )
            )
            return event_id
        except Exception as _e:
            import logging as _lg
            _lg.getLogger(__name__).warning("registrar_asiento non-fatal: %s", _e)
            return 0

    def obtener_ledger(self, cuenta: str, fecha_desde: str = None,
                       fecha_hasta: str = None) -> list:
        """
        Retorna asientos de financial_event_log filtrados por cuenta.
        DEPRECATED: usar GeneralLedgerService.obtener_ledger()
        """
        # DEPRECATED: usar GeneralLedgerService.obtener_ledger()
        _gl = getattr(self, "_gl", None)
        if _gl:
            return _gl.obtener_ledger(cuenta, fecha_desde, fecha_hasta)
        params: list = [cuenta, cuenta]
        where = "(cuenta_debe=? OR cuenta_haber=?)"
        if fecha_desde:
            where += " AND timestamp >= ?"; params.append(fecha_desde)
        if fecha_hasta:
            where += " AND timestamp <= ?"; params.append(fecha_hasta)
        try:
            rows = self.db.execute(
                f"SELECT * FROM financial_event_log WHERE {where} ORDER BY timestamp", params
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def generar_poliza_periodo(
        self,
        fecha_desde: str,
        fecha_hasta: str,
        sucursal_id: Optional[int] = None,
        cuentas: Optional[List[str]] = None,
        eventos: Optional[List[str]] = None,
    ) -> Dict:
        """Fachada legacy. DEPRECATED: usar GeneralLedgerService.generar_poliza_periodo()"""
        _gl = getattr(self, "_gl", None)
        if _gl:
            return _gl.generar_poliza_periodo(
                fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
                sucursal_id=sucursal_id, cuentas=cuentas, eventos=eventos,
            )
        return {
            "fecha_desde": fecha_desde, "fecha_hasta": fecha_hasta,
            "num_asientos": 0, "total_debe": 0.0, "total_haber": 0.0,
            "balanceado": True, "desbalance": 0.0, "movimientos": [],
        }

    def exportar_poliza_periodo(
        self,
        fecha_desde: str,
        fecha_hasta: str,
        sucursal_id: Optional[int] = None,
        cuentas: Optional[List[str]] = None,
        eventos: Optional[List[str]] = None,
        formato: str = "json",
    ) -> str:
        """Fachada legacy. DEPRECATED: usar GeneralLedgerService.exportar_poliza_periodo()"""
        _gl = getattr(self, "_gl", None)
        if _gl:
            return _gl.exportar_poliza_periodo(
                fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
                sucursal_id=sucursal_id, cuentas=cuentas,
                eventos=eventos, formato=formato,
            )
        poliza = self.generar_poliza_periodo(
            fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
            sucursal_id=sucursal_id, cuentas=cuentas, eventos=eventos,
        )
        fmt = (formato or "json").strip().lower()
        if fmt == "json":
            return json.dumps(poliza, ensure_ascii=False, indent=2)
        if fmt == "csv":
            out = StringIO()
            writer = csv.writer(out)
            writer.writerow([
                "id", "fecha", "evento", "modulo", "referencia_id",
                "debe", "haber", "monto", "sucursal_id", "metadata",
            ])
            for m in poliza.get("movimientos", []):
                writer.writerow([
                    m.get("id"), m.get("fecha"), m.get("evento"), m.get("modulo"),
                    m.get("referencia_id"), m.get("debe"), m.get("haber"),
                    m.get("monto"), m.get("sucursal_id"), m.get("metadata"),
                ])
            return out.getvalue()
        raise ValueError("Formato de exportación no soportado. Usa 'json' o 'csv'.")

    def validar_margen(self, producto_id: int, precio_venta: float,
                       margen_minimo: float = 0.05) -> bool:
        """
        Retorna True si el precio_venta supera el margen mínimo sobre el costo.
        margen_minimo: fracción (0.05 = 5%).
        Si no se encuentra el costo del producto, devuelve True (permisivo).
        """
        try:
            row = self.db.execute(
                "SELECT precio_costo FROM productos WHERE id=? LIMIT 1",
                (producto_id,)
            ).fetchone()
            if not row or not row["precio_costo"]:
                return True
            costo = float(row["precio_costo"])
            if costo <= 0:
                return True
            margen = (precio_venta - costo) / costo
            return margen >= margen_minimo
        except Exception:
            return True  # permisivo ante errores

    def controlar_credito(self, cliente_id: int, monto: float) -> dict:
        """
        Verifica si el cliente tiene crédito disponible para el monto solicitado.
        Returns: {"aprobado": bool, "disponible": float, "limite": float}
        """
        try:
            row = self.db.execute(
                "SELECT limite_credito FROM clientes WHERE id=? LIMIT 1",
                (cliente_id,)
            ).fetchone()
            limite = float(row["limite_credito"]) if row and row["limite_credito"] else 0.0

            saldo_row = self.db.execute(
                "SELECT COALESCE(SUM(saldo_pendiente),0) AS total "
                "FROM cuentas_por_cobrar WHERE cliente_id=? AND estado!='pagado'",
                (cliente_id,)
            ).fetchone()
            usado = float(saldo_row["total"]) if saldo_row else 0.0
            disponible = max(0.0, limite - usado)
            return {
                "aprobado": disponible >= monto,
                "disponible": disponible,
                "limite": limite,
                "usado": usado,
            }
        except Exception:
            return {"aprobado": True, "disponible": 0.0, "limite": 0.0, "usado": 0.0}

    def controlar_anticipo(self, venta_id: int, monto_anticipo: float,
                           usuario_id: int = None, sucursal_id: int = 1) -> dict:
        """
        Registra un anticipo contra una venta y loguea el asiento contable.
        Returns: {"registrado": bool, "anticipo_id": int}
        """
        try:
            anticipo_id = new_uuid()  # identidad UUIDv7 (sin rowid implícito)
            self.db.execute(
                """INSERT INTO anticipos (id, venta_id, monto, estado, usuario_id, sucursal_id)
                   VALUES (?, ?, ?, 'aplicado', ?, ?)""",
                (anticipo_id, venta_id, monto_anticipo, usuario_id, sucursal_id)
            )

            self.registrar_asiento(
                debe="caja",
                haber="anticipos_clientes",
                concepto=f"Anticipo venta #{venta_id}",
                monto=monto_anticipo,
                modulo="ventas",
                referencia_id=venta_id,
                usuario_id=usuario_id,
                sucursal_id=sucursal_id,
                evento="ANTICIPO_REGISTRADO",
            )
            self.db.commit()
            return {"registrado": True, "anticipo_id": anticipo_id}
        except Exception as _e:
            import logging as _lg
            _lg.getLogger(__name__).warning("controlar_anticipo: %s", _e)
            return {"registrado": False, "anticipo_id": 0}

    def calcular_margen_real(self, venta_id: int) -> float:
        """
        Calcula el margen real de una venta incluyendo:
        costo de productos + mermas asociadas + costos de delivery + comisiones.
        Returns: margen como fracción (0.20 = 20%). -1.0 si no se puede calcular.
        """
        try:
            # Ingreso bruto de la venta
            venta_row = self.db.execute(
                "SELECT total FROM ventas WHERE id=? LIMIT 1", (venta_id,)
            ).fetchone()
            if not venta_row:
                return -1.0
            total_venta = float(venta_row["total"])
            if total_venta <= 0:
                return -1.0

            # Costo directo de items
            costo_items = self.db.execute(
                """SELECT COALESCE(SUM(vi.cantidad * p.precio_costo), 0) AS costo
                   FROM venta_items vi
                   JOIN productos p ON p.id = vi.producto_id
                   WHERE vi.venta_id=?""",
                (venta_id,)
            ).fetchone()
            costo = float(costo_items["costo"]) if costo_items else 0.0

            # Costo de delivery (tabla opcional)
            try:
                delivery_row = self.db.execute(
                    "SELECT COALESCE(costo_envio, 0) AS costo_envio "
                    "FROM pedidos_delivery WHERE venta_id=? LIMIT 1",
                    (venta_id,)
                ).fetchone()
                costo += float(delivery_row["costo_envio"]) if delivery_row else 0.0
            except Exception:
                pass  # tabla puede no existir en todas las instalaciones

            # Comisiones aplicadas (tabla opcional)
            try:
                comision_row = self.db.execute(
                    "SELECT COALESCE(SUM(monto_comision), 0) AS total_comision "
                    "FROM comisiones WHERE venta_id=?",
                    (venta_id,)
                ).fetchone()
                costo += float(comision_row["total_comision"]) if comision_row else 0.0
            except Exception:
                pass  # tabla puede no existir en todas las instalaciones

            utilidad = total_venta - costo
            return round(utilidad / total_venta, 4)
        except Exception:
            return -1.0

    # ── v13.4: convenience wrappers around registrar_asiento ─────────────────

    def registrar_ingreso(self, concepto: str, monto: float, **kwargs) -> int:
        """Registra un ingreso: caja_ventas (debe) ↔ ventas_contado (haber)."""
        return self.registrar_asiento(
            debe=kwargs.get("debe", "caja_ventas"),
            haber=kwargs.get("haber", "ventas_contado"),
            concepto=concepto, monto=monto,
            modulo=kwargs.get("modulo", "ventas"),
            referencia_id=kwargs.get("referencia_id"),
            usuario_id=kwargs.get("usuario_id"),
            sucursal_id=kwargs.get("sucursal_id", 1),
            evento=kwargs.get("evento", "VENTA_COMPLETADA"),
            metadata=kwargs.get("metadata"),
        )

    def registrar_egreso(self, concepto: str, monto: float, **kwargs) -> int:
        """Registra un egreso: inventario_almacen (debe) ↔ cuentas_por_pagar (haber)."""
        return self.registrar_asiento(
            debe=kwargs.get("debe", "inventario_almacen"),
            haber=kwargs.get("haber", "cuentas_por_pagar"),
            concepto=concepto, monto=monto,
            modulo=kwargs.get("modulo", "compras"),
            referencia_id=kwargs.get("referencia_id"),
            usuario_id=kwargs.get("usuario_id"),
            sucursal_id=kwargs.get("sucursal_id", 1),
            evento=kwargs.get("evento", "COMPRA_REGISTRADA"),
            metadata=kwargs.get("metadata"),
        )

    def registrar_perdida(self, concepto: str, monto: float, **kwargs) -> int:
        """Registra una pérdida/merma: mermas_y_deterioro (debe) ↔ inventario_almacen (haber)."""
        return self.registrar_asiento(
            debe=kwargs.get("debe", "mermas_y_deterioro"),
            haber=kwargs.get("haber", "inventario_almacen"),
            concepto=concepto, monto=monto,
            modulo=kwargs.get("modulo", "merma"),
            referencia_id=kwargs.get("referencia_id"),
            usuario_id=kwargs.get("usuario_id"),
            sucursal_id=kwargs.get("sucursal_id", 1),
            evento=kwargs.get("evento", "MERMA_REGISTRADA"),
            metadata=kwargs.get("metadata"),
        )

    # ═════════════════════════════════════════════════════════════════════════
    # GESTIÓN DE EMPLEADOS - CRUD COMPLETO
    # ═════════════════════════════════════════════════════════════════════════

    def get_employee(self, employee_id: int) -> Optional[Dict]:
        """Obtiene un empleado por ID."""
        row = self.db.fetchone("SELECT * FROM personal WHERE id=?", (employee_id,))
        return dict(row) if row else None

    def upsert_employee(self, data: Dict) -> int:
        """Crea o actualiza un empleado."""
        required = ['nombre', 'salario']
        for field in required:
            if field not in data:
                raise ValueError(f"Campo requerido: {field}")
        
        employee_id = data.get('id')
        if employee_id:
            # Actualizar
            cur = self.db.execute("""
                UPDATE personal SET
                    nombre=?, apellidos=?, puesto=?, salario=?, 
                    fecha_ingreso=?, activo=?
                WHERE id=?
            """, (
                data['nombre'], data.get('apellidos'), data.get('puesto'),
                data['salario'], data.get('fecha_ingreso'), 
                data.get('activo', 1), employee_id
            ))
            self.db.commit()
            return employee_id
        else:
            # Crear
            from backend.shared.ids import new_uuid
            employee_id = new_uuid()  # identidad UUIDv7 explícita (REGLA CERO)
            self.db.execute("""
                INSERT INTO personal (id, nombre, apellidos, puesto, salario, fecha_ingreso, activo)
                VALUES (?, ?, ?, ?, ?, ?, 1)
            """, (
                employee_id,
                data['nombre'], data.get('apellidos'), data.get('puesto'),
                data['salario'], data.get('fecha_ingreso')
            ))
            self.db.commit()
            return employee_id

    def deactivate_employee(self, employee_id: int) -> bool:
        """Marca un empleado como inactivo."""
        self.db.execute("UPDATE personal SET activo=0 WHERE id=?", (employee_id,))
        self.db.commit()
        return True

    def get_products_list(self, active_only: bool = True) -> List[Dict]:
        """Obtiene lista de productos para combos."""
        if active_only:
            rows = self.db.fetchall("SELECT id, nombre, unidad FROM productos WHERE activo=1 ORDER BY nombre")
        else:
            rows = self.db.fetchall("SELECT id, nombre, unidad FROM productos ORDER BY nombre")
        return [dict(r) for r in rows]

    def get_supplier_by_name(self, name: str) -> Optional[Dict]:
        """Busca un proveedor por nombre exacto."""
        row = self.db.fetchone("SELECT id, nombre FROM proveedores WHERE nombre=?", (name,))
        return dict(row) if row else None

    def create_supplier_if_not_exists(self, name: str) -> str:
        """Crea un proveedor si no existe, retorna su ID UUIDv7."""
        existing = self.get_supplier_by_name(name)
        if existing:
            return existing['id']

        from backend.shared.ids import new_uuid
        proveedor_id = new_uuid()  # identidad UUIDv7 explícita (REGLA CERO)
        self.db.execute(
            "INSERT INTO proveedores (id, nombre) VALUES (?, ?)", (proveedor_id, name)
        )
        self.db.commit()
        return proveedor_id

    def get_expense_categories(self) -> List[str]:
        """Obtiene lista de categorías únicas de gastos."""
        rows = self.db.fetchall("SELECT DISTINCT categoria FROM gastos WHERE categoria IS NOT NULL ORDER BY categoria")
        return [r['categoria'] for r in rows]

    def get_compras_inventariables(self, limit: int = 200) -> List[Dict]:
        """Obtiene compras inventariables con información de producto.
        
        Args:
            limit: Máximo número de registros a retornar (default 200)
            
        Returns:
            Lista de diccionarios con datos de compras inventariables
        """
        sql = """
            SELECT ci.id, COALESCE(p.nombre,'?') AS producto,
                   ci.proveedor, ci.volumen, ci.unidad, ci.costo_unitario,
                   ci.costo_total, ci.monto_pagado, ci.saldo_pendiente,
                   ci.estado, ci.fecha
            FROM compras_inventariables ci
            LEFT JOIN productos p ON p.id = ci.producto_id
            ORDER BY ci.fecha DESC
            LIMIT ?
        """
        rows = self.db.fetchall(sql, (limit,))
        return [dict(r) for r in rows]
