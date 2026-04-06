# core/services/franchise_manager.py — SPJ POS v13.30 — FASE 10
"""
FranchiseManager — Gestión multi-sucursal tipo franquicia.

FUNCIONES:
    - Ranking de sucursales por rendimiento
    - Comparativo financiero entre sucursales
    - Eficiencia operativa por sucursal
    - TransferEngine (sugerir transferencias de inventario)
    - Control central de capital por sucursal

USO:
    fm = container.franchise_manager
    ranking = fm.ranking_sucursales()
    comparison = fm.comparar_sucursales([1, 2, 3])
    transfers = fm.sugerir_transferencias()
"""
from __future__ import annotations
import logging
from datetime import date, datetime
from typing import Dict, List, Any, Optional

logger = logging.getLogger("spj.franchise")


class FranchiseManager:
    """Gestión multi-sucursal con métricas comparativas."""

    def __init__(self, db_conn, treasury_service=None, module_config=None):
        self.db = db_conn
        self.treasury = treasury_service
        self._module_config = module_config
        self._bus = None
        try:
            from core.events.event_bus import get_bus
            self._bus = get_bus()
        except Exception:
            pass

    @property
    def enabled(self) -> bool:
        if self._module_config:
            return self._module_config.is_enabled('franchise_mode')
        return False

    # ══════════════════════════════════════════════════════════════════════════
    #  Ranking de sucursales
    # ══════════════════════════════════════════════════════════════════════════

    def ranking_sucursales(self, fecha_desde: str = "",
                           fecha_hasta: str = "") -> List[Dict]:
        """
        Ranking de sucursales por utilidad neta.
        Incluye métricas de eficiencia.
        """
        hoy = date.today()
        df = fecha_desde or date(hoy.year, hoy.month, 1).isoformat()
        dt = fecha_hasta or hoy.isoformat()

        sucursales = self._get_sucursales()
        ranking = []

        for suc in sucursales:
            sid = suc["id"]
            ingresos = self._q(
                "SELECT COALESCE(SUM(total),0) FROM ventas "
                "WHERE estado='completada' AND sucursal_id=? "
                "AND DATE(fecha) BETWEEN ? AND ?", [sid, df, dt])
            tickets = int(self._q(
                "SELECT COUNT(*) FROM ventas "
                "WHERE estado='completada' AND sucursal_id=? "
                "AND DATE(fecha) BETWEEN ? AND ?", [sid, df, dt]))
            gastos = self._q(
                "SELECT COALESCE(SUM(monto),0) FROM gastos "
                "WHERE DATE(fecha) BETWEEN ? AND ?", [df, dt])
            nomina = self._q(
                "SELECT COALESCE(SUM(np.total),0) FROM nomina_pagos np "
                "JOIN empleados e ON e.id=np.empleado_id "
                "WHERE e.sucursal_id=? AND np.estado='pagado' "
                "AND DATE(np.fecha) BETWEEN ? AND ?", [sid, df, dt])
            empleados = int(self._q(
                "SELECT COUNT(*) FROM empleados "
                "WHERE sucursal_id=? AND activo=1", [sid]))

            utilidad = ingresos - nomina  # simplificado para ranking
            eficiencia = (ingresos / max(1, empleados))  # ingreso por empleado
            ticket_avg = (ingresos / max(1, tickets))

            ranking.append({
                "sucursal_id": sid,
                "nombre": suc["nombre"],
                "ingresos": round(ingresos, 2),
                "tickets": tickets,
                "ticket_promedio": round(ticket_avg, 2),
                "nomina": round(nomina, 2),
                "utilidad_estimada": round(utilidad, 2),
                "empleados": empleados,
                "ingreso_por_empleado": round(eficiencia, 2),
                "margen_pct": round(
                    (utilidad / ingresos * 100) if ingresos else 0, 1),
            })

        # Ordenar por utilidad descendente
        ranking.sort(key=lambda x: x["utilidad_estimada"], reverse=True)

        # Agregar posición
        for i, r in enumerate(ranking):
            r["posicion"] = i + 1
            r["medalla"] = ["🥇", "🥈", "🥉"][i] if i < 3 else f"#{i+1}"

        # Publicar evento de ranking generado
        if self._bus and ranking:
            try:
                from core.events.event_bus import FRANQUICIA_RANKING_GENERADO
                top = ranking[0]
                self._bus.publish(FRANQUICIA_RANKING_GENERADO, {
                    "sucursales_count": len(ranking),
                    "top_sucursal":     top["nombre"],
                    "top_sucursal_id":  top["sucursal_id"],
                    "top_utilidad":     top["utilidad_estimada"],
                    "top_margen_pct":   top["margen_pct"],
                    "fecha_desde":      df,
                    "fecha_hasta":      dt,
                }, async_=True)
            except Exception:
                pass

        return ranking

    # ══════════════════════════════════════════════════════════════════════════
    #  Comparativo entre sucursales
    # ══════════════════════════════════════════════════════════════════════════

    def comparar_sucursales(self, sucursal_ids: List[int] = None,
                             df: str = "", dt: str = "") -> Dict:
        """Comparativo detallado entre sucursales seleccionadas."""
        if self.treasury:
            try:
                por_suc = self.treasury.kpis_por_sucursal(df, dt)
                if sucursal_ids:
                    por_suc = [s for s in por_suc
                               if s.get("sucursal_id") in sucursal_ids]
                # Agregar promedios
                if por_suc:
                    n = len(por_suc)
                    avg_ingreso = sum(s["ingresos"] for s in por_suc) / n
                    avg_margen = sum(s["margen_neto_pct"] for s in por_suc) / n
                    return {
                        "sucursales": por_suc,
                        "promedios": {
                            "ingreso_promedio": round(avg_ingreso, 2),
                            "margen_promedio": round(avg_margen, 1),
                        },
                        "mejor": max(por_suc,
                                     key=lambda x: x["utilidad_neta"]),
                        "peor": min(por_suc,
                                    key=lambda x: x["utilidad_neta"]),
                    }
            except Exception as e:
                logger.debug("comparar: %s", e)

        return {"sucursales": [], "promedios": {}}

    # ══════════════════════════════════════════════════════════════════════════
    #  Sugerir transferencias de inventario
    # ══════════════════════════════════════════════════════════════════════════

    def sugerir_transferencias(self, limit: int = 20) -> List[Dict]:
        """
        Detecta productos con sobre-stock en una sucursal y
        bajo-stock en otra. Sugiere transferencias.
        """
        try:
            # Productos con stock muy diferente entre sucursales
            rows = self.db.execute("""
                SELECT p.id, p.nombre, p.stock_minimo,
                    bi1.branch_id AS suc_alta, bi1.quantity AS stock_alta,
                    s1.nombre AS nombre_alta,
                    bi2.branch_id AS suc_baja, bi2.quantity AS stock_baja,
                    s2.nombre AS nombre_baja
                FROM productos p
                JOIN branch_inventory bi1 ON bi1.product_id = p.id
                JOIN branch_inventory bi2 ON bi2.product_id = p.id
                JOIN sucursales s1 ON s1.id = bi1.branch_id
                JOIN sucursales s2 ON s2.id = bi2.branch_id
                WHERE bi1.branch_id != bi2.branch_id
                  AND bi1.quantity > COALESCE(p.stock_minimo, 5) * 3
                  AND bi2.quantity < COALESCE(p.stock_minimo, 5)
                  AND p.activo = 1
                ORDER BY (bi1.quantity - bi2.quantity) DESC
                LIMIT ?
            """, (limit,)).fetchall()

            transferencias = []
            seen = set()
            for r in rows:
                key = f"{r[0]}_{r[3]}_{r[6]}"
                if key in seen:
                    continue
                seen.add(key)
                qty_transferir = min(
                    r[4] * 0.3,  # max 30% del stock alto
                    max(0, r[2] - r[7]) if r[2] else r[4] * 0.2)
                if qty_transferir > 0:
                    transferencias.append({
                        "producto_id": r[0],
                        "producto": r[1],
                        "desde_sucursal": r[5],
                        "desde_id": r[3],
                        "stock_origen": round(r[4], 2),
                        "hacia_sucursal": r[8],
                        "hacia_id": r[6],
                        "stock_destino": round(r[7], 2),
                        "cantidad_sugerida": round(qty_transferir, 2),
                    })
            # Publicar sugerencias de transferencia como decisiones urgentes
            if self._bus and transferencias:
                try:
                    from core.events.event_bus import (
                        FRANQUICIA_TRANSFERENCIA_SUGERIDA, DECISION_URGENTE)
                    for t in transferencias[:5]:  # máximo 5 eventos
                        self._bus.publish(FRANQUICIA_TRANSFERENCIA_SUGERIDA, {
                            "producto_id":       t["producto_id"],
                            "producto":          t["producto"],
                            "desde_sucursal":    t["desde_sucursal"],
                            "desde_id":          t["desde_id"],
                            "hacia_sucursal":    t["hacia_sucursal"],
                            "hacia_id":          t["hacia_id"],
                            "cantidad_sugerida": t["cantidad_sugerida"],
                        }, async_=True)
                    # Publicar decisión urgente si hay transferencias pendientes
                    self._bus.publish(DECISION_URGENTE, {
                        "tipo":             "franquicia_transferencia",
                        "prioridad":        "media",
                        "titulo":           f"Transferencias de inventario sugeridas ({len(transferencias)})",
                        "detalle":          f"Hay {len(transferencias)} productos con desequilibrio de stock entre sucursales.",
                        "impacto_estimado": "Reducción de merma y mejora de disponibilidad",
                        "accion_propuesta": "Revisar y aprobar transferencias en módulo de logística",
                    }, async_=True)
                except Exception:
                    pass

            return transferencias
        except Exception as e:
            logger.debug("transferencias: %s", e)
            return []

    # ══════════════════════════════════════════════════════════════════════════
    #  Eficiencia por sucursal
    # ══════════════════════════════════════════════════════════════════════════

    def eficiencia_sucursal(self, sucursal_id: int) -> Dict:
        """Métricas de eficiencia para una sucursal específica."""
        hoy = date.today()
        df = date(hoy.year, hoy.month, 1).isoformat()
        dt = hoy.isoformat()

        ingresos = self._q(
            "SELECT COALESCE(SUM(total),0) FROM ventas "
            "WHERE estado='completada' AND sucursal_id=? "
            "AND DATE(fecha) BETWEEN ? AND ?", [sucursal_id, df, dt])
        tickets = int(self._q(
            "SELECT COUNT(*) FROM ventas WHERE estado='completada' "
            "AND sucursal_id=? AND DATE(fecha) BETWEEN ? AND ?",
            [sucursal_id, df, dt]))
        empleados = int(self._q(
            "SELECT COUNT(*) FROM empleados "
            "WHERE sucursal_id=? AND activo=1", [sucursal_id]))
        merma = self._q(
            "SELECT COALESCE(SUM(cantidad*COALESCE(costo_unitario,0)),0) "
            "FROM merma WHERE DATE(fecha) BETWEEN ? AND ?", [df, dt])
        cancelaciones = int(self._q(
            "SELECT COUNT(*) FROM ventas WHERE estado='cancelada' "
            "AND sucursal_id=? AND DATE(fecha) BETWEEN ? AND ?",
            [sucursal_id, df, dt]))

        return {
            "sucursal_id": sucursal_id,
            "ingresos_mes": round(ingresos, 2),
            "tickets_mes": tickets,
            "empleados": empleados,
            "ingreso_por_empleado": round(ingresos / max(1, empleados), 2),
            "ingreso_por_ticket": round(ingresos / max(1, tickets), 2),
            "merma_mes": round(merma, 2),
            "merma_pct_ingresos": round(
                (merma / ingresos * 100) if ingresos else 0, 1),
            "cancelaciones": cancelaciones,
            "tasa_cancelacion": round(
                (cancelaciones / max(1, tickets + cancelaciones) * 100), 1),
        }

    # ══════════════════════════════════════════════════════════════════════════
    #  Helpers
    # ══════════════════════════════════════════════════════════════════════════

    def _get_sucursales(self) -> List[Dict]:
        try:
            rows = self.db.execute(
                "SELECT id, nombre FROM sucursales WHERE activa=1"
            ).fetchall()
            return [{"id": r[0], "nombre": r[1]} for r in rows]
        except Exception:
            return []

    def _q(self, sql: str, params: list = None) -> float:
        try:
            row = self.db.execute(sql, params or []).fetchone()
            return float(row[0]) if row and row[0] else 0.0
        except Exception:
            return 0.0
