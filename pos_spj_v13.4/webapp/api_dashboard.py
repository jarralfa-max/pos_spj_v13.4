
# webapp/api_dashboard.py — SPJ POS v13.4
"""
Endpoints REST del Dashboard Web.
Expone datos agregados para el frontend HTML/JS sin SQL directo en la UI.

Arquitectura:
    Frontend (JS) → GET /api/dashboard/* → api_dashboard.py
                                              └→ core/services/* (sin SQL)
                                              └→ DB via core.db.connection (solo aquí)

Todos los endpoints retornan JSON y son agregados por periodo:
    ?periodo=hoy | semana | mes | trimestre
"""
from __future__ import annotations
import json
import logging
from datetime import date, datetime, timedelta
from typing import Any

logger = logging.getLogger("spj.api_dashboard")


# ─── Helpers de fecha ─────────────────────────────────────────────────────────

def _parse_periodo(periodo: str) -> tuple[str, str]:
    """Retorna (fecha_desde, fecha_hasta) en formato ISO para el periodo dado."""
    hoy = date.today()
    if periodo == "semana":
        inicio = hoy - timedelta(days=hoy.weekday())
    elif periodo == "mes":
        inicio = hoy.replace(day=1)
    elif periodo == "trimestre":
        mes_inicio = ((hoy.month - 1) // 3) * 3 + 1
        inicio = hoy.replace(month=mes_inicio, day=1)
    else:  # hoy
        inicio = hoy
    return inicio.isoformat(), hoy.isoformat()


def _fmt_money(v) -> float:
    try:
        return round(float(v or 0), 2)
    except (TypeError, ValueError):
        return 0.0


# ─── Queries SQL centralizadas (solo aquí, nunca en UI) ───────────────────────

def _q_ventas_hoy(conn, fecha_desde: str, fecha_hasta: str) -> dict:
    """KPIs de ventas para el período dado."""
    try:
        row = conn.execute("""
            SELECT
                COALESCE(SUM(total), 0)       AS ventas_total,
                COUNT(*)                       AS tickets,
                COALESCE(AVG(total), 0)        AS ticket_promedio
            FROM ventas
            WHERE DATE(fecha) BETWEEN ? AND ?
              AND estado NOT IN ('cancelada', 'anulada')
        """, (fecha_desde, fecha_hasta)).fetchone()
        return {
            "ventas_total":    _fmt_money(row[0]) if row else 0,
            "tickets":         int(row[1]) if row else 0,
            "ticket_promedio": _fmt_money(row[2]) if row else 0,
        }
    except Exception as e:
        logger.debug("_q_ventas_hoy: %s", e)
        return {"ventas_total": 0, "tickets": 0, "ticket_promedio": 0}


def _q_ventas_ayer(conn, fecha_desde: str) -> dict:
    """Ventas del día anterior para calcular delta."""
    try:
        ayer = (date.fromisoformat(fecha_desde) - timedelta(days=1)).isoformat()
        row = conn.execute("""
            SELECT COALESCE(SUM(total), 0), COUNT(*), COALESCE(AVG(total), 0)
            FROM ventas
            WHERE DATE(fecha) = ?
              AND estado NOT IN ('cancelada', 'anulada')
        """, (ayer,)).fetchone()
        return {
            "ventas_total":    _fmt_money(row[0]) if row else 0,
            "tickets":         int(row[1]) if row else 0,
            "ticket_promedio": _fmt_money(row[2]) if row else 0,
        }
    except Exception as e:
        logger.debug("_q_ventas_ayer: %s", e)
        return {"ventas_total": 0, "tickets": 0, "ticket_promedio": 0}


def _pct_delta(actual: float, anterior: float) -> float | None:
    """Calcula % de cambio vs periodo anterior."""
    if anterior == 0:
        return None
    return round((actual - anterior) / anterior * 100, 1)


def _q_clientes(conn) -> dict:
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM clientes WHERE activo=1"
        ).fetchone()
        return {"activos": int(row[0]) if row else 0}
    except Exception as e:
        logger.debug("_q_clientes: %s", e)
        return {"activos": 0}


def _q_pedidos_wa(conn, fecha_desde: str, fecha_hasta: str) -> dict:
    try:
        row = conn.execute("""
            SELECT COUNT(*), COALESCE(SUM(total), 0)
            FROM pedidos
            WHERE DATE(fecha_pedido) BETWEEN ? AND ?
              AND canal = 'whatsapp'
              AND estado NOT IN ('cancelado')
        """, (fecha_desde, fecha_hasta)).fetchone()
        return {"count": int(row[0]) if row else 0, "monto": _fmt_money(row[1]) if row else 0}
    except Exception as e:
        logger.debug("_q_pedidos_wa: %s", e)
        return {"count": 0, "monto": 0}


