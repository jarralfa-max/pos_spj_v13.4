
# core/forecast/replenishment_engine.py
# ── ReplenishmentEngine — Motor de Reabastecimiento Inteligente ───────────────
#
# RESPONSABILIDADES:
#   ✔ Orquestar forecast para todos los productos activos de una sucursal
#   ✔ Calcular recomendaciones de compra (COMPRA) o producción (PRODUCCION)
#   ✔ Para subproductos: calcular materia prima necesaria via receta
#   ✔ Generar alertas cuando stock < reorder_point
#   ✔ Publicar FORECAST_GENERATED vía EventBus
#   ✔ Registrar ejecución en forecast_run_log
#
# FLUJO POR EJECUCIÓN:
#   1. Cargar productos activos de la sucursal
#   2. Para cada producto:
#       a. Obtener stock actual (inventario_actual)
#       b. Ejecutar DemandForecastEngine.forecast_product()
#       c. Calcular recommended_quantity
#       d. Determinar tipo: COMPRA | PRODUCCION | TRANSFERENCIA
#       e. Si subproducto: calcular fuente (materia prima)
#       f. Guardar demand_forecast + replenishment_recommendations
#   3. Persistir forecast_run_log
#   4. Publicar FORECAST_GENERATED

from __future__ import annotations

import logging
import time
import uuid
from datetime import date, datetime
from typing import Dict, List, Optional

from core.forecast.demand_forecast_engine import DemandForecastEngine
from core.forecast.safety_stock_calculator import SafetyStockCalculator

logger = logging.getLogger("spj.forecast.replenishment")


