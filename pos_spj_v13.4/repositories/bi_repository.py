# repositories/bi_repository.py
"""BIRepository — consultas de Business Intelligence sobre ventas y telemetría."""
from __future__ import annotations
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)


class BIRepository:

    def __init__(self, db):
        self.db = db

    def get_ranking_cajeros(
        self,
        sucursal_id: int,
        fecha_inicio: str,
        fecha_fin: str,
        limite: int = 20,
    ) -> list:
        """Ranking de cajeros por número de ventas en el rango dado."""
        try:
            rows = self.db.execute("""
                SELECT
                    COALESCE(usuario, '(sin usuario)') AS cajero,
                    COUNT(id)   AS num_ventas,
                    SUM(total)  AS total_ventas,
                    SUM(descuento) AS total_descuentos
                FROM ventas
                WHERE sucursal_id = ?
                  AND estado NOT IN ('cancelada','anulada')
                  AND fecha BETWEEN ? AND ?
                GROUP BY COALESCE(usuario, '(sin usuario)')
                ORDER BY num_ventas DESC
                LIMIT ?
            """, (sucursal_id, fecha_inicio, fecha_fin, limite)).fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.warning("get_ranking_cajeros: %s", exc)
            return []

    def get_kpis_dia(self) -> dict:
        """KPIs del día actual para la barra BI (todas las sucursales):
        ventas, tickets, clientes únicos e ingresos/costo para el margen bruto.
        Devuelve valores crudos; la UI compone ticket promedio y margen.
        """
        out = {"ventas": 0.0, "tickets": 0, "clientes": 0,
               "ingresos": 0.0, "costo": 0.0}
        try:
            r = self.db.execute("""
                SELECT
                    COALESCE(SUM(total),0),
                    COUNT(*),
                    COUNT(DISTINCT cliente_id)
                FROM ventas
                WHERE DATE(fecha)=DATE('now')
                AND estado='completada'
            """).fetchone()
            out["ventas"] = float(r[0] or 0)
            out["tickets"] = int(r[1] or 0)
            out["clientes"] = int(r[2] or 0)

            r2 = self.db.execute("""
                SELECT
                    COALESCE(SUM(vd.cantidad*vd.precio_unitario),0),
                    COALESCE(SUM(vd.cantidad*COALESCE(p.precio_compra,0)),0)
                FROM ventas v
                JOIN detalles_venta vd ON vd.venta_id = v.id
                JOIN productos p ON p.id = vd.producto_id
                WHERE DATE(v.fecha)=DATE('now')
                AND v.estado='completada'
            """).fetchone()
            out["ingresos"] = float(r2[0] or 0)
            out["costo"] = float(r2[1] or 0)
        except Exception as exc:
            logger.warning("get_kpis_dia: %s", exc)
        return out

    def get_scan_telemetria(
        self,
        sucursal_id: int,
        fecha_inicio: str,
        fecha_fin: str,
    ) -> list:
        """Telemetría de eventos de escaneo agrupada por tipo y acción."""
        try:
            rows = self.db.execute("""
                SELECT tipo, accion, COUNT(*) AS total
                FROM scan_event_log
                WHERE sucursal_id = ?
                  AND created_at BETWEEN ? AND ?
                GROUP BY tipo, accion
                ORDER BY total DESC
            """, (sucursal_id, fecha_inicio, fecha_fin)).fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.warning("get_scan_telemetria: %s", exc)
            return []