def _q_stock_bajo(conn) -> int:
    try:
        row = conn.execute("""
            SELECT COUNT(*) FROM productos p
            WHERE p.activo = 1
              AND p.existencia <= COALESCE(p.minimo, 0)
              AND p.minimo > 0
        """).fetchone()
        return int(row[0]) if row else 0
    except Exception as e:
        logger.debug("_q_stock_bajo: %s", e)
        return 0


def _q_merma(conn, fecha_desde: str, fecha_hasta: str) -> float:
    try:
        row = conn.execute("""
            SELECT COALESCE(SUM(costo_estimado), 0)
            FROM merma
            WHERE DATE(fecha) BETWEEN ? AND ?
        """, (fecha_desde, fecha_hasta)).fetchone()
        return _fmt_money(row[0]) if row else 0.0
    except Exception as e:
        logger.debug("_q_merma: %s", e)
        return 0.0


def _q_margen(ventas: float, merma: float) -> float:
    if ventas == 0:
        return 0.0
    return round((ventas - merma) / ventas * 100, 1)


def _q_ultimas_ventas(conn, fecha_desde: str, fecha_hasta: str, limit: int = 20) -> list:
    try:
        rows = conn.execute("""
            SELECT
                v.id,
                v.folio,
                v.fecha,
                COALESCE(c.nombre, 'Consumidor final') AS cliente,
                COALESCE(v.cajero, v.usuario, '—')     AS cajero,
                COALESCE(v.forma_pago, '—')             AS forma_pago,
                v.total,
                COALESCE(v.estado, 'completada')        AS estado
            FROM ventas v
            LEFT JOIN clientes c ON c.id = v.cliente_id
            WHERE DATE(v.fecha) BETWEEN ? AND ?
            ORDER BY v.fecha DESC
            LIMIT ?
        """, (fecha_desde, fecha_hasta, limit)).fetchall()
        cols = ['id','folio','fecha','cliente','cajero','forma_pago','total','estado']
        return [dict(zip(cols, r)) for r in rows]
    except Exception as e:
        logger.debug("_q_ultimas_ventas: %s", e)
        return []


def _q_ventas_por_dia(conn, fecha_desde: str, fecha_hasta: str) -> list:
    try:
        rows = conn.execute("""
            SELECT DATE(fecha) AS dia, COALESCE(SUM(total), 0) AS total
            FROM ventas
            WHERE DATE(fecha) BETWEEN ? AND ?
              AND estado NOT IN ('cancelada', 'anulada')
            GROUP BY dia
            ORDER BY dia
        """, (fecha_desde, fecha_hasta)).fetchall()
        return [{"dia": r[0], "total": _fmt_money(r[1])} for r in rows]
    except Exception as e:
        logger.debug("_q_ventas_por_dia: %s", e)
        return []


def _q_pedidos_wa_por_dia(conn, fecha_desde: str, fecha_hasta: str) -> list:
    try:
        rows = conn.execute("""
            SELECT DATE(fecha_pedido) AS dia, COALESCE(SUM(total), 0) AS total
            FROM pedidos
            WHERE DATE(fecha_pedido) BETWEEN ? AND ?
              AND canal = 'whatsapp'
              AND estado NOT IN ('cancelado')
            GROUP BY dia
            ORDER BY dia
        """, (fecha_desde, fecha_hasta)).fetchall()
        return [{"dia": r[0], "total": _fmt_money(r[1])} for r in rows]
    except Exception as e:
        logger.debug("_q_pedidos_wa_por_dia: %s", e)
        return []


def _q_ventas_por_hora(conn, fecha: str) -> list:
    try:
        rows = conn.execute("""
            SELECT CAST(strftime('%H', fecha) AS INTEGER) AS hora,
                   COALESCE(SUM(total), 0) AS total
            FROM ventas
            WHERE DATE(fecha) = ?
              AND estado NOT IN ('cancelada', 'anulada')
            GROUP BY hora
            ORDER BY hora
        """, (fecha,)).fetchall()
        # Rellenar las 24 horas
        mapa = {r[0]: _fmt_money(r[1]) for r in rows}
        return [{"hora": h, "ventas": mapa.get(h, 0)} for h in range(24)]
    except Exception as e:
        logger.debug("_q_ventas_por_hora: %s", e)
        return [{"hora": h, "ventas": 0} for h in range(24)]


