# core/services/alert_engine.py — SPJ POS v13.30 — FASE 4
"""
AlertEngine — Motor de alertas inteligentes empresariales.

Extiende AlertasService (operativo) con análisis financiero, 
detección de anomalías y alertas de negocio.

NIVELES DE SEVERIDAD:
    low        — informativo (log)
    medium     — atención requerida (UI)
    high       — acción urgente (UI + notificación)
    critical   — riesgo para el negocio (UI + WhatsApp)

CATEGORÍAS:
    financial  — pérdidas, margen bajo, flujo insuficiente, ROI negativo
    inventory  — stock bajo, merma alta, caducidad, sobre-stock
    loyalty    — costo excesivo, canje anómalo, pasivo alto
    hr         — costo RRHH alto vs ingresos, horas extra
    operations — cancelaciones frecuentes, ajustes sospechosos
    sales      — caída de ventas, ticket promedio bajo

USO:
    alert_engine = container.alert_engine
    alertas = alert_engine.run_all_checks()
    criticas = alert_engine.get_alerts(severity='critical')
"""
from __future__ import annotations
import json
import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger("spj.alerts")


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertCategory(str, Enum):
    FINANCIAL = "financial"
    INVENTORY = "inventory"
    LOYALTY = "loyalty"
    HR = "hr"
    OPERATIONS = "operations"
    SALES = "sales"


SEVERITY_EMOJI = {
    Severity.LOW: "🔵",
    Severity.MEDIUM: "🟡",
    Severity.HIGH: "🟠",
    Severity.CRITICAL: "🔴",
}


class Alert:
    """Alerta individual."""
    def __init__(self, category: str, severity: str, title: str,
                 message: str, data: Dict = None):
        self.category = category
        self.severity = severity
        self.title = title
        self.message = message
        self.data = data or {}
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict:
        emoji = SEVERITY_EMOJI.get(self.severity, "ℹ️")
        return {
            "category": self.category,
            "severity": self.severity,
            "title": f"{emoji} {self.title}",
            "message": self.message,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }


