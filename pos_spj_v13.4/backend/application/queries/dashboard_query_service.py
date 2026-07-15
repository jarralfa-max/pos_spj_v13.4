# backend/application/queries/dashboard_query_service.py
"""
DashboardQueryService — lecturas del dashboard operativo (KPIs diarios).

Ruta canónica de lectura para `ui/dashboard.py`: la UI PyQt no ejecuta SQL;
consume este QueryService (Bug 2: los KPIs diarios del Dashboard solo pueden
venir de QueryServices).

Reglas:
- `branch_id` es UUID string o None (None = todas las sucursales, vista
  gerente). PROHIBIDO el default entero `sucursal_id=1`.
- Queries parametrizados — nunca interpolar identificadores de dominio.
- Tabla opcional ausente → valor vacío/cero, jamás romper el dashboard.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("spj.queries.dashboard")

_ESTADOS_WA_ACTIVOS = ("entregado", "cancelado")


class DashboardQueryService:
    def __init__(self, db_conn: Any) -> None:
        self.db = db_conn

    # ── infra ────────────────────────────────────────────────────────────────
    def _table_exists(self, name: str) -> bool:
        try:
            row = self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
            ).fetchone()
            return bool(row)
        except Exception:
            return False

    def _scalar(self, sql: str, params: tuple = ()) -> Any:
        row = self.db.execute(sql, params).fetchone()
        return row[0] if row else None

    @staticmethod
    def _branch_clause(branch_id: str | None) -> tuple[str, tuple]:
        """Filtro de sucursal parametrizado. None → sin filtro (vista global)."""
        branch_id = str(branch_id or "").strip()
        if not branch_id:
            return "", ()
        return " AND sucursal_id = ?", (branch_id,)

    # ── gráfica semanal ──────────────────────────────────────────────────────
    def weekly_sales_by_day(self) -> list[dict]:
        """Ventas completadas por día de los últimos 7 días: [{fecha, total}]."""
        if not self._table_exists("ventas"):
            return []
        rows = self.db.execute(
            """
            SELECT DATE('now', printf('-%d days', 6-seq)) AS dia,
                   COALESCE(SUM(v.total), 0) AS total
            FROM (SELECT 0 AS seq UNION SELECT 1 UNION SELECT 2
                  UNION SELECT 3 UNION SELECT 4 UNION SELECT 5 UNION SELECT 6) d
            LEFT JOIN ventas v
                ON DATE(v.fecha) = DATE('now', printf('-%d days', 6-d.seq))
               AND v.estado = 'completada'
            GROUP BY dia
            ORDER BY dia
            """
        ).fetchall()
        return [{"fecha": str(r[0]), "total": float(r[1] or 0)} for r in rows]

    # ── KPIs diarios ─────────────────────────────────────────────────────────
    def daily_kpis(self, branch_id: str | None = None) -> dict:
        """KPIs del día. branch_id UUID string filtra; None = global."""
        kpis: dict = {
            "ventas_hoy": 0.0,
            "tickets_hoy": 0,
            "ticket_promedio": 0.0,
            "margen_pct": 0.0,
            "ventas_ayer": 0.0,
            "clientes_hoy": 0,
            "pedidos_wa_activos": 0,
            "productos_stock_bajo": 0,
        }
        clause, params = self._branch_clause(branch_id)
        if self._table_exists("ventas"):
            row = self.db.execute(
                "SELECT COALESCE(SUM(total),0), COUNT(*) FROM ventas"
                " WHERE DATE(fecha)=DATE('now') AND estado='completada'" + clause,
                params,
            ).fetchone()
            kpis["ventas_hoy"] = float(row[0] or 0)
            kpis["tickets_hoy"] = int(row[1] or 0)
            if kpis["tickets_hoy"]:
                kpis["ticket_promedio"] = kpis["ventas_hoy"] / kpis["tickets_hoy"]
            kpis["ventas_ayer"] = float(
                self._scalar(
                    "SELECT COALESCE(SUM(total),0) FROM ventas"
                    " WHERE DATE(fecha)=DATE('now','-1 day')"
                    " AND estado='completada'" + clause,
                    params,
                )
                or 0
            )
            kpis["clientes_hoy"] = int(
                self._scalar(
                    "SELECT COUNT(DISTINCT cliente_id) FROM ventas"
                    " WHERE DATE(fecha)=DATE('now') AND estado='completada'"
                    " AND cliente_id IS NOT NULL" + clause,
                    params,
                )
                or 0
            )
        if (
            self._table_exists("ventas")
            and self._table_exists("detalles_venta")
            and self._table_exists("productos")
        ):
            row = self.db.execute(
                """
                SELECT COALESCE(SUM(vd.cantidad * vd.precio_unitario),0),
                       COALESCE(SUM(vd.cantidad * COALESCE(p.precio_compra,0)),0)
                FROM ventas v
                JOIN detalles_venta vd ON vd.venta_id = v.id
                JOIN productos p ON p.id = vd.producto_id
                WHERE DATE(v.fecha)=DATE('now') AND v.estado='completada'
                """
            ).fetchone()
            ingresos = float(row[0] or 0)
            costos = float(row[1] or 0)
            if ingresos > 0:
                kpis["margen_pct"] = (ingresos - costos) / ingresos * 100
        if self._table_exists("pedidos_whatsapp"):
            kpis["pedidos_wa_activos"] = int(
                self._scalar(
                    "SELECT COUNT(*) FROM pedidos_whatsapp"
                    " WHERE estado NOT IN (?, ?)",
                    _ESTADOS_WA_ACTIVOS,
                )
                or 0
            )
        if self._table_exists("productos"):
            kpis["productos_stock_bajo"] = int(
                self._scalar(
                    "SELECT COUNT(*) FROM productos"
                    " WHERE existencia <= COALESCE(stock_minimo,5) AND activo=1"
                )
                or 0
            )
        return kpis

    # ── actividad reciente ───────────────────────────────────────────────────
    def recent_activity(self, *, limit: int = 8) -> list[dict]:
        """Ventas y pedidos WA de hoy, más recientes primero."""
        eventos: list[dict] = []
        if self._table_exists("ventas"):
            rows = self.db.execute(
                "SELECT total, fecha FROM ventas"
                " WHERE DATE(fecha)=DATE('now') AND estado='completada'"
                " ORDER BY fecha DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            eventos += [
                {"tipo": "venta", "total": float(r[0] or 0),
                 "fecha": str(r[1] or ""), "estado": "completada"}
                for r in rows
            ]
        if self._table_exists("pedidos_whatsapp"):
            rows = self.db.execute(
                "SELECT total, fecha, estado FROM pedidos_whatsapp"
                " WHERE DATE(fecha)=DATE('now')"
                " ORDER BY fecha DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
            eventos += [
                {"tipo": "pedido", "total": float(r[0] or 0),
                 "fecha": str(r[1] or ""), "estado": str(r[2] or "")}
                for r in rows
            ]
        eventos.sort(key=lambda e: e["fecha"], reverse=True)
        return eventos[: int(limit)]

    # ── pedidos WhatsApp activos ─────────────────────────────────────────────
    def active_whatsapp_orders(self, *, limit: int = 8) -> list[dict]:
        if not self._table_exists("pedidos_whatsapp"):
            return []
        rows = self.db.execute(
            """
            SELECT id, cliente_nombre, numero_whatsapp, estado,
                   total, tipo_entrega, fecha
            FROM pedidos_whatsapp
            WHERE estado NOT IN (?, ?)
            ORDER BY CASE estado
                WHEN 'nuevo' THEN 0 WHEN 'confirmado' THEN 1
                WHEN 'pesando' THEN 2 ELSE 3 END, fecha DESC
            LIMIT ?
            """,
            _ESTADOS_WA_ACTIVOS + (int(limit),),
        ).fetchall()
        cols = ("id", "cliente_nombre", "numero_whatsapp", "estado",
                "total", "tipo_entrega", "fecha")
        return [dict(zip(cols, tuple(r))) for r in rows]

    # ── alertas operativas ───────────────────────────────────────────────────
    def operational_alerts(self, *, limit_each: int = 5,
                           log_limit: int = 10) -> list[dict]:
        """Stock bajo + caducidades próximas + alertas_log no leídas."""
        alertas: list[dict] = []
        if self._table_exists("productos"):
            rows = self.db.execute(
                "SELECT nombre FROM productos"
                " WHERE existencia <= COALESCE(stock_minimo,5) AND activo=1"
                " LIMIT ?",
                (int(limit_each),),
            ).fetchall()
            alertas += [
                {"texto": f"Stock bajo: {r[0]}", "tipo": "danger"} for r in rows
            ]
        if self._table_exists("lotes") and self._table_exists("productos"):
            try:
                rows = self.db.execute(
                    """
                    SELECT p.nombre FROM lotes l
                    JOIN productos p ON p.id = l.producto_id
                    WHERE l.caducidad <= DATE('now','+3 days')
                      AND l.estado='activo' AND l.cantidad_disponible > 0
                    LIMIT ?
                    """,
                    (int(limit_each),),
                ).fetchall()
                alertas += [
                    {"texto": f"Caducidad próxima: {r[0]}", "tipo": "warning"}
                    for r in rows
                ]
            except Exception as exc:
                logger.debug("operational_alerts lotes: %s", exc)
        if self._table_exists("alertas_log"):
            try:
                rows = self.db.execute(
                    "SELECT titulo, tipo FROM alertas_log"
                    " WHERE leida=0 AND tipo != 'ok'"
                    " ORDER BY fecha DESC LIMIT ?",
                    (int(log_limit),),
                ).fetchall()
                alertas += [
                    {
                        "texto": str(r[0] or ""),
                        "tipo": "warning"
                        if r[1] in ("stock_bajo", "caducidad_proxima")
                        else "info",
                    }
                    for r in rows
                ]
            except Exception as exc:
                logger.debug("operational_alerts log: %s", exc)
        return alertas

    # ── repartidores ─────────────────────────────────────────────────────────
    def drivers_status(self) -> list[dict]:
        if not self._table_exists("drivers"):
            return []
        try:
            rows = self.db.execute(
                """
                SELECT d.nombre, d.en_ruta, COUNT(p.id) AS pedidos_activos
                FROM drivers d
                LEFT JOIN pedidos_whatsapp p
                    ON p.repartidor_id = d.id AND p.estado='listo'
                WHERE d.activo=1
                GROUP BY d.id
                ORDER BY d.nombre
                """
            ).fetchall()
        except Exception as exc:
            logger.debug("drivers_status: %s", exc)
            return []
        return [
            {"nombre": str(r[0] or ""), "en_ruta": bool(r[1]),
             "pedidos_activos": int(r[2] or 0)}
            for r in rows
        ]