def _q_productos_top(conn, fecha_desde: str, fecha_hasta: str, limit: int = 10) -> list:
    try:
        rows = conn.execute("""
            SELECT
                p.nombre,
                COALESCE(SUM(dv.subtotal), 0) AS ventas,
                COALESCE(SUM(dv.cantidad), 0) AS unidades
            FROM detalle_ventas dv
            JOIN productos p ON p.id = dv.producto_id
            JOIN ventas v    ON v.id = dv.venta_id
            WHERE DATE(v.fecha) BETWEEN ? AND ?
              AND v.estado NOT IN ('cancelada', 'anulada')
            GROUP BY p.id, p.nombre
            ORDER BY ventas DESC
            LIMIT ?
        """, (fecha_desde, fecha_hasta, limit)).fetchall()
        return [
            {"nombre": r[0], "ventas": _fmt_money(r[1]), "unidades": float(r[2] or 0)}
            for r in rows
        ]
    except Exception as e:
        logger.debug("_q_productos_top: %s", e)
        return []


def _q_inventario_categorias(conn) -> list:
    try:
        rows = conn.execute("""
            SELECT
                COALESCE(categoria, 'Sin categoría') AS categoria,
                COALESCE(SUM(existencia), 0)         AS unidades,
                COUNT(*)                              AS productos
            FROM productos
            WHERE activo = 1
            GROUP BY categoria
            ORDER BY unidades DESC
        """).fetchall()
        return [
            {"categoria": r[0], "unidades": float(r[1] or 0), "productos": int(r[2] or 0)}
            for r in rows
        ]
    except Exception as e:
        logger.debug("_q_inventario_categorias: %s", e)
        return []


def _q_caja_periodo(conn, fecha_desde: str, fecha_hasta: str) -> dict:
    """Flujo de caja diario para la gráfica de tendencia."""
    try:
        rows_ing = conn.execute("""
            SELECT DATE(fecha) AS dia, COALESCE(SUM(total), 0)
            FROM ventas
            WHERE DATE(fecha) BETWEEN ? AND ?
              AND estado NOT IN ('cancelada', 'anulada')
            GROUP BY dia ORDER BY dia
        """, (fecha_desde, fecha_hasta)).fetchall()

        rows_egr = conn.execute("""
            SELECT DATE(fecha) AS dia, COALESCE(SUM(monto), 0)
            FROM gastos
            WHERE DATE(fecha) BETWEEN ? AND ?
            GROUP BY dia ORDER BY dia
        """, (fecha_desde, fecha_hasta)).fetchall()
    except Exception:
        rows_ing, rows_egr = [], []

    # Construir serie de fechas completa
    inicio = date.fromisoformat(fecha_desde)
    fin    = date.fromisoformat(fecha_hasta)
    dias   = [(inicio + timedelta(days=i)).isoformat()
              for i in range((fin - inicio).days + 1)]

    ing_map = {r[0]: _fmt_money(r[1]) for r in rows_ing}
    egr_map = {r[0]: _fmt_money(r[1]) for r in rows_egr}

    ingresos = [ing_map.get(d, 0) for d in dias]
    egresos  = [egr_map.get(d, 0) for d in dias]
    saldo    = []
    acc = 0.0
    for i, e in zip(ingresos, egresos):
        acc += i - e
        saldo.append(round(acc, 2))

    labels = [d[5:] for d in dias]  # MM-DD
    return {"labels": labels, "ingresos": ingresos, "egresos": egresos, "saldo": saldo}


def _q_alertas(conn) -> list:
    """Alertas activas del sistema."""
    try:
        rows = conn.execute("""
            SELECT titulo, mensaje, prioridad, modulo
            FROM alertas
            WHERE activa = 1
            ORDER BY
              CASE prioridad
                WHEN 'critica' THEN 1 WHEN 'alta' THEN 2
                WHEN 'media' THEN 3 ELSE 4 END
            LIMIT 5
        """).fetchall()
        return [
            {"titulo": r[0], "mensaje": r[1], "prioridad": r[2], "modulo": r[3]}
            for r in rows
        ]
    except Exception as e:
        logger.debug("_q_alertas: %s", e)
        return []


# ─── Handlers de endpoint ─────────────────────────────────────────────────────