class ReplenishmentEngine:
    """
    Orquestador del motor de compras inteligentes.

    Uso:
        engine = ReplenishmentEngine(db)
        result = engine.run(branch_id=1)
        # result = {"run_id":..., "ok":N, "skip":N, "recomendaciones":N, "alertas":N}
    """

    def __init__(self, db):
        from core.db.connection import wrap
        self.db = wrap(db)
        self._forecast_eng = DemandForecastEngine(db)

    # ── Helpers ─────────────────────────────────────────────────────────────────

    def _get_config(self, key: str, default: str) -> str:
        try:
            row = self.db.fetchone(
                "SELECT valor FROM configuraciones WHERE clave=?", (key,)
            )
            return row["valor"] if row else default
        except Exception:
            return default

    def _get_stock(self, product_id: int, branch_id: int) -> float:
        try:
            row = self.db.fetchone("""
                SELECT COALESCE(cantidad, 0) FROM inventario_actual
                WHERE producto_id=? AND sucursal_id=?
            """, (product_id, branch_id))
            return float(row[0]) if row else 0.0
        except Exception:
            return 0.0

    def _get_active_products(self, branch_id: int) -> List[Dict]:
        """Productos activos con relevancia para forecast."""
        try:
            rows = self.db.fetchall("""
                SELECT p.id, p.nombre, p.unidad,
                       p.es_subproducto, p.producto_padre_id,
                       COALESCE(p.lead_time_dias, 2) AS lead_time,
                       COALESCE(p.stock_minimo, 0)   AS stock_minimo,
                       p.proveedor_id
                FROM productos p
                WHERE p.activo = 1
                  AND p._deleted = 0
                ORDER BY p.nombre
            """)
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.warning("get_active_products: %s", exc)
            return []

    def _get_receta_fuente(self, product_id: int) -> Optional[Dict]:
        """
        Para un subproducto, obtiene el producto fuente y rendimiento
        desde receta_componentes + recetas.
        Retorna {fuente_id, rendimiento_pct, receta_id} o None.
        """
        try:
            row = self.db.fetchone("""
                SELECT r.producto_base_id AS fuente_id,
                       rc.rendimiento_porcentaje AS rendimiento_pct,
                       r.id AS receta_id
                FROM receta_componentes rc
                JOIN recetas r ON r.id = rc.receta_id
                WHERE rc.producto_id = ? AND r.activo = 1
                ORDER BY r.id DESC LIMIT 1
            """, (product_id,))
            return dict(row) if row else None
        except Exception:
            return None

    def _calc_fuente_kg(self, demand_kg: float, rendimiento_pct: float) -> float:
        """
        Calcula cuánta materia prima necesito para producir demand_kg
        de un subproducto con ese rendimiento.
        fuente_kg = demand_kg / (rendimiento_pct / 100)
        """
        if rendimiento_pct <= 0:
            return 0.0
        return round(demand_kg / (rendimiento_pct / 100), 4)

    def _publicar_evento(self, run_id: str, branch_id: int, n_rec: int) -> None:
        try:
            from core.events.event_bus import get_bus
            get_bus().publish("FORECAST_GENERATED", {
                "run_id": run_id,
                "branch_id": branch_id,
                "recomendaciones": n_rec,
            })
        except Exception as exc:
            logger.warning("EventBus FORECAST falló: %s", exc)

    # ── Ejecución principal ─────────────────────────────────────────────────────

    def run(
        self,
        branch_id: Optional[int] = None,
        horizon_days: int = 7,
        force: bool = False,
    ) -> Dict:
        """
        Ejecuta el motor de forecast y genera recomendaciones.

        branch_id: None = todas las sucursales
        horizon_days: días hacia adelante
        force: ignorar cache de last_run

        Retorna:
            {run_id, ok, skip, recomendaciones, alertas, duracion_ms}
        """
        t0 = time.monotonic()
        run_id = str(uuid.uuid4())
        horizon = int(self._get_config("forecast_horizon_days", str(horizon_days)))

        branches = []
        if branch_id:
            branches = [branch_id]
        else:
            try:
                rows = self.db.fetchall(
                    "SELECT id FROM sucursales WHERE activa=1"
                )
                branches = [r["id"] for r in rows]
            except Exception:
                branches = [1]

        total_ok, total_skip, total_rec, total_alerts = 0, 0, 0, 0

        for bid in branches:
            ok, skip, rec, alerts = self._run_branch(bid, horizon, run_id)
            total_ok    += ok
            total_skip  += skip
            total_rec   += rec
            total_alerts += alerts

        dur_ms = int((time.monotonic() - t0) * 1000)

        # Registrar ejecución
        try:
            self.db.execute("""
                INSERT INTO forecast_run_log
                    (id, branch_id, productos_ok, productos_skip,
                     recomendaciones, alertas, duracion_ms)
                VALUES (?,?,?,?,?,?,?)
            """, (run_id, branch_id, total_ok, total_skip,
                  total_rec, total_alerts, dur_ms))
        except Exception as exc:
            logger.warning("save_run_log: %s", exc)

        self._publicar_evento(run_id, branch_id or 0, total_rec)

        logger.info(
            "FORECAST run=%s branch=%s ok=%d skip=%d rec=%d alerts=%d %dms",
            run_id[:8], branch_id, total_ok, total_skip, total_rec, total_alerts, dur_ms
        )

        return {
            "run_id":         run_id,
            "ok":             total_ok,
            "skip":           total_skip,
            "recomendaciones": total_rec,
            "alertas":        total_alerts,
            "duracion_ms":    dur_ms,
        }

    def _run_branch(
        self, branch_id: int, horizon: int, run_id: str
    ) -> tuple[int, int, int, int]:
        ok, skip, rec, alerts = 0, 0, 0, 0
        products = self._get_active_products(branch_id)

        for prod in products:
            pid = prod["id"]
            try:
                result = self._process_product(
                    prod, branch_id, horizon, run_id
                )
                if result is None:
                    skip += 1
                else:
                    ok += 1
                    if result.get("saved_forecast", 0) > 0:
                        rec += 1
                    if result.get("alerta"):
                        alerts += 1
            except Exception as exc:
                logger.error("Error prod=%d suc=%d: %s", pid, branch_id, exc)
                skip += 1

        return ok, skip, rec, alerts

    def _process_product(
        self, prod: Dict, branch_id: int, horizon: int, run_id: str
    ) -> Optional[Dict]:
        pid = prod["id"]
        current_stock = self._get_stock(pid, branch_id)

        # Intentar forecast
        fc = self._forecast_eng.forecast_product(pid, branch_id, horizon, run_id)
        if fc is None:
            # Sin suficiente historial — aún así verificar si stock es crítico
            min_stock = float(prod.get("stock_minimo") or 0)
            if current_stock <= min_stock and min_stock > 0:
                # Usar promedio histórico simple si hay algo
                avg = self._simple_avg(pid, branch_id)
                if avg > 0:
                    fc = {
                        "product_id": pid, "branch_id": branch_id,
                        "method": "simple_avg",
                        "avg_daily_demand": avg,
                        "forecast_total": avg * horizon,
                        "forecast_by_day": [],
                        "safety_stock": 0.0,
                        "reorder_point": min_stock,
                        "confidence": 0.3,
                        "lead_time_days": int(prod.get("lead_time") or 2),
                        "horizon_days": horizon,
                        "run_id": run_id,
                    }
                else:
                    return None
            else:
                return None

        avg_daily = fc["avg_daily_demand"]
        ss        = fc["safety_stock"]
        rop       = fc["reorder_point"]
        lt        = fc["lead_time_days"]
        forecast  = fc["forecast_total"]

        # Cantidad recomendada
        qty = SafetyStockCalculator.recommended_quantity(forecast, ss, current_stock)

        # Días de cobertura
        days_cov = SafetyStockCalculator.days_coverage(current_stock, avg_daily)
        urgency  = SafetyStockCalculator.urgency_level(days_cov)

        # Tipo de recomendación
        tipo = "COMPRA"
        fuente_prod_id = None
        fuente_qty = 0.0

        if prod.get("es_subproducto"):
            receta_info = self._get_receta_fuente(pid)
            if receta_info and receta_info.get("rendimiento_pct", 0) > 0:
                tipo = "PRODUCCION"
                fuente_prod_id = receta_info["fuente_id"]
                fuente_qty = self._calc_fuente_kg(qty, receta_info["rendimiento_pct"])

        # Guardar forecast si hay días
        n_saved = self._forecast_eng.save_forecast(fc) if fc.get("forecast_by_day") else 0

        # Guardar recomendación
        alerta = (current_stock <= rop) or (urgency in ("critico", "bajo"))
        self._save_recommendation(
            run_id=run_id, product_id=pid, branch_id=branch_id,
            qty=qty, ss=ss, rop=rop, lt=lt,
            current_stock=current_stock, days_cov=days_cov,
            avg_daily=avg_daily, forecast=forecast,
            urgency=urgency, tipo=tipo,
            fuente_prod_id=fuente_prod_id, fuente_qty=fuente_qty,
        )

        return {
            "product_id":    pid,
            "saved_forecast": n_saved,
            "qty":           qty,
            "urgency":       urgency,
            "alerta":        alerta,
        }

    def _simple_avg(self, product_id: int, branch_id: int, days: int = 30) -> float:
        """Media simple cuando hay pocos datos."""
        from datetime import timedelta
        since = (date.today() - timedelta(days=days)).isoformat()
        try:
            row = self.db.fetchone("""
                SELECT COALESCE(SUM(CAST(dv.cantidad AS REAL)), 0) / ? AS avg_d
                FROM detalles_venta dv
                JOIN ventas v ON v.id = dv.venta_id
                WHERE dv.producto_id=?
                  AND (v.sucursal_id=? OR ?=0)
                  AND v.estado NOT IN ('cancelada','anulada')
                  AND v.fecha >= ?
            """, (days, product_id, branch_id, branch_id, since))
            return float(row["avg_d"] or 0) if row else 0.0
        except Exception:
            return 0.0

    def _save_recommendation(
        self, run_id, product_id, branch_id,
        qty, ss, rop, lt, current_stock, days_cov,
        avg_daily, forecast, urgency, tipo,
        fuente_prod_id, fuente_qty,
    ) -> None:
        rec_id = str(uuid.uuid4())
        try:
            self.db.execute("""
                INSERT INTO replenishment_recommendations (
                    id, product_id, branch_id,
                    recommended_quantity, safety_stock, reorder_point,
                    lead_time_days, current_stock, days_coverage,
                    avg_daily_demand, forecast_demand,
                    urgency, tipo, fuente_producto_id, fuente_cantidad,
                    estado, run_id
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pendiente',?)
            """, (rec_id, product_id, branch_id,
                  qty, ss, rop, lt, current_stock, days_cov,
                  avg_daily, forecast, urgency, tipo,
                  fuente_prod_id, fuente_qty, run_id))
        except Exception as exc:
            logger.warning("save_recommendation prod=%d: %s", product_id, exc)

    # ── Consultas ──────────────────────────────────────────────────────────────

    def get_dashboard(
        self, branch_id: Optional[int] = None,
        urgency: Optional[str] = None,
        buscar: str = "",
        limit: int = 200,
    ) -> List[Dict]:
        """
        Datos para el dashboard de planeación de compras.
        Retorna la última recomendación por producto.
        """
        filters, params = [], []

        if branch_id:
            filters.append("rr.branch_id=?"); params.append(branch_id)
        if urgency:
            filters.append("rr.urgency=?"); params.append(urgency)
        if buscar:
            filters.append("LOWER(p.nombre) LIKE ?")
            params.append(f"%{buscar.lower()}%")

        where = "WHERE " + " AND ".join(filters) if filters else ""
        params.append(limit)

        try:
            rows = self.db.fetchall(f"""
                SELECT rr.id, rr.product_id, p.nombre AS producto_nombre,
                       p.unidad, p.codigo,
                       c.nombre AS categoria,
                       rr.branch_id, s.nombre AS sucursal_nombre,
                       rr.recommended_quantity, rr.safety_stock,
                       rr.reorder_point, rr.lead_time_days,
                       rr.current_stock, rr.days_coverage,
                       rr.avg_daily_demand, rr.forecast_demand,
                       rr.urgency, rr.tipo,
                       rr.fuente_producto_id,
                       pf.nombre AS fuente_nombre,
                       rr.fuente_cantidad, rr.estado,
                       rr.created_at,
                       (SELECT df.predicted_demand
                        FROM demand_forecast df
                        WHERE df.product_id=rr.product_id
                          AND df.branch_id=rr.branch_id
                          AND df.forecast_date = date('now','+1 day')
                        ORDER BY df.created_at DESC LIMIT 1
                       ) AS manana_demand,
                       (SELECT df.predicted_demand
                        FROM demand_forecast df
                        WHERE df.product_id=rr.product_id
                          AND df.branch_id=rr.branch_id
                          AND df.forecast_date = date('now','+7 days')
                        ORDER BY df.created_at DESC LIMIT 1
                       ) AS semana_demand
                FROM replenishment_recommendations rr
                JOIN productos p ON p.id = rr.product_id
                LEFT JOIN categorias c ON c.id = p.categoria_id
                LEFT JOIN sucursales s ON s.id = rr.branch_id
                LEFT JOIN productos pf ON pf.id = rr.fuente_producto_id
                {where}
                GROUP BY rr.product_id, rr.branch_id
                HAVING rr.created_at = MAX(rr.created_at)
                ORDER BY
                    CASE rr.urgency
                        WHEN 'critico' THEN 1 WHEN 'bajo' THEN 2
                        WHEN 'normal' THEN 3 ELSE 4 END,
                    rr.days_coverage ASC
                LIMIT ?
            """, params)
            return [dict(r) for r in rows]
        except Exception as exc:
            logger.error("get_dashboard: %s", exc)
            return []

    def get_forecast_series(
        self, product_id: int, branch_id: int, days: int = 14
    ) -> List[Dict]:
        """Serie de forecast para un producto."""
        try:
            rows = self.db.fetchall("""
                SELECT forecast_date, predicted_demand, confidence,
                       lower_bound, upper_bound, method, seasonality_factor
                FROM demand_forecast
                WHERE product_id=? AND branch_id=?
                  AND forecast_date >= date('now')
                ORDER BY forecast_date
                LIMIT ?
            """, (product_id, branch_id, days))
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_historial_runs(self, limit: int = 20) -> List[Dict]:
        try:
            rows = self.db.fetchall("""
        SELECT frl.*,
                       s.nombre AS sucursal_nombre
                FROM forecast_run_log frl
                LEFT JOIN sucursales s ON s.id = frl.branch_id
                ORDER BY created_at DESC LIMIT ?
            """, (limit,))
            return [dict(r) for r in rows]
        except Exception:
            return []

    def get_precision_metrics(self, branch_id: Optional[int] = None) -> List[Dict]:
        params = []
        where = ""
        if branch_id:
            where = "WHERE fm.branch_id=?"
            params.append(branch_id)
        try:
            rows = self.db.fetchall(f"""
                SELECT fm.*, p.nombre AS producto_nombre, s.nombre AS sucursal_nombre
                FROM forecast_metrics fm
                LEFT JOIN productos p ON p.id = fm.product_id
                LEFT JOIN sucursales s ON s.id = fm.branch_id
                {where}
                ORDER BY fm.mae ASC
            """, params)
            return [dict(r) for r in rows]
        except Exception:
            return []

    def approve_recommendation(self, rec_id: str) -> None:
        self.db.execute(
            "UPDATE replenishment_recommendations SET estado='aprobada' WHERE id=?",
            (rec_id,)
        )

    def reject_recommendation(self, rec_id: str) -> None:
        self.db.execute(
            "UPDATE replenishment_recommendations SET estado='rechazada' WHERE id=?",
            (rec_id,)
        )
