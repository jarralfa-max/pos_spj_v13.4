# core/services/decision_engine.py — SPJ POS v13.30 — FASE 5
"""
DecisionEngine — Motor de decisiones (SOLO SUGERENCIAS).

IMPORTANTE: Este motor NUNCA ejecuta acciones automáticamente.
Solo analiza datos y genera sugerencias que un humano debe aprobar.

CATEGORÍAS DE SUGERENCIAS:
    pricing      — ajustar precios (margen bajo, competencia, demanda)
    purchasing   — qué comprar, cuánto, cuándo
    transfers    — mover inventario entre sucursales
    cost_control — reducir gastos, optimizar operación
    loyalty      — ajustar programa de fidelización
    capital      — uso de capital, inversiones
    hr           — dotación de personal

USO:
    engine = container.decision_engine
    sugerencias = engine.generar_sugerencias()
    # → [{"tipo":"purchasing", "prioridad":"alta", "titulo":"Comprar pechuga",
    #     "detalle":"Stock para 2 días. Sugerencia: 200kg", "accion_propuesta":{...}}]
    # El usuario decide si ejecutar o no.
"""
from __future__ import annotations
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("spj.decisions")


@dataclass
class Suggestion:
    """Una sugerencia accionable."""
    tipo: str                    # pricing, purchasing, transfers, cost_control, etc.
    prioridad: str = "media"     # baja, media, alta, urgente
    titulo: str = ""
    detalle: str = ""
    impacto_estimado: str = ""   # Ej: "Ahorro: $2,500/mes"
    accion_propuesta: Dict = field(default_factory=dict)
    datos_soporte: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        emoji = {"urgente": "🔴", "alta": "🟠", "media": "🟡", "baja": "🔵"
                 }.get(self.prioridad, "⚪")
        return {
            "tipo": self.tipo,
            "prioridad": f"{emoji} {self.prioridad.upper()}",
            "titulo": self.titulo,
            "detalle": self.detalle,
            "impacto_estimado": self.impacto_estimado,
            "accion_propuesta": self.accion_propuesta,
            "datos_soporte": self.datos_soporte,
        }