def handle_kpis(params: dict) -> dict[str, Any]:
    """
    GET /api/dashboard/kpis?periodo=hoy|semana|mes|trimestre

    Retorna todos los KPIs de portada del dashboard.
    """
    try:
        from core.db.connection import get_connection
        conn = get_connection()
    except Exception as e:
        logger.error("handle_kpis: no se pudo obtener conexión: %s", e)
        return {"ok": False, "error": str(e)}

    periodo      = params.get("periodo", "hoy")
    desde, hasta = _parse_periodo(periodo)

    hoy   = _q_ventas_hoy(conn, desde, hasta)
    ayer  = _q_ventas_ayer(conn, desde)
    clis  = _q_clientes(conn)
    wa    = _q_pedidos_wa(conn, desde, hasta)
    merma = _q_merma(conn, desde, hasta)

    wa_ayer = _q_pedidos_wa(conn,
                            (date.fromisoformat(desde) - timedelta(days=1)).isoformat(),
                            (date.fromisoformat(hasta) - timedelta(days=1)).isoformat())

    ventas_ultimas = _q_ultimas_ventas(conn, desde, hasta, limit=20)
    alertas        = _q_alertas(conn)
    stock_bajo     = _q_stock_bajo(conn)
    margen         = _q_margen(hoy["ventas_total"], merma)

    return {
        "ok": True,
        "periodo": {"desde": desde, "hasta": hasta, "label": periodo},
        # KPIs principales
        "ventas_hoy":      hoy["ventas_total"],
        "ventas_delta":    _pct_delta(hoy["ventas_total"],    ayer["ventas_total"]),
        "tickets_hoy":     hoy["tickets"],
        "tickets_delta":   _pct_delta(hoy["tickets"],          ayer["tickets"]),
        "ticket_promedio": hoy["ticket_promedio"],
        "promedio_delta":  _pct_delta(hoy["ticket_promedio"], ayer["ticket_promedio"]),
        "clientes_activos": clis["activos"],
        "clientes_delta":  None,
        "pedidos_wa":      wa["count"],
        "pedidos_wa_delta": _pct_delta(wa["count"], wa_ayer["count"]),
        "merma_hoy":       merma,
        "merma_delta":     None,
        "margen_bruto":    margen,
        "margen_delta":    None,
        "stock_bajo":      stock_bajo,
        # Tablas
        "ultimas_ventas":  ventas_ultimas,
        "alertas":         alertas,
    }


def handle_ventas_chart(params: dict) -> dict[str, Any]:
    """
    GET /api/dashboard/ventas-chart?periodo=...

    Retorna datos para gráficas de ventas: por día, por hora, flujo de caja.
    """
    try:
        from core.db.connection import get_connection
        conn = get_connection()
    except Exception as e:
        return {"ok": False, "error": str(e)}

    periodo      = params.get("periodo", "hoy")
    desde, hasta = _parse_periodo(periodo)

    por_dia   = _q_ventas_por_dia(conn, desde, hasta)
    wa_dia    = _q_pedidos_wa_por_dia(conn, desde, hasta)
    por_hora  = _q_ventas_por_hora(conn, date.today().isoformat())
    caja      = _q_caja_periodo(conn, desde, hasta)

    # Merge de fechas (ventas y WA pueden no coincidir)
    fechas_set = sorted(set(d["dia"] for d in por_dia + wa_dia))
    ventas_map = {d["dia"]: d["total"] for d in por_dia}
    wa_map     = {d["dia"]: d["total"] for d in wa_dia}

    labels       = [d[5:] for d in fechas_set]  # MM-DD
    ventas_serie = [ventas_map.get(d, 0) for d in fechas_set]
    wa_serie     = [wa_map.get(d, 0)     for d in fechas_set]

    return {
        "ok":       True,
        "labels":   labels,
        "ventas":   ventas_serie,
        "pedidos_wa": wa_serie,
        "por_hora": por_hora,
        "caja":     caja,
    }


def handle_productos_top(params: dict) -> dict[str, Any]:
    """GET /api/dashboard/productos-top?periodo=..."""
    try:
        from core.db.connection import get_connection
        conn = get_connection()
    except Exception as e:
        return {"ok": False, "error": str(e)}

    periodo      = params.get("periodo", "hoy")
    desde, hasta = _parse_periodo(periodo)
    items        = _q_productos_top(conn, desde, hasta, limit=10)

    return {"ok": True, "items": items, "periodo": {"desde": desde, "hasta": hasta}}


def handle_inventario(_params: dict) -> dict[str, Any]:
    """GET /api/dashboard/inventario"""
    try:
        from core.db.connection import get_connection
        conn = get_connection()
    except Exception as e:
        return {"ok": False, "error": str(e)}

    categorias = _q_inventario_categorias(conn)
    return {"ok": True, "categorias": categorias}


def handle_alertas(_params: dict) -> dict[str, Any]:
    """GET /api/dashboard/alertas"""
    try:
        from core.db.connection import get_connection
        conn = get_connection()
        alertas = _q_alertas(conn)
        return {"ok": True, "alertas": alertas}
    except Exception as e:
        return {"ok": False, "error": str(e), "alertas": []}


# ─── Tabla de despacho (usada por el handler HTTP) ────────────────────────────

DASHBOARD_ROUTES: dict[str, Any] = {
    "/api/dashboard/kpis":         handle_kpis,
    "/api/dashboard/ventas-chart": handle_ventas_chart,
    "/api/dashboard/productos-top": handle_productos_top,
    "/api/dashboard/inventario":   handle_inventario,
    "/api/dashboard/alertas":      handle_alertas,
}
