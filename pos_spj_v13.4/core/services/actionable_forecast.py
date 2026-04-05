# core/services/actionable_forecast.py — SPJ POS v13.30 — FASE 6
"""
ActionableForecastService — Convierte predicciones en acciones concretas.

Ya existen:
  - DemandForecastEngine (series de tiempo por producto)
  - ReplenishmentEngine (punto de reorden)
  - TransferSuggestionEngine (entre sucursales)

ESTA FASE agrega:
  - DemandAnalyzer: analiza tendencias y estacionalidad
  - PurchasePlanner: genera plan de compras con montos
  - RiskAnalyzer: detecta riesgos de inventario
  - Orquestador que une forecast → decisión → acción propuesta

TODO se integra con DecisionEngine (Fase 5) y TreasuryService (Fase 3).

USO:
    forecast = container.actionable_forecast
    plan = forecast.plan_compras_semanal(sucursal_id=1)
    # → [{"producto":"Pechuga","comprar_kg":200,"costo_est":18000,"prioridad":"alta"}]
    riesgos = forecast.analisis_riesgos()
    # → [{"tipo":"desabasto","producto":"Arrachera","dias_stock":1.5}]
"""
from __future__ import annotations
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any

logger = logging.getLogger("spj.forecast")


class ActionableForecastService:
    """Convierte predicciones de demanda en planes de compra accionables."""

    def __init__(self, db_conn, treasury_service=None, module_config=None):
        self.db = db_conn
        self.treasury = treasury_service
        self._module_config = module_config
        self._forecast_engine = None
        self._init_engines()

    def _init_engines(self):
        try:
            from core.forecast.demand_forecast_engine import DemandForecastEngine
            self._forecast_engine = DemandForecastEngine(self.db)
        except Exception as e:
            logger.debug("DemandForecastEngine no disponible: %s", e)

    @property
    def enabled(self) -> bool:
        if self._module_config:
            return self._module_config.is_enabled('forecasting')
        return True

    # ══════════════════════════════════════════════════════════════════════════
    #  DemandAnalyzer — analiza tendencias
    # ══════════════════════════════════════════════════════════════════════════

    def analisis_demanda(self, producto_id: int = 0,
                          sucursal_id: int = 1,
                          dias: int = 30) -> List[Dict]:
        """Analiza tendencia de demanda por producto."""
        results = []
        try:
            q = """
                SELECT p.id, p.nombre, p.existencia, p.unidad,
                       COALESCE(p.precio_compra, p.costo, 0) as costo,
                       p.stock_minimo
                FROM productos p
                WHERE p.activo=1
            """
            params = []
            if producto_id:
                q += " AND p.id=?"
                params.append(producto_id)

            productos = self.db.execute(q, params).fetchall()

            for prod in productos:
                pid, nombre, stock = prod[0], prod[1], float(prod[2] or 0)
                unidad, costo = prod[3] or 'kg', float(prod[4] or 0)
                stock_min = float(prod[5] or 0)

                # Ventas últimos N días
                ventas = self.db.execute("""
                    SELECT DATE(v.fecha) as dia, SUM(dv.cantidad) as qty
                    FROM detalles_venta dv
                    JOIN ventas v ON v.id=dv.venta_id
                    WHERE dv.producto_id=? AND v.estado='completada'
                      AND v.fecha > datetime('now', ?)
                    GROUP BY DATE(v.fecha)
                    ORDER BY dia
                """, (pid, f'-{dias} days')).fetchall()

                if not ventas:
                    continue

                cantidades = [float(v[1]) for v in ventas]
                dias_con_venta = len(cantidades)
                promedio_diario = sum(cantidades) / dias if dias > 0 else 0
                dias_stock = stock / promedio_diario if promedio_diario > 0 else 999

                # Tendencia: comparar primera mitad vs segunda mitad
                mitad = len(cantidades) // 2
                if mitad > 2:
                    avg_1 = sum(cantidades[:mitad]) / mitad
                    avg_2 = sum(cantidades[mitad:]) / (len(cantidades) - mitad)
                    tendencia_pct = ((avg_2 - avg_1) / avg_1 * 100) if avg_1 > 0 else 0
                else:
                    tendencia_pct = 0

                if tendencia_pct > 20:
                    tendencia = "📈 creciendo"
                elif tendencia_pct < -20:
                    tendencia = "📉 decreciendo"
                else:
                    tendencia = "➡️ estable"

                results.append({
                    "producto_id": pid,
                    "nombre": nombre,
                    "stock_actual": stock,
                    "unidad": unidad,
                    "promedio_diario": round(promedio_diario, 2),
                    "dias_stock": round(dias_stock, 1),
                    "tendencia": tendencia,
                    "tendencia_pct": round(tendencia_pct, 1),
                    "dias_con_venta": dias_con_venta,
                    "costo_unitario": costo,
                })

            results.sort(key=lambda x: x["dias_stock"])
        except Exception as e:
            logger.error("analisis_demanda: %s", e)
        return results

    # ══════════════════════════════════════════════════════════════════════════
    #  PurchasePlanner — plan de compras semanal
    # ══════════════════════════════════════════════════════════════════════════

    def plan_compras_semanal(self, sucursal_id: int = 1,
                              dias_cobertura: int = 7) -> Dict:
        """
        Genera plan de compras para cubrir N días de venta.
        Retorna lista de productos + totales + validación de capital.
        """
        analisis = self.analisis_demanda(sucursal_id=sucursal_id)
        items = []
        total_costo = 0.0

        for prod in analisis:
            if prod["promedio_diario"] <= 0:
                continue
            necesidad = prod["promedio_diario"] * dias_cobertura
            comprar = max(0, necesidad - prod["stock_actual"])

            if comprar <= 0:
                continue

            costo = comprar * prod["costo_unitario"]

            if prod["dias_stock"] <= 1:
                prioridad = "urgente"
            elif prod["dias_stock"] <= 3:
                prioridad = "alta"
            elif prod["dias_stock"] <= dias_cobertura:
                prioridad = "media"
            else:
                prioridad = "baja"

            items.append({
                "producto_id": prod["producto_id"],
                "nombre": prod["nombre"],
                "stock_actual": prod["stock_actual"],
                "dias_stock": prod["dias_stock"],
                "promedio_diario": prod["promedio_diario"],
                "comprar": round(comprar, 1),
                "unidad": prod["unidad"],
                "costo_unitario": prod["costo_unitario"],
                "costo_total": round(costo, 2),
                "prioridad": prioridad,
                "tendencia": prod["tendencia"],
            })
            total_costo += costo

        # Ordenar por prioridad
        order = {"urgente": 0, "alta": 1, "media": 2, "baja": 3}
        items.sort(key=lambda x: order.get(x["prioridad"], 9))

        # Validar contra capital disponible
        capital_disponible = 0
        capital_suficiente = True
        if self.treasury:
            try:
                estado = self.treasury.estado_cuenta()
                capital_disponible = estado.get("capital_disponible", 0)
                capital_suficiente = capital_disponible >= total_costo
            except Exception:
                pass

        return {
            "dias_cobertura": dias_cobertura,
            "items": items,
            "total_productos": len(items),
            "total_costo_estimado": round(total_costo, 2),
            "capital_disponible": round(capital_disponible, 2),
            "capital_suficiente": capital_suficiente,
            "urgentes": sum(1 for i in items if i["prioridad"] == "urgente"),
        }

    # ══════════════════════════════════════════════════════════════════════════
    #  RiskAnalyzer — riesgos de inventario
    # ══════════════════════════════════════════════════════════════════════════

    def analisis_riesgos(self, sucursal_id: int = 1) -> List[Dict]:
        """Identifica riesgos: desabasto, sobre-stock, caducidad, merma."""
        riesgos = []
        analisis = self.analisis_demanda(sucursal_id=sucursal_id)

        for prod in analisis:
            # Riesgo de desabasto
            if 0 < prod["dias_stock"] <= 2:
                riesgos.append({
                    "tipo": "desabasto",
                    "severidad": "critico" if prod["dias_stock"] <= 1 else "alto",
                    "producto": prod["nombre"],
                    "detalle": f"Stock para {prod['dias_stock']:.1f} días",
                    "impacto": f"Pérdida potencial: "
                               f"${prod['promedio_diario'] * prod['costo_unitario'] * 3:,.2f} "
                               f"(3 días sin vender)",
                    "producto_id": prod["producto_id"],
                })

            # Sobre-stock (>60 días)
            if prod["dias_stock"] > 60:
                capital_atrapado = prod["stock_actual"] * prod["costo_unitario"]
                riesgos.append({
                    "tipo": "sobre_stock",
                    "severidad": "medio",
                    "producto": prod["nombre"],
                    "detalle": f"Stock para {prod['dias_stock']:.0f} días",
                    "impacto": f"Capital atrapado: ${capital_atrapado:,.2f}",
                    "producto_id": prod["producto_id"],
                })

        # Caducidad próxima
        try:
            lotes = self.db.execute("""
                SELECT l.numero_lote, p.nombre, l.fecha_caducidad,
                       l.cantidad_actual, p.id
                FROM lotes l
                JOIN productos p ON p.id=l.producto_id
                WHERE l.estado='activo'
                  AND l.fecha_caducidad IS NOT NULL
                  AND l.fecha_caducidad <= date('now', '+5 days')
                  AND l.cantidad_actual > 0
                ORDER BY l.fecha_caducidad
            """).fetchall()
            for l in (lotes or []):
                riesgos.append({
                    "tipo": "caducidad",
                    "severidad": "critico" if l[2] <= date.today().isoformat() else "alto",
                    "producto": l[1],
                    "detalle": f"Lote {l[0]} caduca {l[2]}, quedan {float(l[3]):.1f} uds",
                    "producto_id": l[4],
                })
        except Exception:
            pass

        # Merma recurrente (>3% del producto)
        try:
            merma_prods = self.db.execute("""
                SELECT p.nombre, SUM(m.cantidad) as merma_total,
                       COALESCE(SUM(m.cantidad * m.costo_unitario), 0) as costo_merma,
                       p.id
                FROM merma m
                JOIN productos p ON p.id=m.producto_id
                WHERE m.fecha > datetime('now', '-30 days')
                GROUP BY p.id
                HAVING merma_total > 5
                ORDER BY costo_merma DESC LIMIT 5
            """).fetchall()
            for m in (merma_prods or []):
                riesgos.append({
                    "tipo": "merma_recurrente",
                    "severidad": "medio",
                    "producto": m[0],
                    "detalle": f"Merma: {float(m[1]):.1f} uds en 30 días "
                               f"(${float(m[2]):,.2f})",
                    "producto_id": m[3],
                })
        except Exception:
            pass

        # Ordenar por severidad
        sev_order = {"critico": 0, "alto": 1, "medio": 2, "bajo": 3}
        riesgos.sort(key=lambda r: sev_order.get(r["severidad"], 9))
        return riesgos

    # ══════════════════════════════════════════════════════════════════════════
    #  Forecast individual (wrapper del engine existente)
    # ══════════════════════════════════════════════════════════════════════════

    def forecast_producto(self, producto_id: int,
                           sucursal_id: int = 1,
                           dias: int = 7) -> Optional[Dict]:
        """Forecast de un producto individual usando DemandForecastEngine."""
        if not self._forecast_engine:
            return None
        try:
            return self._forecast_engine.forecast_product(
                producto_id, sucursal_id, horizon_days=dias)
        except Exception as e:
            logger.debug("forecast_producto: %s", e)
            return None
