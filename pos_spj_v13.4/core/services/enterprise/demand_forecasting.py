
# core/services/enterprise/demand_forecasting.py
# ── DemandForecasting — Motor de Predicción de Demanda ───────────────────────
#
# Implementa promedio móvil ponderado para:
#   • Predecir demanda semanal por producto
#   • Sugerir cantidad de compra con buffer de seguridad
#   • Clasificar días de la semana por demanda
#   • Calcular tendencia (creciente / estable / decreciente)
#
# Algoritmos:
#   WMA_7  — promedio móvil ponderado 7 días (más reciente pesa más)
#   SMA_14 — promedio simple 14 días
#   SMA_30 — promedio simple 30 días
#
# Versión: 1.0 — Fase 7
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("spj.demand_forecasting")


@dataclass
class DemandPoint:
    fecha: str
    dia_semana: int          # 0=lunes … 6=domingo
    dia_nombre: str
    cantidad: float
    revenue: float
    tickets: int


@dataclass
class ProductForecast:
    producto_id: int
    producto_nombre: str
    unidad: str
    # Histórico
    historico: List[DemandPoint]
    # Promedios
    wma_7: float
    sma_14: float
    sma_30: float
    # Tendencia
    tendencia: str           # 'CRECIENTE' | 'ESTABLE' | 'DECRECIENTE'
    tendencia_pct: float     # cambio % últimas 2 semanas
    # Por día de semana
    demanda_por_dia: Dict[str, float]  # {'Lunes': 120.0, ...}
    pico_semana: str         # día de mayor demanda
    # Sugerencia de compra
    compra_sugerida_7d: float
    compra_sugerida_semana: float
    stock_actual: float
    dias_cobertura: float
    alerta: str              # '' | 'CRITICO' | 'BAJO' | 'EXCEDENTE'


@dataclass
class AlertaInventario:
    producto_id: int
    nombre: str
    stock_actual: float
    stock_minimo: float
    unidad: str
    nivel: str               # 'CRITICO' | 'BAJO' | 'EXCEDENTE' | 'OK'
    dias_cobertura: float
    compra_sugerida: float


DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