class AlertEngine:
    """Motor de alertas inteligentes del ERP."""

    def __init__(self, db_conn, treasury_service=None,
                 loyalty_service=None, alertas_service=None,
                 module_config=None):
        self.db = db_conn
        self.treasury = treasury_service
        self.loyalty = loyalty_service
        self.alertas = alertas_service
        self._module_config = module_config
        self._alerts: List[Alert] = []
        self._bus = None
        try:
            from core.events.event_bus import get_bus
            self._bus = get_bus()
        except Exception:
            pass
        self._ensure_table()

    @property
    def enabled(self) -> bool:
        if self._module_config:
            return self._module_config.is_enabled('alerts')
        return True

    def _ensure_table(self):
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS alert_engine_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT,
                    data_json TEXT DEFAULT '{}',
                    leida INTEGER DEFAULT 0,
                    sucursal_id INTEGER DEFAULT 1,
                    fecha TEXT DEFAULT (datetime('now'))
                )
            """)
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  API principal
    # ══════════════════════════════════════════════════════════════════════════

    def run_all_checks(self, sucursal_id: int = 0) -> List[Dict]:
        """Ejecuta TODAS las verificaciones. Retorna alertas generadas."""
        if not self.enabled:
            return []

        self._alerts = []

        # Checks existentes (operativos)
        if self.alertas:
            try:
                self.alertas.run_checks()
            except Exception:
                pass

        # Checks financieros (Fase 3 → Fase 4)
        self._check_financial(sucursal_id)

        # Checks de inventario avanzados
        self._check_inventory()

        # Checks de fidelización
        self._check_loyalty()

        # Checks de RRHH
        self._check_hr()

        # Checks operativos
        self._check_operations()

        # Checks de ventas
        self._check_sales()

        # Persistir alertas nuevas
        for a in self._alerts:
            self._persist(a, sucursal_id)

        # Enviar críticas por WhatsApp
        criticas = [a for a in self._alerts if a.severity == Severity.CRITICAL]
        if criticas:
            self._notify_whatsapp(criticas, sucursal_id)

        result = [a.to_dict() for a in self._alerts]
        logger.info("AlertEngine: %d alertas (%d críticas)",
                     len(result), len(criticas))
        return result

    def get_alerts(self, severity: str = "", category: str = "",
                   limit: int = 50) -> List[Dict]:
        """Obtiene alertas del log, filtradas opcionalmente."""
        q = "SELECT * FROM alert_engine_log WHERE 1=1"
        params = []
        if severity:
            q += " AND severity=?"
            params.append(severity)
        if category:
            q += " AND category=?"
            params.append(category)
        q += " ORDER BY fecha DESC LIMIT ?"
        params.append(limit)
        try:
            rows = self.db.execute(q, params).fetchall()
            return [dict(zip(
                ["id", "category", "severity", "title", "message",
                 "data_json", "leida", "sucursal_id", "fecha"],
                r)) for r in rows]
        except Exception:
            return []

    def get_unread(self, limit: int = 20) -> List[Dict]:
        return self.get_alerts_filtered(leida=False, limit=limit)

    def get_alerts_filtered(self, leida: bool = None, limit: int = 50) -> List[Dict]:
        q = "SELECT * FROM alert_engine_log"
        params = []
        if leida is not None:
            q += " WHERE leida=?"
            params.append(0 if not leida else 1)
        q += " ORDER BY fecha DESC LIMIT ?"
        params.append(limit)
        try:
            rows = self.db.execute(q, params).fetchall()
            return [dict(zip(
                ["id", "category", "severity", "title", "message",
                 "data_json", "leida", "sucursal_id", "fecha"],
                r)) for r in rows]
        except Exception:
            return []

    def mark_read(self, alert_id: int = 0):
        if alert_id:
            self.db.execute("UPDATE alert_engine_log SET leida=1 WHERE id=?",
                            (alert_id,))
        else:
            self.db.execute("UPDATE alert_engine_log SET leida=1")
        try:
            self.db.commit()
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  Checks FINANCIEROS (Tesorería Central)
    # ══════════════════════════════════════════════════════════════════════════

    def _check_financial(self, sucursal_id: int = 0):
        if not self.treasury:
            return
        try:
            k = self.treasury.kpis_financieros(sucursal_id=sucursal_id)
        except Exception:
            return

        # ── Operando con pérdida ──────────────────────────────────────
        if k["utilidad_neta"] < 0:
            self._emit(AlertCategory.FINANCIAL, Severity.CRITICAL,
                "Operando con pérdida",
                f"Utilidad neta: ${k['utilidad_neta']:,.2f}\n"
                f"Ingresos: ${k['ingresos']:,.2f} vs Egresos: "
                f"${k['egresos']['total_egresos']:,.2f}",
                {"utilidad": k["utilidad_neta"], "ingresos": k["ingresos"]})

        # ── Margen neto muy bajo ──────────────────────────────────────
        elif 0 < k["margen_neto_pct"] < 5:
            self._emit(AlertCategory.FINANCIAL, Severity.HIGH,
                "Margen neto peligrosamente bajo",
                f"Margen: {k['margen_neto_pct']:.1f}% — "
                f"se recomienda mínimo 10%",
                {"margen": k["margen_neto_pct"]})

        # ── Capital bajo (< 2 meses de operación) ─────────────────────
        if 0 < k["burn_rate_meses"] < 2:
            self._emit(AlertCategory.FINANCIAL, Severity.CRITICAL,
                "Capital crítico",
                f"Capital disponible para solo {k['burn_rate_meses']:.1f} meses.\n"
                f"Disponible: ${k['capital_disponible']:,.2f}",
                {"burn_rate": k["burn_rate_meses"],
                 "capital": k["capital_disponible"]})
        elif 2 <= k.get("burn_rate_meses", 99) < 4:
            self._emit(AlertCategory.FINANCIAL, Severity.HIGH,
                "Capital limitado",
                f"Quedan ~{k['burn_rate_meses']:.1f} meses de capital.",
                {"burn_rate": k["burn_rate_meses"]})

        # ── ROI negativo ──────────────────────────────────────────────
        if k["capital_invertido"] > 0 and k["roi_pct"] < -10:
            self._emit(AlertCategory.FINANCIAL, Severity.HIGH,
                "ROI negativo",
                f"Retorno sobre inversión: {k['roi_pct']:.1f}%\n"
                f"La inversión no se está recuperando.",
                {"roi": k["roi_pct"]})

        # ── CXP vencidas ──────────────────────────────────────────────
        cxp_vencidas = self._q(
            "SELECT COUNT(*) FROM accounts_payable "
            "WHERE status IN ('pendiente','parcial') "
            "AND due_date IS NOT NULL AND due_date < date('now')")
        if cxp_vencidas > 0:
            self._emit(AlertCategory.FINANCIAL, Severity.HIGH,
                f"{int(cxp_vencidas)} cuentas por pagar vencidas",
                "Revisar pagos pendientes a proveedores.",
                {"cxp_vencidas": int(cxp_vencidas)})

        # ── Gastos fijos > 30% de ingresos ────────────────────────────
        if k["ingresos"] > 0:
            ratio_fijos = k["egresos"]["gastos_fijos"] / k["ingresos"] * 100
            if ratio_fijos > 30:
                self._emit(AlertCategory.FINANCIAL, Severity.MEDIUM,
                    "Gastos fijos altos",
                    f"Gastos fijos = {ratio_fijos:.1f}% de ingresos.\n"
                    f"Fijos: ${k['egresos']['gastos_fijos']:,.2f} vs "
                    f"Ingresos: ${k['ingresos']:,.2f}",
                    {"ratio": ratio_fijos})

    # ══════════════════════════════════════════════════════════════════════════
    #  Checks de INVENTARIO
    # ══════════════════════════════════════════════════════════════════════════

    def _check_inventory(self):
        # ── Merma alta (>5% de compras) ───────────────────────────────
        try:
            hoy = date.today()
            df = date(hoy.year, hoy.month, 1).isoformat()
            merma = self._q(
                "SELECT COALESCE(SUM(cantidad*COALESCE(costo_unitario,0)),0) "
                "FROM merma WHERE DATE(fecha) BETWEEN ? AND ?",
                [df, hoy.isoformat()])
            compras = self._q(
                "SELECT COALESCE(SUM(costo_total),0) FROM compras_inventariables "
                "WHERE DATE(fecha) BETWEEN ? AND ?",
                [df, hoy.isoformat()])
            if compras > 0 and merma > 0:
                pct_merma = merma / compras * 100
                if pct_merma > 5:
                    sev = Severity.CRITICAL if pct_merma > 10 else Severity.HIGH
                    self._emit(AlertCategory.INVENTORY, sev,
                        "Merma excesiva",
                        f"Merma = {pct_merma:.1f}% de compras "
                        f"(${merma:,.2f} de ${compras:,.2f})",
                        {"pct_merma": pct_merma, "merma": merma})
        except Exception:
            pass

        # ── Productos sin movimiento (30 días) ────────────────────────
        try:
            sin_mov = self._q(
                "SELECT COUNT(*) FROM productos p "
                "WHERE p.activo=1 AND p.existencia > 0 "
                "AND p.id NOT IN ("
                "  SELECT DISTINCT producto_id FROM detalles_venta dv "
                "  JOIN ventas v ON v.id=dv.venta_id "
                "  WHERE v.fecha > datetime('now','-30 days'))")
            if sin_mov > 5:
                self._emit(AlertCategory.INVENTORY, Severity.MEDIUM,
                    f"{int(sin_mov)} productos sin venta en 30 días",
                    "Revisar inventario para posible liquidación o merma.",
                    {"sin_movimiento": int(sin_mov)})
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  Checks de FIDELIZACIÓN
    # ══════════════════════════════════════════════════════════════════════════

    def _check_loyalty(self):
        if not self.loyalty:
            return
        try:
            pasivo = self.loyalty.pasivo_financiero()
            valor = pasivo.get("valor_monetario", 0)

            # Pasivo de fidelización > $5,000
            if valor > 5000:
                sev = Severity.CRITICAL if valor > 20000 else (
                    Severity.HIGH if valor > 10000 else Severity.MEDIUM)
                self._emit(AlertCategory.LOYALTY, sev,
                    "Pasivo de fidelización alto",
                    f"Estrellas emitidas representan ${valor:,.2f} en obligaciones.\n"
                    f"Total estrellas: {pasivo.get('total_estrellas', 0):,}",
                    {"pasivo": valor})

            # Ratio pasivo vs ingresos mensuales
            if self.treasury:
                try:
                    ingresos = self.treasury.kpis_financieros().get("ingresos", 0)
                    if ingresos > 0 and valor > ingresos * 0.1:
                        self._emit(AlertCategory.LOYALTY, Severity.HIGH,
                            "Costo fidelización > 10% de ingresos",
                            f"Pasivo: ${valor:,.2f} vs Ingresos: ${ingresos:,.2f}\n"
                            f"Considerar reducir tasa de acumulación.",
                            {"ratio": valor / ingresos * 100})
                except Exception:
                    pass
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  Checks de RRHH
    # ══════════════════════════════════════════════════════════════════════════

    def _check_hr(self):
        try:
            hoy = date.today()
            df = date(hoy.year, hoy.month, 1).isoformat()
            nomina = self._q(
                "SELECT COALESCE(SUM(total),0) FROM nomina_pagos "
                "WHERE estado='pagado' AND DATE(fecha) BETWEEN ? AND ?",
                [df, hoy.isoformat()])
            ingresos = self._q(
                "SELECT COALESCE(SUM(total),0) FROM ventas "
                "WHERE estado='completada' AND DATE(fecha) BETWEEN ? AND ?",
                [df, hoy.isoformat()])

            if ingresos > 0 and nomina > 0:
                ratio = nomina / ingresos * 100
                if ratio > 35:
                    sev = Severity.CRITICAL if ratio > 50 else Severity.HIGH
                    self._emit(AlertCategory.HR, sev,
                        "Costo RRHH alto vs ingresos",
                        f"Nómina = {ratio:.1f}% de ingresos.\n"
                        f"Nómina: ${nomina:,.2f} vs Ingresos: ${ingresos:,.2f}\n"
                        f"Se recomienda máximo 25-30%.",
                        {"ratio": ratio, "nomina": nomina})
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  Checks OPERATIVOS (cancelaciones, ajustes)
    # ══════════════════════════════════════════════════════════════════════════

    def _check_operations(self):
        # ── Cancelaciones frecuentes hoy ──────────────────────────────
        try:
            cancelaciones = self._q(
                "SELECT COUNT(*) FROM ventas "
                "WHERE estado='cancelada' AND DATE(fecha)=DATE('now')")
            ventas_hoy = self._q(
                "SELECT COUNT(*) FROM ventas WHERE DATE(fecha)=DATE('now')")
            if ventas_hoy > 5 and cancelaciones > 0:
                ratio = cancelaciones / ventas_hoy * 100
                if ratio > 10:
                    self._emit(AlertCategory.OPERATIONS, Severity.HIGH,
                        f"{int(cancelaciones)} cancelaciones hoy ({ratio:.0f}%)",
                        "Verificar posible mal uso del sistema.",
                        {"cancelaciones": int(cancelaciones),
                         "ventas": int(ventas_hoy)})
        except Exception:
            pass

        # ── Ajustes de inventario sospechosos ─────────────────────────
        try:
            ajustes = self._q(
                "SELECT COUNT(*) FROM ajustes_inventario "
                "WHERE DATE(fecha)=DATE('now')")
            if ajustes > 5:
                self._emit(AlertCategory.OPERATIONS, Severity.MEDIUM,
                    f"{int(ajustes)} ajustes de inventario hoy",
                    "Revisar motivos de los ajustes.",
                    {"ajustes": int(ajustes)})
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  Checks de VENTAS
    # ══════════════════════════════════════════════════════════════════════════

    def _check_sales(self):
        # ── Caída de ventas vs semana pasada ──────────────────────────
        try:
            hoy = date.today()
            ventas_hoy = self._q(
                "SELECT COALESCE(SUM(total),0) FROM ventas "
                "WHERE estado='completada' AND DATE(fecha)=?",
                [hoy.isoformat()])
            dia_semana_pasada = (hoy - timedelta(days=7)).isoformat()
            ventas_semana_pasada = self._q(
                "SELECT COALESCE(SUM(total),0) FROM ventas "
                "WHERE estado='completada' AND DATE(fecha)=?",
                [dia_semana_pasada])

            if ventas_semana_pasada > 1000 and ventas_hoy > 0:
                caida = (1 - ventas_hoy / ventas_semana_pasada) * 100
                if caida > 40:
                    sev = Severity.HIGH if caida > 60 else Severity.MEDIUM
                    self._emit(AlertCategory.SALES, sev,
                        f"Ventas -{caida:.0f}% vs misma día semana pasada",
                        f"Hoy: ${ventas_hoy:,.2f} vs "
                        f"Semana pasada: ${ventas_semana_pasada:,.2f}",
                        {"caida_pct": caida})
        except Exception:
            pass

        # ── Ticket promedio muy bajo ──────────────────────────────────
        try:
            hoy_iso = date.today().isoformat()
            avg = self._q(
                "SELECT AVG(total) FROM ventas "
                "WHERE estado='completada' AND DATE(fecha)=? AND total > 0",
                [hoy_iso])
            avg_mes = self._q(
                "SELECT AVG(total) FROM ventas "
                "WHERE estado='completada' AND total > 0 "
                "AND fecha > datetime('now','-30 days')")
            if avg_mes > 0 and avg > 0 and avg < avg_mes * 0.5:
                self._emit(AlertCategory.SALES, Severity.MEDIUM,
                    "Ticket promedio bajo",
                    f"Promedio hoy: ${avg:.2f} vs mes: ${avg_mes:.2f}",
                    {"avg_hoy": avg, "avg_mes": avg_mes})
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  Internals
    # ══════════════════════════════════════════════════════════════════════════

    def _emit(self, category, severity, title, message, data=None):
        self._alerts.append(Alert(category, severity, title, message, data))

    def _persist(self, alert: Alert, sucursal_id: int = 1):
        try:
            self.db.execute(
                "INSERT INTO alert_engine_log "
                "(category, severity, title, message, data_json, sucursal_id) "
                "VALUES (?,?,?,?,?,?)",
                (alert.category, alert.severity, alert.title,
                 alert.message, json.dumps(alert.data or {}, default=str),
                 sucursal_id))
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception:
            pass
        # Publicar ALERT_CRITICAL al EventBus para severidades high/critical
        if self._bus and alert.severity in (Severity.HIGH, Severity.CRITICAL):
            try:
                from core.events.event_bus import ALERT_CRITICAL
                self._bus.publish(ALERT_CRITICAL, {
                    "category":    alert.category,
                    "severity":    alert.severity,
                    "title":       alert.title,
                    "message":     alert.message,
                    "data":        alert.data or {},
                    "sucursal_id": sucursal_id,
                }, async_=True)
            except Exception:
                pass

    def _notify_whatsapp(self, alerts: List[Alert], sucursal_id: int):
        """Envía alertas críticas al staff por WhatsApp."""
        try:
            # Obtener teléfonos de gerentes
            rows = self.db.execute(
                "SELECT telefono FROM empleados "
                "WHERE (rol='gerente' OR rol='admin') AND activo=1 "
                "AND telefono IS NOT NULL").fetchall()
            phones = [r[0] for r in rows if r[0]]
            if not phones:
                return

            texto = "🚨 *ALERTAS CRÍTICAS — SPJ POS*\n\n"
            for a in alerts[:5]:
                texto += f"{SEVERITY_EMOJI[a.severity]} *{a.title}*\n{a.message}\n\n"

            # Intentar enviar via WhatsApp service del ERP
            try:
                from integrations.whatsapp_service import WhatsAppService
                wa = WhatsAppService(self.db)
                for phone in phones[:3]:
                    wa.send_message(phone, texto)
            except Exception:
                pass
        except Exception as e:
            logger.debug("WA notify: %s", e)

    def _q(self, sql: str, params: list = None) -> float:
        try:
            row = self.db.execute(sql, params or []).fetchone()
            return float(row[0]) if row and row[0] else 0.0
        except Exception:
            return 0.0
