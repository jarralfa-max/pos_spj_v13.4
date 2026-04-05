
# core/services/enterprise/finance_service.py
# ── FinanceService — Motor Financiero Enterprise SPJ POS ─────────────────────
#
# Centraliza TODAS las consultas financieras del sistema.
# NINGUNA ventana UI ejecuta SQL directamente.
#
# Métodos públicos:
#   balance_general()         — Activos / Pasivos / Patrimonio
#   flujo_caja()              — Entradas y salidas por período
#   gastos_mes()              — Gastos agrupados por categoría
#   cuentas_por_pagar()       — CXP con vencimiento y aging
#   cuentas_por_cobrar()      — CXC con días vencidos
#   dashboard_kpis()          — KPIs financieros ejecutivos
#   get_suppliers()           — Catálogo de proveedores
#   get_assets()              — Activos fijos con depreciación
#   get_maintenance()         — Historial de mantenimientos
#   get_personal()            — Plantilla laboral
#   get_nomina_pagos()        — Historial de nómina
#   crear_cxp()               — Crear cuenta por pagar manual
#   abonar_cxp()              — Registrar pago parcial o total CXP
#   crear_cxc()               — Crear cuenta por cobrar manual
#   cobrar_cxc()              — Registrar cobro CXC
#   registrar_asset()         — Alta de activo fijo
#   registrar_mantenimiento() — Alta de mantenimiento
#   pagar_nomina()            — Registrar pago de nómina
#   sync_cxp_from_compras()   — Sincronizar CXP desde compras_inventariables
#   sync_cxc_from_ventas()    — Sincronizar CXC desde ventas a crédito
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

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