class DecisionEngine:
    """
    Genera sugerencias basadas en datos del ERP.
    NO ejecuta nada — solo presenta opciones al usuario.
    """

    def __init__(self, db_conn, treasury_service=None,
                 loyalty_service=None, alert_engine=None,
                 module_config=None):
        self.db = db_conn
        self.treasury = treasury_service
        self.loyalty = loyalty_service
        self.alerts = alert_engine
        self._module_config = module_config
        self._bus = None
        try:
            from core.events.event_bus import get_bus
            self._bus = get_bus()
        except Exception:
            pass
        self._ensure_table()

    def _ensure_table(self):
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS decision_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo TEXT NOT NULL,
                    prioridad TEXT NOT NULL,
                    titulo TEXT NOT NULL,
                    detalle TEXT DEFAULT '',
                    impacto_estimado TEXT DEFAULT '',
                    accion_json TEXT DEFAULT '{}',
                    fecha TEXT DEFAULT (datetime('now'))
                )
            """)
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception:
            pass

    @property
    def enabled(self) -> bool:
        if self._module_config:
            return self._module_config.is_enabled('decisions')
        return True

    # ══════════════════════════════════════════════════════════════════════════
    #  API principal
    # ══════════════════════════════════════════════════════════════════════════

    def generar_sugerencias(self, sucursal_id: int = 0) -> List[Dict]:
        """Genera TODAS las sugerencias. Retorna lista ordenada por prioridad."""
        if not self.enabled:
            return []

        sugs: List[Suggestion] = []
        sugs.extend(self._suggest_pricing(sucursal_id))
        sugs.extend(self._suggest_purchasing(sucursal_id))
        sugs.extend(self._suggest_transfers())
        sugs.extend(self._suggest_cost_control(sucursal_id))
        sugs.extend(self._suggest_loyalty())
        sugs.extend(self._suggest_capital())
        sugs.extend(self._suggest_hr())

        # Ordenar: urgente > alta > media > baja
        order = {"urgente": 0, "alta": 1, "media": 2, "baja": 3}
        sugs.sort(key=lambda s: order.get(s.prioridad, 9))

        # Persistir en log y publicar urgentes al EventBus
        import json
        for s in sugs:
            self._persist(s)
            if s.prioridad in ("urgente", "alta") and self._bus:
                try:
                    from core.events.event_bus import DECISION_URGENTE
                    self._bus.publish(DECISION_URGENTE, {
                        "tipo":              s.tipo,
                        "prioridad":         s.prioridad,
                        "titulo":            s.titulo,
                        "detalle":           s.detalle,
                        "impacto_estimado":  s.impacto_estimado,
                        "accion_propuesta":  s.accion_propuesta,
                    }, async_=True)
                except Exception:
                    pass

        result = [s.to_dict() for s in sugs]
        logger.info("DecisionEngine: %d sugerencias (%d urgentes/altas)",
                    len(result),
                    sum(1 for s in sugs if s.prioridad in ("urgente", "alta")))
        return result

    def _persist(self, s: "Suggestion") -> None:
        import json
        try:
            self.db.execute(
                "INSERT INTO decision_log "
                "(tipo, prioridad, titulo, detalle, impacto_estimado, accion_json) "
                "VALUES (?,?,?,?,?,?)",
                (s.tipo, s.prioridad, s.titulo, s.detalle,
                 s.impacto_estimado,
                 json.dumps(s.accion_propuesta or {}, default=str)))
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  PRICING — Ajuste de precios
    # ══════════════════════════════════════════════════════════════════════════

    def _suggest_pricing(self, suc_id: int = 0) -> List[Suggestion]:
        sugs = []
        try:
            # Productos vendidos por debajo del costo
            rows = self.db.execute("""
                SELECT p.nombre, p.precio, COALESCE(p.precio_compra, p.costo, 0) as costo,
                       p.id
                FROM productos p
                WHERE p.activo=1 AND COALESCE(p.precio_compra, p.costo, 0) > 0
                  AND p.precio < COALESCE(p.precio_compra, p.costo, 0) * 1.10
            """).fetchall()
            for r in rows:
                nombre, precio, costo = r[0], float(r[1]), float(r[2])
                margen = ((precio - costo) / costo * 100) if costo > 0 else 0
                precio_sugerido = round(costo * 1.30, 2)  # 30% margen mínimo
                sugs.append(Suggestion(
                    tipo="pricing",
                    prioridad="alta" if margen < 0 else "media",
                    titulo=f"Ajustar precio: {nombre}",
                    detalle=f"Precio: ${precio:.2f} | Costo: ${costo:.2f} | "
                            f"Margen: {margen:.1f}%",
                    impacto_estimado=f"Precio sugerido: ${precio_sugerido:.2f} (+30% margen)",
                    accion_propuesta={
                        "tipo": "actualizar_precio",
                        "producto_id": r[3],
                        "precio_actual": precio,
                        "precio_sugerido": precio_sugerido,
                    }))
        except Exception:
            pass

        # Top 5 productos más vendidos con margen < 15%
        try:
            rows = self.db.execute("""
                SELECT p.nombre, p.precio, COALESCE(p.precio_compra,p.costo,0) as costo,
                       SUM(dv.cantidad) as vendido, p.id
                FROM detalles_venta dv
                JOIN ventas v ON v.id=dv.venta_id
                JOIN productos p ON p.id=dv.producto_id
                WHERE v.estado='completada' AND v.fecha > datetime('now','-30 days')
                  AND COALESCE(p.precio_compra,p.costo,0) > 0
                GROUP BY p.id
                HAVING ((p.precio - costo) / costo * 100) < 15
                ORDER BY vendido DESC LIMIT 5
            """).fetchall()
            for r in rows:
                nombre, precio, costo, vendido = r[0], float(r[1]), float(r[2]), float(r[3])
                margen = ((precio - costo) / costo * 100) if costo else 0
                sugs.append(Suggestion(
                    tipo="pricing", prioridad="media",
                    titulo=f"Oportunidad de precio: {nombre}",
                    detalle=f"Alta demanda ({vendido:.0f} uds/mes) con margen bajo ({margen:.1f}%).\n"
                            f"Subir precio impactaría positivamente.",
                    impacto_estimado=f"Si sube 10%: +${vendido * precio * 0.10:.2f}/mes extra",
                    accion_propuesta={"producto_id": r[4], "tipo": "revisar_precio"}))
        except Exception:
            pass
        return sugs

    # ══════════════════════════════════════════════════════════════════════════
    #  PURCHASING — Compras de inventario
    # ══════════════════════════════════════════════════════════════════════════

    def _suggest_purchasing(self, suc_id: int = 0) -> List[Suggestion]:
        sugs = []
        try:
            # Productos con stock < 3 días de venta
            rows = self.db.execute("""
                SELECT p.nombre, p.existencia, p.unidad, p.id,
                       COALESCE(p.precio_compra, p.costo, 0) as costo,
                       COALESCE((
                           SELECT AVG(dv.cantidad) FROM detalles_venta dv
                           JOIN ventas v ON v.id=dv.venta_id
                           WHERE dv.producto_id=p.id AND v.estado='completada'
                             AND v.fecha > datetime('now','-14 days')
                       ), 0) as venta_diaria_avg
                FROM productos p
                WHERE p.activo=1 AND p.existencia > 0
            """).fetchall()
            for r in rows:
                nombre, stock, unidad, pid = r[0], float(r[1]), r[2], r[3]
                costo, venta_dia = float(r[4]), float(r[5])
                if venta_dia <= 0:
                    continue
                dias_stock = stock / venta_dia if venta_dia > 0 else 999

                if dias_stock <= 3:
                    cantidad_sugerida = round(venta_dia * 7, 1)  # 1 semana
                    costo_compra = cantidad_sugerida * costo
                    sugs.append(Suggestion(
                        tipo="purchasing",
                        prioridad="urgente" if dias_stock <= 1 else "alta",
                        titulo=f"Comprar {nombre}",
                        detalle=f"Stock actual: {stock:.1f} {unidad} "
                                f"({dias_stock:.1f} días de venta).\n"
                                f"Venta promedio: {venta_dia:.1f} {unidad}/día",
                        impacto_estimado=f"Sugerencia: {cantidad_sugerida:.1f} {unidad} "
                                         f"(~${costo_compra:,.2f})",
                        accion_propuesta={
                            "tipo": "generar_orden_compra",
                            "producto_id": pid,
                            "cantidad": cantidad_sugerida,
                            "costo_estimado": costo_compra,
                        }))
                elif dias_stock > 60 and stock > 0:
                    sugs.append(Suggestion(
                        tipo="purchasing", prioridad="baja",
                        titulo=f"Sobre-stock: {nombre}",
                        detalle=f"Stock para {dias_stock:.0f} días. "
                                f"Considerar no re-comprar hasta bajar.",
                        accion_propuesta={"tipo": "pausar_compra", "producto_id": pid}))
        except Exception:
            pass
        return sugs

    # ══════════════════════════════════════════════════════════════════════════
    #  TRANSFERS — Mover inventario entre sucursales
    # ══════════════════════════════════════════════════════════════════════════

    def _suggest_transfers(self) -> List[Suggestion]:
        sugs = []
        try:
            # Productos con stock alto en una sucursal y bajo en otra
            rows = self.db.execute("""
                SELECT p.nombre, p.id,
                       bi1.branch_id as suc_origen, bi1.quantity as stock_origen,
                       bi2.branch_id as suc_destino, bi2.quantity as stock_destino,
                       s1.nombre as nombre_origen, s2.nombre as nombre_destino
                FROM branch_inventory bi1
                JOIN branch_inventory bi2 ON bi1.product_id = bi2.product_id
                    AND bi1.branch_id != bi2.branch_id
                JOIN productos p ON p.id = bi1.product_id
                JOIN sucursales s1 ON s1.id = bi1.branch_id
                JOIN sucursales s2 ON s2.id = bi2.branch_id
                WHERE bi1.quantity > bi2.quantity * 3
                  AND bi2.quantity < 10
                  AND bi1.quantity > 20
                  AND p.activo = 1
                LIMIT 10
            """).fetchall()
            for r in rows:
                nombre = r[0]
                stock_o, stock_d = float(r[3]), float(r[4])
                transferir = round((stock_o - stock_d) / 2, 1)
                sugs.append(Suggestion(
                    tipo="transfers", prioridad="media",
                    titulo=f"Transferir {nombre}",
                    detalle=f"{r[6]}: {stock_o:.0f} uds → {r[7]}: {stock_d:.0f} uds\n"
                            f"Sugerencia: mover {transferir:.0f} unidades.",
                    accion_propuesta={
                        "tipo": "transferencia",
                        "producto_id": r[1],
                        "origen": r[2], "destino": r[4],
                        "cantidad": transferir,
                    }))
        except Exception:
            pass
        return sugs

    # ══════════════════════════════════════════════════════════════════════════
    #  COST CONTROL — Reducir gastos
    # ══════════════════════════════════════════════════════════════════════════

    def _suggest_cost_control(self, suc_id: int = 0) -> List[Suggestion]:
        sugs = []
        if not self.treasury:
            return sugs
        try:
            k = self.treasury.kpis_financieros(sucursal_id=suc_id)
            egresos = k.get("egresos", {})

            # Merma como % de compras
            compras = egresos.get("compras_inventario", 0)
            merma = egresos.get("merma", 0)
            if compras > 0 and merma > 0:
                pct = merma / compras * 100
                if pct > 3:
                    ahorro = merma * 0.5  # Meta: reducir 50%
                    sugs.append(Suggestion(
                        tipo="cost_control", prioridad="alta",
                        titulo="Reducir merma",
                        detalle=f"Merma = {pct:.1f}% de compras (${merma:,.2f}).\n"
                                f"Revisar cadena de frío, rotación FIFO, porciones.",
                        impacto_estimado=f"Meta -50%: ahorro ${ahorro:,.2f}/mes",
                        accion_propuesta={"tipo": "plan_reduccion_merma"}))

            # Gastos fijos vs ingresos
            fijos = egresos.get("gastos_fijos", 0)
            ingresos = k.get("ingresos", 0)
            if ingresos > 0 and fijos / ingresos > 0.25:
                sugs.append(Suggestion(
                    tipo="cost_control", prioridad="media",
                    titulo="Gastos fijos altos",
                    detalle=f"Fijos: ${fijos:,.2f} = {fijos/ingresos*100:.1f}% de ingresos.\n"
                            f"Renegociar renta, revisar servicios innecesarios.",
                    impacto_estimado=f"Meta -10%: ahorro ${fijos*0.10:,.2f}/mes"))

            # Nómina vs ingresos
            nomina = egresos.get("nomina_rrhh", 0)
            if ingresos > 0 and nomina / ingresos > 0.30:
                sugs.append(Suggestion(
                    tipo="cost_control", prioridad="media",
                    titulo="Optimizar nómina",
                    detalle=f"Nómina: ${nomina:,.2f} = {nomina/ingresos*100:.1f}% de ingresos.\n"
                            f"Meta: 25-30%. Revisar turnos y productividad.",
                    impacto_estimado=f"Reducir a 25%: ahorro ${nomina - ingresos*0.25:,.2f}/mes"))
        except Exception:
            pass
        return sugs

    # ══════════════════════════════════════════════════════════════════════════
    #  LOYALTY — Ajustar programa de fidelización
    # ══════════════════════════════════════════════════════════════════════════

    def _suggest_loyalty(self) -> List[Suggestion]:
        sugs = []
        if not self.loyalty:
            return sugs
        try:
            pasivo = self.loyalty.pasivo_financiero()
            valor = pasivo.get("valor_monetario", 0)
            total_estrellas = pasivo.get("total_estrellas", 0)

            if valor > 10000:
                sugs.append(Suggestion(
                    tipo="loyalty", prioridad="alta",
                    titulo="Pasivo de fidelización alto",
                    detalle=f"Hay {total_estrellas:,} estrellas en circulación "
                            f"(= ${valor:,.2f} de obligación).\n"
                            f"Opciones: reducir tasa, aumentar caducidad, promover canje.",
                    impacto_estimado=f"Si reduce tasa 50%: reduce emisión ~${valor*0.5:,.2f}/mes",
                    accion_propuesta={"tipo": "ajustar_tasa_loyalty"}))

            # Clientes con saldo alto que nunca canjean
            top = self.db.execute("""
                SELECT cliente_id, SUM(monto) as saldo
                FROM growth_ledger
                WHERE revertido=0 AND moneda='estrellas'
                  AND (expira_en IS NULL OR expira_en > datetime('now'))
                GROUP BY cliente_id
                HAVING saldo > 1000
                ORDER BY saldo DESC LIMIT 5
            """).fetchall()
            if top:
                sugs.append(Suggestion(
                    tipo="loyalty", prioridad="baja",
                    titulo=f"{len(top)} clientes con saldo alto sin canjear",
                    detalle="Enviar promoción de canje para reducir pasivo.",
                    accion_propuesta={"tipo": "promocion_canje",
                                      "clientes": [r[0] for r in top]}))
        except Exception:
            pass
        return sugs

    # ══════════════════════════════════════════════════════════════════════════
    #  CAPITAL — Uso del capital
    # ══════════════════════════════════════════════════════════════════════════

    def _suggest_capital(self) -> List[Suggestion]:
        sugs = []
        if not self.treasury:
            return sugs
        try:
            k = self.treasury.kpis_financieros()
            capital = k.get("capital_disponible", 0)
            roi = k.get("roi_pct", 0)
            burn = k.get("burn_rate_meses", 0)

            if capital > 0 and burn > 6 and roi > 10:
                sugs.append(Suggestion(
                    tipo="capital", prioridad="baja",
                    titulo="Capital ocioso — considerar inversión",
                    detalle=f"Capital disponible: ${capital:,.2f}, ROI: {roi:.1f}%, "
                            f"Burn rate: {burn:.1f} meses.\n"
                            f"El negocio es rentable y hay margen para invertir.",
                    accion_propuesta={"tipo": "evaluar_inversion"}))
            elif burn < 3 and burn > 0:
                sugs.append(Suggestion(
                    tipo="capital", prioridad="urgente",
                    titulo="Inyección de capital necesaria",
                    detalle=f"Solo quedan {burn:.1f} meses de capital.\n"
                            f"Considerar: inyección de socios, crédito bancario, "
                            f"o reducción drástica de gastos.",
                    accion_propuesta={"tipo": "solicitar_inyeccion"}))
        except Exception:
            pass
        return sugs

    # ══════════════════════════════════════════════════════════════════════════
    #  HR — Dotación de personal
    # ══════════════════════════════════════════════════════════════════════════

    def _suggest_hr(self) -> List[Suggestion]:
        sugs = []
        try:
            # Ventas por empleado
            empleados = self._q("SELECT COUNT(*) FROM empleados WHERE activo=1")
            ingresos = self._q(
                "SELECT COALESCE(SUM(total),0) FROM ventas "
                "WHERE estado='completada' AND fecha > datetime('now','-30 days')")
            if empleados > 0 and ingresos > 0:
                venta_por_emp = ingresos / empleados
                if venta_por_emp < 20000:
                    sugs.append(Suggestion(
                        tipo="hr", prioridad="media",
                        titulo="Baja productividad por empleado",
                        detalle=f"Venta/empleado: ${venta_por_emp:,.2f}/mes "
                                f"({int(empleados)} empleados).\n"
                                f"Meta: >$25,000/empleado.",
                        accion_propuesta={"tipo": "revisar_plantilla"}))
        except Exception:
            pass
        return sugs

    # ══════════════════════════════════════════════════════════════════════════
    #  Helper
    # ══════════════════════════════════════════════════════════════════════════

    def _q(self, sql: str, params: list = None) -> float:
        try:
            row = self.db.execute(sql, params or []).fetchone()
            return float(row[0]) if row and row[0] else 0.0
        except Exception:
            return 0.0