class DemandForecastingEngine:

    def __init__(self, db):
        self.db = db
        self._bus = None
        try:
            from core.events.event_bus import get_bus
            self._bus = get_bus()
        except Exception:
            pass

    # ═════════════════════════════════════════════════════════════════════════
    # HISTORIAL DE VENTAS
    # ═════════════════════════════════════════════════════════════════════════

    def _get_daily_sales(
        self,
        producto_id: int,
        branch_id: Optional[int],
        days: int = 90,
    ) -> List[DemandPoint]:
        """Ventas diarias reales de un producto en los últimos N días."""
        date_from = (date.today() - timedelta(days=days)).isoformat()
        date_to   = date.today().isoformat()

        branch_filter = "AND v.sucursal_id = ?" if branch_id else ""
        params = [producto_id, date_from, date_to]
        if branch_id:
            params.insert(0, branch_id)
            params = [producto_id, branch_id, date_from, date_to]

        sql = f"""
            SELECT
                DATE(v.fecha) AS dia,
                COALESCE(SUM(dv.cantidad), 0) AS qty,
                COALESCE(SUM(dv.subtotal), 0) AS revenue,
                COUNT(DISTINCT v.id) AS tickets
            FROM detalles_venta dv
            JOIN ventas v ON v.id = dv.venta_id
            WHERE dv.producto_id = ?
              {branch_filter}
              AND DATE(v.fecha) BETWEEN ? AND ?
              AND v.estado = 'completada'
            GROUP BY dia
            ORDER BY dia
        """
        params_q = ([producto_id] + ([branch_id] if branch_id else []) + [date_from, date_to])
        rows = self.db.fetchall(sql, params_q)

        points = []
        for r in rows:
            d = datetime.strptime(r["dia"], "%Y-%m-%d").date()
            dow = d.weekday()
            points.append(DemandPoint(
                fecha=r["dia"],
                dia_semana=dow,
                dia_nombre=DIAS[dow],
                cantidad=float(r["qty"] or 0),
                revenue=float(r["revenue"] or 0),
                tickets=int(r["tickets"] or 0),
            ))
        return points

    # ═════════════════════════════════════════════════════════════════════════
    # ALGORITMOS DE PREDICCIÓN
    # ═════════════════════════════════════════════════════════════════════════

    def _wma(self, series: List[float], window: int) -> float:
        """Promedio móvil ponderado — más reciente pesa más."""
        if not series:
            return 0.0
        data = series[-window:]
        n = len(data)
        if n == 0:
            return 0.0
        weights = list(range(1, n + 1))          # 1, 2, 3, …, n
        total = sum(w * v for w, v in zip(weights, data))
        weight_sum = sum(weights)
        return total / weight_sum if weight_sum else 0.0

    def _sma(self, series: List[float], window: int) -> float:
        """Promedio simple."""
        if not series:
            return 0.0
        data = series[-window:]
        return sum(data) / len(data)

    def _tendencia(self, series: List[float]) -> Tuple[str, float]:
        """Calcula tendencia comparando últimas 2 semanas."""
        if len(series) < 14:
            return "ESTABLE", 0.0
        semana1 = sum(series[-14:-7]) / 7
        semana2 = sum(series[-7:]) / 7
        if semana1 == 0:
            return "ESTABLE", 0.0
        pct = (semana2 - semana1) / semana1 * 100
        if pct > 5:
            return "CRECIENTE", round(pct, 1)
        elif pct < -5:
            return "DECRECIENTE", round(pct, 1)
        return "ESTABLE", round(pct, 1)

    def _compra_sugerida(
        self, demanda_diaria: float, stock_actual: float,
        dias: int = 7, buffer: float = 1.2,
    ) -> float:
        """
        Sugerencia de compra considerando stock actual y buffer de seguridad.
        buffer=1.2 → 20% de margen de seguridad.
        """
        necesario = demanda_diaria * dias * buffer
        return max(0.0, round(necesario - stock_actual, 3))

    # ═════════════════════════════════════════════════════════════════════════
    # FORECAST COMPLETO POR PRODUCTO
    # ═════════════════════════════════════════════════════════════════════════

    def forecast_producto(
        self,
        producto_id: int,
        branch_id: Optional[int] = None,
        days_history: int = 90,
    ) -> ProductForecast:
        """Genera pronóstico completo para un producto."""
        # Info del producto
        prod_row = self.db.fetchone(
            "SELECT nombre, unidad, existencia, stock_minimo FROM productos WHERE id=?",
            (producto_id,)
        )
        if not prod_row:
            raise ValueError(f"Producto {producto_id} no encontrado")

        nombre = prod_row["nombre"]
        unidad = prod_row["unidad"] or "kg"
        stock_actual = float(prod_row["existencia"] or 0)
        stock_minimo = float(prod_row["stock_minimo"] or 0)

        # Historial
        historico = self._get_daily_sales(producto_id, branch_id, days_history)
        series = [p.cantidad for p in historico]

        # Promedios
        wma_7  = self._wma(series, 7)
        sma_14 = self._sma(series, 14)
        sma_30 = self._sma(series, 30)

        # Tendencia
        tendencia, tendencia_pct = self._tendencia(series)

        # Demanda por día de semana
        demanda_por_dia: Dict[str, List[float]] = {d: [] for d in DIAS}
        for p in historico:
            demanda_por_dia[p.dia_nombre].append(p.cantidad)
        demanda_avg_dia = {
            d: (sum(v) / len(v) if v else 0.0)
            for d, v in demanda_por_dia.items()
        }
        pico = max(demanda_avg_dia, key=demanda_avg_dia.get) if demanda_avg_dia else "—"

        # Sugerencia de compra (usa WMA_7 como base)
        compra_7d = self._compra_sugerida(wma_7, stock_actual, 7)
        compra_semana = self._compra_sugerida(wma_7, stock_actual, 7, buffer=1.15)

        # Días de cobertura
        dias_cob = (stock_actual / wma_7) if wma_7 > 0 else 999

        # Alerta
        if stock_actual <= 0:
            alerta = "CRITICO"
        elif stock_actual < stock_minimo:
            alerta = "BAJO"
        elif stock_actual > wma_7 * 30:
            alerta = "EXCEDENTE"
        else:
            alerta = ""

        return ProductForecast(
            producto_id=producto_id,
            producto_nombre=nombre,
            unidad=unidad,
            historico=historico,
            wma_7=round(wma_7, 3),
            sma_14=round(sma_14, 3),
            sma_30=round(sma_30, 3),
            tendencia=tendencia,
            tendencia_pct=tendencia_pct,
            demanda_por_dia={d: round(v, 3) for d, v in demanda_avg_dia.items()},
            pico_semana=pico,
            compra_sugerida_7d=round(compra_7d, 3),
            compra_sugerida_semana=round(compra_semana, 3),
            stock_actual=stock_actual,
            dias_cobertura=round(dias_cob, 1),
            alerta=alerta,
        )

    # ═════════════════════════════════════════════════════════════════════════
    # FORECAST MULTI-PRODUCTO
    # ═════════════════════════════════════════════════════════════════════════

    def forecast_all(
        self,
        branch_id: Optional[int] = None,
        top_n: int = 30,
        days_history: int = 90,
    ) -> List[ProductForecast]:
        """Genera pronóstico para los N productos con más ventas."""
        branch_filter = "AND v.sucursal_id = ?" if branch_id else ""
        date_from = (date.today() - timedelta(days=days_history)).isoformat()

        params = []
        if branch_id: params.append(branch_id)
        params += [date_from, top_n]

        rows = self.db.fetchall(f"""
            SELECT dv.producto_id, SUM(dv.cantidad) AS total_qty
            FROM detalles_venta dv
            JOIN ventas v ON v.id = dv.venta_id
            WHERE v.estado = 'completada' {branch_filter}
              AND DATE(v.fecha) >= ?
            GROUP BY dv.producto_id
            ORDER BY total_qty DESC
            LIMIT ?
        """, params)

        results = []
        for row in rows:
            try:
                fc = self.forecast_producto(row["producto_id"], branch_id, days_history)
                results.append(fc)
            except Exception as e:
                logger.warning("forecast_producto %s: %s", row["producto_id"], e)

        # Publicar FORECAST_GENERADO al EventBus con resumen del batch
        if self._bus and results:
            try:
                from core.events.event_bus import FORECAST_GENERADO
                criticos = [f for f in results if f.alerta == "CRITICO"]
                self._bus.publish(FORECAST_GENERADO, {
                    "motor":           "wma_sma",
                    "branch_id":       branch_id,
                    "productos_total": len(results),
                    "criticos":        len(criticos),
                    "criticos_ids":    [f.producto_id for f in criticos],
                    "top_n":           top_n,
                    "days_history":    days_history,
                }, async_=True)
            except Exception:
                pass
        return results

    # ═════════════════════════════════════════════════════════════════════════
    # ALERTAS DE INVENTARIO
    # ═════════════════════════════════════════════════════════════════════════

    def get_alertas_inventario(
        self, branch_id: Optional[int] = None
    ) -> List[AlertaInventario]:
        """Genera lista de alertas de inventario con sugerencias de compra."""
        if branch_id:
            rows = self.db.fetchall("""
                SELECT p.id, p.nombre, p.unidad,
                       COALESCE(ia.cantidad, p.existencia, 0) AS stock,
                       COALESCE(p.stock_minimo, 0) AS stock_min
                FROM productos p
                LEFT JOIN inventario_actual ia
                    ON ia.producto_id = p.id AND ia.sucursal_id = ?
                WHERE p.activo = 1
            """, (branch_id,))
        else:
            rows = self.db.fetchall("""
        SELECT p.id, p.nombre, p.unidad,
                       COALESCE(p.existencia, 0) AS stock,
                       COALESCE(p.stock_minimo, 0) AS stock_min
                FROM productos p WHERE p.activo = 1
            """)

        date_from = (date.today() - timedelta(days=30)).isoformat()
        alertas = []

        for r in rows:
            pid = r["id"]
            stock = float(r["stock"] or 0)
            stock_min = float(r["stock_min"] or 0)

            # Demanda promedio últimos 30 días
            dem_row = self.db.fetchone("""
                SELECT COALESCE(SUM(dv.cantidad) / 30.0, 0) AS avg_daily
                FROM detalles_venta dv
                JOIN ventas v ON v.id = dv.venta_id
                WHERE dv.producto_id = ? AND v.estado='completada'
                  AND DATE(v.fecha) >= ?
            """, (pid, date_from))
            avg_daily = float(dem_row["avg_daily"] or 0) if dem_row else 0.0
            dias_cob = (stock / avg_daily) if avg_daily > 0 else 999

            if stock <= 0:
                nivel = "CRITICO"
            elif stock < stock_min:
                nivel = "BAJO"
            elif avg_daily > 0 and stock > avg_daily * 45:
                nivel = "EXCEDENTE"
            else:
                nivel = "OK"

            if nivel in ("CRITICO", "BAJO"):
                compra = max(0, avg_daily * 14 * 1.2 - stock)
            else:
                compra = 0.0

            if nivel != "OK":
                alertas.append(AlertaInventario(
                    producto_id=pid,
                    nombre=r["nombre"],
                    stock_actual=round(stock, 3),
                    stock_minimo=round(stock_min, 3),
                    unidad=r["unidad"] or "kg",
                    nivel=nivel,
                    dias_cobertura=round(dias_cob, 1),
                    compra_sugerida=round(compra, 3),
                ))

        # Ordenar: CRITICO primero, luego BAJO, luego EXCEDENTE
        orden = {"CRITICO": 0, "BAJO": 1, "EXCEDENTE": 2}
        alertas.sort(key=lambda a: orden.get(a.nivel, 9))
        return alertas

    # ═════════════════════════════════════════════════════════════════════════
    # ROTACIÓN DE INVENTARIO
    # ═════════════════════════════════════════════════════════════════════════

    def get_rotacion_inventario(
        self, branch_id: Optional[int] = None,
        date_from: str = "", date_to: str = "",
    ) -> List[Dict]:
        """
        Calcula rotación = ventas_periodo / inventario_promedio.
        Clasifica: ALTA (>12), MEDIA (3-12), BAJA (<3).
        """
        if not date_from:
            date_from = (date.today() - timedelta(days=30)).isoformat()
        if not date_to:
            date_to = date.today().isoformat()

        branch_f = "AND v.sucursal_id = ?" if branch_id else ""
        params = ([branch_id] if branch_id else []) + [date_from, date_to]

        rows = self.db.fetchall(f"""
            SELECT
                dv.producto_id,
                p.nombre, p.unidad,
                SUM(dv.cantidad) AS ventas_qty,
                SUM(dv.subtotal) AS ventas_valor,
                COALESCE(p.existencia, 0) AS stock_actual,
                COALESCE(p.precio_compra, p.costo, 0) AS costo_unit
            FROM detalles_venta dv
            JOIN ventas v ON v.id = dv.venta_id
            JOIN productos p ON p.id = dv.producto_id
            WHERE v.estado = 'completada' {branch_f}
              AND DATE(v.fecha) BETWEEN ? AND ?
            GROUP BY dv.producto_id
            ORDER BY ventas_qty DESC
        """, params)

        result = []
        for r in rows:
            ventas_qty = float(r["ventas_qty"] or 0)
            stock = float(r["stock_actual"] or 0)
            inv_prom = max(stock, ventas_qty / 2)  # estimación conservadora

            rotacion = ventas_qty / inv_prom if inv_prom > 0 else 0
            if rotacion >= 12:
                clasif = "ALTA"
            elif rotacion >= 3:
                clasif = "MEDIA"
            else:
                clasif = "BAJA"

            result.append({
                "producto_id": r["producto_id"],
                "nombre": r["nombre"],
                "unidad": r["unidad"],
                "ventas_qty": round(ventas_qty, 3),
                "ventas_valor": round(float(r["ventas_valor"] or 0), 2),
                "stock_actual": round(stock, 3),
                "rotacion": round(rotacion, 2),
                "clasificacion": clasif,
            })
        return result