class FinanceService:

    def __init__(self, db):
        """
        db: objeto con métodos fetchone(sql,params), fetchall(sql,params),
            execute(sql,params), conn (sqlite3.Connection).
        Compatible con el helper DB del sistema SPJ.
        """
        self.db = db

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
        gasto_row = self.db.fetchone("""
            SELECT COALESCE(SUM(monto), 0) AS gastos
            FROM gastos
            WHERE DATE(fecha) BETWEEN DATE(?) AND DATE(?)
              AND activo = 1
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
        nom_row = self.db.fetchone("""
            SELECT COALESCE(SUM(total), 0) AS nomina
            FROM nomina_pagos
            WHERE DATE(created_at) BETWEEN DATE(?) AND DATE(?)
              AND estado = 'pagado'
        """, (df, dt))
        nomina = float(nom_row["nomina"] or 0) if nom_row else 0

        # Valor inventario
        inv_row = self.db.fetchone("""
            SELECT COALESCE(SUM(existencia * COALESCE(precio_compra, costo, 0)), 0) AS inv_val
            FROM productos WHERE activo = 1
        """)
        inv_val = float(inv_row["inv_val"] or 0) if inv_row else 0

        # Activos fijos
        assets_row = self.db.fetchone("""
            SELECT COALESCE(SUM(valor_actual), 0) AS activos_total
            FROM assets WHERE activo = 1 AND estado != 'dado_baja'
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

        inv_row = self.db.fetchone("""
            SELECT COALESCE(SUM(existencia * COALESCE(precio_compra,costo,0)), 0) AS v
            FROM productos WHERE activo=1
        """)
        inventario = float(inv_row["v"] or 0) if inv_row else 0

        af_row = self.db.fetchone("""
            SELECT COALESCE(SUM(valor_actual), 0) AS v
            FROM assets WHERE activo=1 AND estado != 'dado_baja'
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

        gastos_pend_row = self.db.fetchone("""
            SELECT COALESCE(SUM(monto - COALESCE(monto_pagado,0)), 0) AS v
            FROM gastos WHERE estado != 'pagado' AND activo=1
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
        gastos_row = self.db.fetchone("""
            SELECT COALESCE(SUM(monto), 0) AS total
            FROM gastos
            WHERE DATE(fecha) BETWEEN DATE(?) AND DATE(?)
              AND estado = 'pagado' AND activo = 1
        """, (date_from, date_to))
        gastos_tot = float(gastos_row["total"] or 0) if gastos_row else 0

        # Pagos a proveedores (CXP abonos)
        pagos_prov_row = self.db.fetchone("""
            SELECT COALESCE(SUM(monto), 0) AS total FROM ap_payments
            WHERE DATE(fecha) BETWEEN DATE(?) AND DATE(?)
        """, (date_from, date_to))
        pagos_prov = float(pagos_prov_row["total"] or 0) if pagos_prov_row else 0

        # Nómina pagada
        nomina_row = self.db.fetchone("""
            SELECT COALESCE(SUM(total), 0) AS total FROM nomina_pagos
            WHERE DATE(created_at) BETWEEN DATE(?) AND DATE(?)
              AND estado = 'pagado'
        """, (date_from, date_to))
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

        daily_gastos = self.db.fetchall("""
        SELECT DATE(fecha) AS dia,
                   COALESCE(SUM(monto), 0) AS egresos
            FROM gastos
            WHERE DATE(fecha) BETWEEN DATE(?) AND DATE(?)
              AND activo=1
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
    # GASTOS POR MES
    # ═════════════════════════════════════════════════════════════════════════

    def gastos_mes(
        self, date_from: str, date_to: str
    ) -> Dict:
        """Gastos agrupados por categoría y estado para el período."""
        by_cat = self.db.fetchall("""
            SELECT categoria,
                   COUNT(*)            AS num_registros,
                   SUM(monto)          AS total,
                   SUM(COALESCE(monto_pagado,0)) AS pagado,
                   SUM(monto - COALESCE(monto_pagado,0)) AS pendiente
            FROM gastos
            WHERE DATE(fecha) BETWEEN DATE(?) AND DATE(?)
              AND activo=1
            GROUP BY categoria
            ORDER BY total DESC
        """, (date_from, date_to))

        detalle = self.db.fetchall("""
        SELECT g.id, g.fecha, g.categoria, g.concepto, g.descripcion,
                   g.monto, g.monto_pagado, g.estado, g.metodo_pago,
                   g.recurrente, g.usuario,
                   COALESCE(p.nombre, g.referencia, '') AS proveedor
            FROM gastos g
            LEFT JOIN proveedores p ON p.id = g.proveedor_id
            WHERE DATE(g.fecha) BETWEEN DATE(?) AND DATE(?)
              AND g.activo=1
            ORDER BY g.fecha DESC
        """, (date_from, date_to))

        total_general = sum(float(r["total"] or 0) for r in by_cat)
        return {
            "date_from":    date_from,
            "date_to":      date_to,
            "total":        round(total_general, 2),
            "by_categoria": [dict(r) for r in by_cat],
            "detalle":      [dict(r) for r in detalle],
        }

    # ═════════════════════════════════════════════════════════════════════════
    # CUENTAS POR PAGAR (CXP)
    # ═════════════════════════════════════════════════════════════════════════

    def cuentas_por_pagar(
        self,
        status_filter: Optional[str] = None,
        supplier_id: Optional[int] = None,
    ) -> List[Dict]:
        """CXP con aging, proveedor y totales."""
        conds = ["ap.status IN ('pendiente','parcial')"]
        params = []
        if status_filter:
            conds = [f"ap.status = ?"]
            params.append(status_filter)
        if supplier_id:
            conds.append("ap.supplier_id = ?")
            params.append(supplier_id)

        where = "WHERE " + " AND ".join(conds) if conds else ""
        rows = self.db.fetchall(f"""
            SELECT ap.*,
                   COALESCE(s.nombre, '—') AS supplier_nombre,
                   COALESCE(s.telefono,'') AS supplier_telefono
            FROM accounts_payable ap
            LEFT JOIN suppliers s ON s.id = ap.supplier_id
            {where}
            ORDER BY COALESCE(ap.due_date,'9999-12-31'), ap.created_at DESC
        """, params)

        result = []
        for r in rows:
            d = dict(r)
            d["aging"] = _aging(d.get("due_date"))
            d["dias_vencido"] = max(0, (date.today() - date.fromisoformat(
                str(d["due_date"])[:10])).days) if d.get("due_date") else 0
            result.append(d)
        return result

    def cxp_summary(self) -> Dict:
        row = self.db.fetchone("""
            SELECT
                COALESCE(SUM(CASE WHEN status='pendiente' THEN balance END),0) AS pendiente,
                COALESCE(SUM(CASE WHEN status='parcial'   THEN balance END),0) AS parcial,
                COUNT(CASE WHEN status IN ('pendiente','parcial')
                           AND due_date IS NOT NULL AND due_date < date('now') THEN 1 END) AS vencidas
            FROM accounts_payable
        """)
        return dict(row) if row else {}

    def crear_cxp(
        self,
        supplier_id: Optional[int],
        concepto: str,
        amount: float,
        due_date: Optional[str],
        tipo: str = "factura",
        referencia: Optional[str] = None,
        ref_type: str = "manual",
        usuario: str = "Sistema",
        notas: Optional[str] = None,
    ) -> int:
        """Crea una nueva CXP. Retorna el id creado."""
        folio = f"CXP-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        cur = self.db.execute("""
            INSERT INTO accounts_payable
                (folio, supplier_id, concepto, amount, balance,
                 due_date, status, tipo, referencia, ref_type, usuario, notas)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (folio, supplier_id, concepto, amount, amount,
              due_date, "pendiente", tipo, referencia, ref_type, usuario, notas))
        self.db.conn.commit()
        return cur.lastrowid

    def abonar_cxp(
        self,
        ap_id: int,
        monto: float,
        metodo_pago: str = "efectivo",
        usuario: str = "Sistema",
        notas: Optional[str] = None,
    ) -> Dict:
        """Registra abono a CXP. Actualiza balance y status."""
        row = self.db.fetchone(
            "SELECT balance, status FROM accounts_payable WHERE id=?", (ap_id,)
        )
        if not row:
            raise ValueError(f"CXP {ap_id} no encontrada")
        balance = float(row["balance"])
        if monto > balance:
            monto = balance

        nuevo_balance = round(balance - monto, 2)
        nuevo_status  = "pagado" if nuevo_balance <= 0 else "parcial"

        self.db.execute("""
            UPDATE accounts_payable
            SET balance=?, status=?, updated_at=datetime('now')
            WHERE id=?
        """, (nuevo_balance, nuevo_status, ap_id))

        self.db.execute("""
        INSERT INTO ap_payments (ap_id, monto, metodo_pago, usuario, notas)
            VALUES (?,?,?,?,?)
        """, (ap_id, monto, metodo_pago, usuario, notas))

        self.db.conn.commit()
        return {"nuevo_balance": nuevo_balance, "nuevo_status": nuevo_status}

    def historial_pagos_cxp(self, ap_id: int) -> List[Dict]:
        rows = self.db.fetchall(
            "SELECT * FROM ap_payments WHERE ap_id=? ORDER BY fecha DESC", (ap_id,)
        )
        return [dict(r) for r in rows]

    # ═════════════════════════════════════════════════════════════════════════
    # CUENTAS POR COBRAR (CXC)
    # ═════════════════════════════════════════════════════════════════════════

    def cuentas_por_cobrar(
        self, status_filter: Optional[str] = None
    ) -> List[Dict]:
        """CXC con aging y datos de cliente."""
        conds = ["ar.status IN ('pendiente','parcial','vencido')"]
        params = []
        if status_filter:
            conds = [f"ar.status = ?"]
            params.append(status_filter)

        where = "WHERE " + " AND ".join(conds)
        rows = self.db.fetchall(f"""
            SELECT ar.*,
                   COALESCE(c.nombre,'') || ' ' || COALESCE(c.apellido_paterno,'')
                       AS cliente_nombre,
                   COALESCE(c.telefono,'') AS cliente_telefono
            FROM accounts_receivable ar
            LEFT JOIN clientes c ON c.id = ar.cliente_id
            {where}
            ORDER BY COALESCE(ar.due_date,'9999-12-31'), ar.created_at DESC
        """, params)

        result = []
        for r in rows:
            d = dict(r)
            d["aging"] = _aging(d.get("due_date"))
            d["dias_vencido"] = max(0, (date.today() - date.fromisoformat(
                str(d["due_date"])[:10])).days) if d.get("due_date") else 0
            result.append(d)
        return result

    def cxc_summary(self) -> Dict:
        row = self.db.fetchone("""
            SELECT COALESCE(SUM(balance),0) AS total,
                   COUNT(*) AS count,
                   COUNT(CASE WHEN due_date IS NOT NULL AND due_date < date('now') THEN 1 END) AS vencidas
            FROM accounts_receivable WHERE status IN ('pendiente','parcial','vencido')
        """)
        return dict(row) if row else {}

    def crear_cxc(
        self,
        cliente_id: Optional[int],
        concepto: str,
        amount: float,
        due_date: Optional[str] = None,
        venta_id: Optional[int] = None,
        usuario: str = "Sistema",
    ) -> int:
        folio = f"CXC-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        cur = self.db.execute("""
            INSERT INTO accounts_receivable
                (folio, cliente_id, venta_id, concepto, amount, balance,
                 due_date, status, tipo, usuario)
            VALUES (?,?,?,?,?,?,?,'pendiente','manual',?)
        """, (folio, cliente_id, venta_id, concepto, amount, amount,
              due_date, usuario))
        self.db.conn.commit()
        return cur.lastrowid

    def cobrar_cxc(
        self,
        ar_id: int,
        monto: float,
        metodo_pago: str = "efectivo",
        usuario: str = "Sistema",
        notas: Optional[str] = None,
    ) -> Dict:
        row = self.db.fetchone(
            "SELECT balance FROM accounts_receivable WHERE id=?", (ar_id,)
        )
        if not row:
            raise ValueError(f"CXC {ar_id} no encontrada")
        balance = float(row["balance"])
        if monto > balance:
            monto = balance

        nuevo_balance = round(balance - monto, 2)
        nuevo_status  = "pagado" if nuevo_balance <= 0 else "parcial"

        self.db.execute("""
            UPDATE accounts_receivable
            SET balance=?, status=?, updated_at=datetime('now')
            WHERE id=?
        """, (nuevo_balance, nuevo_status, ar_id))

        self.db.execute("""
        INSERT INTO ar_payments (ar_id, monto, metodo_pago, usuario, notas)
            VALUES (?,?,?,?,?)
        """, (ar_id, monto, metodo_pago, usuario, notas))

        self.db.conn.commit()
        return {"nuevo_balance": nuevo_balance, "nuevo_status": nuevo_status}

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
            cur = self.db.execute("""
                INSERT INTO suppliers
                    (nombre, rfc, telefono, email, direccion, tipo,
                     condiciones_pago, limite_credito, banco, cuenta_bancaria,
                     contacto, notas, activo)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (data.get("nombre",""), data.get("rfc"), data.get("telefono"),
                  data.get("email"), data.get("direccion"), data.get("tipo","general"),
                  data.get("condiciones_pago",30), data.get("limite_credito",0),
                  data.get("banco"), data.get("cuenta_bancaria"), data.get("contacto"),
                  data.get("notas"), 1))
            sid = cur.lastrowid
        self.db.conn.commit()
        return sid

    # ═════════════════════════════════════════════════════════════════════════
    # ACTIVOS FIJOS
    # ═════════════════════════════════════════════════════════════════════════

    def get_assets(
        self, estado: Optional[str] = None, tipo: Optional[str] = None
    ) -> List[Dict]:
        conds = ["activo=1"]
        params = []
        if estado:
            conds.append("estado=?"); params.append(estado)
        if tipo:
            conds.append("tipo=?"); params.append(tipo)
        rows = self.db.fetchall(f"""
            SELECT a.*,
                   (SELECT COUNT(*) FROM asset_maintenance m WHERE m.asset_id=a.id) AS num_mant,
                   (SELECT COALESCE(SUM(costo),0) FROM asset_maintenance m WHERE m.asset_id=a.id) AS costo_mant
            FROM assets a
            WHERE {' AND '.join(conds)}
            ORDER BY a.tipo, a.nombre
        """, params)
        return [dict(r) for r in rows]

    def upsert_asset(self, data: Dict) -> int:
        aid = data.get("id")
        if aid:
            self.db.execute("""
                UPDATE assets SET nombre=?, tipo=?, marca=?, modelo=?,
                    numero_serie=?, fecha_compra=?, valor_compra=?,
                    valor_actual=?, depreciacion_anual=?, estado=?,
                    ubicacion=?, sucursal_id=?, responsable=?,
                    proveedor=?, notas=?
                WHERE id=?
            """, (data["nombre"], data.get("tipo","equipo"), data.get("marca"),
                  data.get("modelo"), data.get("numero_serie"), data.get("fecha_compra"),
                  data.get("valor_compra",0), data.get("valor_actual",0),
                  data.get("depreciacion_anual",0), data.get("estado","activo"),
                  data.get("ubicacion"), data.get("sucursal_id",1),
                  data.get("responsable"), data.get("proveedor"), data.get("notas"),
                  aid))
        else:
            codigo = f"ACT-{datetime.now().strftime('%y%m%d%H%M%S')}"
            cur = self.db.execute("""
                INSERT INTO assets (codigo, nombre, tipo, marca, modelo,
                    numero_serie, fecha_compra, valor_compra, valor_actual,
                    depreciacion_anual, estado, ubicacion, sucursal_id,
                    responsable, proveedor, notas)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (codigo, data["nombre"], data.get("tipo","equipo"), data.get("marca"),
                  data.get("modelo"), data.get("numero_serie"), data.get("fecha_compra"),
                  data.get("valor_compra",0), data.get("valor_actual", data.get("valor_compra",0)),
                  data.get("depreciacion_anual",0), data.get("estado","activo"),
                  data.get("ubicacion"), data.get("sucursal_id",1),
                  data.get("responsable"), data.get("proveedor"), data.get("notas")))
            aid = cur.lastrowid
        self.db.conn.commit()
        return aid

    def get_maintenance(
        self, asset_id: Optional[int] = None, limit: int = 100
    ) -> List[Dict]:
        if asset_id:
            rows = self.db.fetchall("""
                SELECT m.*, a.nombre AS activo_nombre, a.tipo AS activo_tipo
                FROM asset_maintenance m
                JOIN assets a ON a.id = m.asset_id
                WHERE m.asset_id=?
                ORDER BY m.fecha DESC LIMIT ?
            """, (asset_id, limit))
        else:
            rows = self.db.fetchall("""
        SELECT m.*, a.nombre AS activo_nombre, a.tipo AS activo_tipo
                FROM asset_maintenance m
                JOIN assets a ON a.id = m.asset_id
                ORDER BY m.fecha DESC LIMIT ?
            """, (limit,))
        return [dict(r) for r in rows]

    def registrar_mantenimiento(self, data: Dict) -> int:
        cur = self.db.execute("""
        INSERT INTO asset_maintenance
                (asset_id, tipo, fecha, descripcion, costo,
                 responsable, proveedor, estado, proxima_revision, notas)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (data["asset_id"], data.get("tipo","preventivo"),
              data.get("fecha", date.today().isoformat()),
              data.get("descripcion"), data.get("costo",0),
              data.get("responsable"), data.get("proveedor"),
              data.get("estado","completado"),
              data.get("proxima_revision"), data.get("notas")))
        self.db.conn.commit()
        return cur.lastrowid

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
        if date_from:
            conds.append("DATE(np.created_at) >= DATE(?)"); params.append(date_from)
        if date_to:
            conds.append("DATE(np.created_at) <= DATE(?)"); params.append(date_to)
        params.append(limit)
        rows = self.db.fetchall(f"""
            SELECT np.*,
                   COALESCE(p.nombre,'?') || ' ' || COALESCE(p.apellidos,'') AS empleado_nombre,
                   COALESCE(p.puesto,'') AS puesto
            FROM nomina_pagos np
            LEFT JOIN personal p ON p.id = np.empleado_id
            WHERE {' AND '.join(conds)}
            ORDER BY np.created_at DESC LIMIT ?
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
        total = round(salario_base + bonos - deducciones, 2)
        cur = self.db.execute("""
            INSERT INTO nomina_pagos
                (empleado_id, periodo_inicio, periodo_fin, salario_base,
                 bonos, deducciones, total, metodo_pago, estado, usuario, notas)
            VALUES (?,?,?,?,?,?,?,'efectivo','pagado',?,?)
        """, (empleado_id, periodo_inicio, periodo_fin, salario_base,
              bonos, deducciones, total, usuario, notas))
        self.db.conn.commit()
        return cur.lastrowid

    def costo_nomina_mes(self, date_from: str, date_to: str) -> float:
        row = self.db.fetchone("""
        SELECT COALESCE(SUM(total),0) AS total FROM nomina_pagos
            WHERE DATE(created_at) BETWEEN DATE(?) AND DATE(?)
              AND estado='pagado'
        """, (date_from, date_to))
        return float(row["total"] or 0) if row else 0

    # ═════════════════════════════════════════════════════════════════════════
    # SINCRONIZACIÓN AUTOMÁTICA
    # ═════════════════════════════════════════════════════════════════════════

    def sync_cxp_from_compras(self) -> int:
        """Genera CXP desde compras_inventariables con saldo > 0 que no estén ya."""
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
        return count

    def sync_cxc_from_ventas(self) -> int:
        """Genera CXC desde ventas a crédito que no estén ya."""
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
        return count

    # ── Módulo Caja ───────────────────────────────────────────────────────────

    def get_estado_turno(self, sucursal_id: int, usuario: str):
        """Retorna el turno abierto actual o None si la caja está cerrada."""
        try:
            row = self.db.execute(
                """SELECT id, fondo_inicial, fecha_apertura
                   FROM turnos_caja
                   WHERE sucursal_id=? AND cajero=? AND estado='abierto'
                   ORDER BY fecha_apertura DESC LIMIT 1""",
                (sucursal_id, usuario)
            ).fetchone()
            return dict(row) if row else None
        except Exception:
            return None

    def abrir_turno(self, sucursal_id: int, usuario: str, fondo_inicial: float) -> int:
        """Abre un nuevo turno de caja. Lanza si ya hay uno abierto."""
        existing = self.get_estado_turno(sucursal_id, usuario)
        if existing:
            raise ValueError("Ya hay un turno abierto para este cajero.")
        cur = self.db.execute(
            """INSERT INTO turnos_caja
               (sucursal_id, cajero, fondo_inicial, estado, fecha_apertura)
               VALUES (?,?,?,'abierto', datetime('now'))""",
            (sucursal_id, usuario, fondo_inicial)
        )
        try: self.db.commit()
        except Exception: pass
        return cur.lastrowid

    def registrar_movimiento_manual(
        self, turno_id: int, sucursal_id: int,
        usuario: str, tipo: str, monto: float, concepto: str
    ) -> None:
        """Registra entrada o retiro manual en caja."""
        self.db.execute(
            """INSERT INTO movimientos_caja
               (turno_id, sucursal_id, tipo, monto, concepto, usuario, fecha)
               VALUES (?,?,?,?,?,?, datetime('now'))""",
            (turno_id, sucursal_id, tipo, monto, concepto, usuario)
        )
        try: self.db.commit()
        except Exception: pass

    def generar_corte_z(
        self, turno_id: int, sucursal_id: int,
        usuario: str, efectivo_fisico: float
    ) -> dict:
        """Cierra el turno y calcula diferencias."""
        # Sumar ventas del turno
        row_v = self.db.execute(
            """SELECT COALESCE(SUM(total),0) FROM ventas
               WHERE sucursal_id=? AND usuario=?
               AND fecha >= (SELECT fecha_apertura FROM turnos_caja WHERE id=?)""",
            (sucursal_id, usuario, turno_id)
        ).fetchone()
        total_ventas = float(row_v[0]) if row_v else 0.0

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

        esperado   = fondo + total_ventas + otros_ingresos - retiros
        diferencia = efectivo_fisico - esperado

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
            "otros_ingresos":otros_ingresos,
            "retiros":       retiros,
            "efectivo_esperado": esperado,
            "efectivo_contado":  efectivo_fisico,
            "diferencia":    diferencia,
            "ventas_por_pago": ventas_por_pago,
        }

    def get_movimientos_turno(self, turno_id: int) -> list:
        """Retorna los movimientos manuales del turno."""
        try:
            rows = self.db.execute(
                """SELECT tipo, monto, concepto, usuario, fecha
                   FROM movimientos_caja WHERE turno_id=? ORDER BY fecha""",
                (turno_id,)
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
            turno_id = row['id'] if row else None
            self.db.execute(
                """INSERT INTO movimientos_caja
                   (turno_id, sucursal_id, tipo, monto, concepto, usuario, fecha)
                   VALUES (?,?,?,?,?,?,datetime('now'))""",
                (turno_id, branch_id, 'VENTA', amount,
                 f"{category}: {description}", user)
            )
            # No commit here — caller (SalesService SAVEPOINT) owns the transaction
        except Exception as _ri_e:
            import logging as _lg
            _lg.getLogger(__name__).warning("register_income non-fatal: %s", _ri_e)
            # Non-fatal: the sale itself is still committed by the outer SAVEPOINT
