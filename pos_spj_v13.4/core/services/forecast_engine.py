
# core/services/forecast_engine.py — SPJ POS v12
"""Motor de pronostico SES para demanda diaria por producto."""
from __future__ import annotations
import logging
from datetime import date, timedelta

logger = logging.getLogger("spj.forecast_engine")


class ForecastEngine:
    """SES (alpha=0.3) sobre ventas de los ultimos 60 dias."""

    def __init__(self, conn, sucursal_id: int = 1,
                 alpha: float = 0.3, horizonte: int = 7):
        self.conn = conn
        self.sucursal_id = sucursal_id
        self.alpha = alpha
        self.horizonte = horizonte

    def run(self) -> list:
        """Pronostica todos los productos activos. Retorna lista de dicts."""
        productos = self._get_productos_activos()
        resultados = []
        for prod in productos:
            try:
                fc = self._ses(prod["id"])
                stock = self._stock(prod["id"])
                stock_min = float(prod.get("stock_minimo") or 5)
                dias = (stock / fc) if fc > 0 else 999
                resultados.append({
                    "producto_id": prod["id"],
                    "nombre": prod["nombre"],
                    "stock_actual": round(stock, 3),
                    "stock_minimo": round(stock_min, 3),
                    "demanda_diaria": round(fc, 3),
                    "demanda_horizonte": round(fc * self.horizonte, 3),
                    "dias_stock": round(dias, 1),
                    "requiere_pedido": dias < self.horizonte or stock <= stock_min,
                })
            except Exception as e:
                logger.debug("forecast prod %d: %s", prod["id"], e)
        resultados.sort(key=lambda r: r["dias_stock"])
        return resultados

    def forecast_producto(self, producto_id: int) -> dict:
        """Pronostico individual para un producto."""
        fc = self._ses(producto_id)
        return {
            "producto_id": producto_id,
            "demanda_diaria": round(fc, 3),
            "demanda_semana": round(fc * 7, 3),
            "demanda_mes": round(fc * 30, 3),
        }

    def generar_forecast_diario(self) -> list:
        """Alias de run() requerido por SchedulerService."""
        return self.run()

    def _get_productos_activos(self) -> list:
        try:
            rows = self.conn.execute(
                "SELECT id, nombre, stock_minimo FROM productos "
                "WHERE activo=1 AND COALESCE(oculto,0)=0 ORDER BY nombre"
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def _stock(self, producto_id: int) -> float:
        try:
            r = self.conn.execute(
                "SELECT existencia FROM inventario "
                "WHERE producto_id=? AND sucursal_id=?",
                (producto_id, self.sucursal_id)).fetchone()
            if r: return float(r[0])
            r2 = self.conn.execute(
                "SELECT existencia FROM productos WHERE id=?",
                (producto_id,)).fetchone()
            return float(r2[0]) if r2 else 0.0
        except Exception:
            return 0.0

    def _ses(self, producto_id: int) -> float:
        """Suavizamiento Exponencial Simple sobre ventas diarias."""
        fecha_ini = (date.today() - timedelta(days=60)).isoformat()
        try:
            rows = self.conn.execute("""
                SELECT DATE(v.fecha) as dia, SUM(dv.cantidad) as total
                FROM detalles_venta dv
                JOIN ventas v ON v.id = dv.venta_id
                WHERE dv.producto_id=? AND v.sucursal_id=?
                  AND v.estado='completada' AND DATE(v.fecha)>=?
                GROUP BY dia ORDER BY dia
            """, (producto_id, self.sucursal_id, fecha_ini)).fetchall()
        except Exception:
            return 0.0
        if not rows: return 0.0
        vals = [float(r[1]) for r in rows]
        ses = vals[0]
        for c in vals[1:]:
            ses = self.alpha * c + (1 - self.alpha) * ses
        return max(0.0, ses)
