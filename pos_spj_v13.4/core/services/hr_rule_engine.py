# core/services/hr_rule_engine.py — SPJ POS v13.30 — FASE 11
"""
HRRuleEngine — Motor de reglas laborales inteligente.

REGLAS IMPLEMENTADAS:
    1. Máximo 6 días laborables consecutivos (NOM-035)
    2. Descanso obligatorio — programa automáticamente el día de descanso
    3. Rotación de descansos — evita que toda la sucursal descanse el mismo día
    4. Cobertura mínima — valida que siempre haya al menos 1 empleado por turno
    5. Nómina vencida — detecta empleados sin pago en el periodo corriente
    6. Horas extra — detecta cuando se supera el límite semanal (48 hrs LFT)

EVENTOS PUBLICADOS:
    EMPLOYEE_OVERWORK   — días consecutivos > MAX_CONSECUTIVE_DAYS
    EMPLOYEE_REST_DAY   — descanso programado
    PAYROLL_GENERATED   — nómina procesada y auditada
    PAYROLL_DUE         — nómina próxima a vencer o vencida

USO:
    engine = container.hr_rule_engine
    engine.auditar_sucursal(sucursal_id=1)
    engine.verificar_dias_consecutivos(empleado_id=5)
    engine.auditar_nomina_pendiente()
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any

logger = logging.getLogger("spj.hr_rule_engine")

# ── Constantes laborales (LFT México) ─────────────────────────────────────────
MAX_CONSECUTIVE_DAYS = 6    # Art. 69 LFT: mínimo 1 día descanso por cada 6
MAX_WEEKLY_HOURS     = 48   # Art. 61 LFT: límite semanal jornada diurna
MIN_COVERAGE         = 1    # empleados mínimos activos por sucursal por turno
PAYROLL_PERIOD_DAYS  = 7    # frecuencia de pago semanal (configurable)


class HRRuleEngine:
    """
    Motor de reglas laborales — valida cumplimiento NOM-035 / LFT.
    No ejecuta acciones de nómina, solo detecta y publica eventos.
    Integrar con RRHHService para trigger automático.
    """

    def __init__(self, db_conn, module_config=None):
        self.db = db_conn
        self._module_config = module_config
        self._bus = None
        try:
            from core.events.event_bus import get_bus
            self._bus = get_bus()
        except Exception:
            pass
        # Detectar tabla de empleados (personal vs empleados según schema)
        self._emp_table = self._detect_emp_table()
        self._ensure_tables()

    @property
    def enabled(self) -> bool:
        if self._module_config:
            return self._module_config.is_enabled("rrhh")
        return True  # Activo por defecto — reglas laborales no se desactivan

    # ══════════════════════════════════════════════════════════════════════════
    #  API principal
    # ══════════════════════════════════════════════════════════════════════════

    def auditar_sucursal(self, sucursal_id: int,
                         fecha: Optional[str] = None) -> Dict[str, Any]:
        """
        Auditoría completa de reglas laborales para una sucursal.
        Retorna informe con violaciones, descansos sugeridos y cobertura.
        """
        fecha_obj = _parse_date(fecha) or date.today()
        empleados = self._get_empleados(sucursal_id)

        overwork_list: List[Dict]     = []
        rest_needed:   List[Dict]     = []
        cobertura_ok:  bool           = True

        for emp in empleados:
            consecutivos = self._dias_consecutivos(emp["id"], fecha_obj)
            if consecutivos >= MAX_CONSECUTIVE_DAYS:
                overwork_list.append({
                    "empleado_id":      emp["id"],
                    "nombre":           emp["nombre"],
                    "dias_consecutivos": consecutivos,
                    "sucursal_id":      sucursal_id,
                })
                # Publicar evento de sobrecarga
                self._publish_overwork(emp, consecutivos, sucursal_id)
                # Calcular y publicar día de descanso sugerido
                descanso = self._sugerir_descanso(emp["id"], fecha_obj,
                                                   sucursal_id, empleados)
                if descanso:
                    rest_needed.append(descanso)

        # Validar cobertura mínima
        activos_hoy = self._empleados_activos_hoy(sucursal_id, fecha_obj)
        en_descanso = sum(1 for r in rest_needed
                          if r.get("fecha_descanso") == fecha_obj.isoformat())
        if (activos_hoy - en_descanso) < MIN_COVERAGE:
            cobertura_ok = False
            logger.warning("Cobertura insuficiente en sucursal %d para %s",
                           sucursal_id, fecha_obj)

        resultado = {
            "sucursal_id":       sucursal_id,
            "fecha":             fecha_obj.isoformat(),
            "empleados_total":   len(empleados),
            "activos_hoy":       activos_hoy,
            "overwork":          overwork_list,
            "descansos_sugeridos": rest_needed,
            "cobertura_ok":      cobertura_ok,
        }
        self._persist_auditoria(sucursal_id, fecha_obj, resultado)
        return resultado

    def verificar_dias_consecutivos(self, empleado_id: int,
                                     fecha: Optional[str] = None) -> Dict:
        """
        Verifica días laborales consecutivos del empleado.
        Retorna {'empleado_id', 'dias_consecutivos', 'requiere_descanso', 'alerta'}.
        """
        fecha_obj = _parse_date(fecha) or date.today()
        consecutivos = self._dias_consecutivos(empleado_id, fecha_obj)
        requiere = consecutivos >= MAX_CONSECUTIVE_DAYS

        emp = self._get_empleado(empleado_id)
        if requiere and emp:
            suc_id = emp.get("sucursal_id", 0)
            self._publish_overwork(emp, consecutivos, suc_id)

        return {
            "empleado_id":      empleado_id,
            "dias_consecutivos": consecutivos,
            "max_permitido":    MAX_CONSECUTIVE_DAYS,
            "requiere_descanso": requiere,
            "alerta":           "OVERWORK" if requiere else "OK",
        }

    def programar_descanso(self, empleado_id: int,
                            fecha_descanso: Optional[str] = None,
                            sucursal_id: int = 0) -> Dict:
        """
        Registra un día de descanso para el empleado y publica evento.
        Si no se provee fecha_descanso, calcula la más conveniente.
        """
        emp = self._get_empleado(empleado_id)
        if not emp:
            return {"ok": False, "error": "Empleado no encontrado"}

        fecha_obj = _parse_date(fecha_descanso) or (date.today() + timedelta(days=1))
        suc_id    = sucursal_id or emp.get("sucursal_id", 0)

        # Registrar en tabla de asistencias como descanso
        try:
            self.db.execute("""
                INSERT OR IGNORE INTO asistencias
                    (personal_id, fecha, estado, horas_trabajadas)
                VALUES (?, ?, 'DESCANSO', 0.0)
            """, (empleado_id, fecha_obj.isoformat()))
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug("programar_descanso DB: %s", e)

        # Publicar evento
        self._publish_rest_day(emp, fecha_obj, suc_id)

        return {
            "ok":             True,
            "empleado_id":    empleado_id,
            "nombre":         emp.get("nombre", ""),
            "fecha_descanso": fecha_obj.isoformat(),
            "sucursal_id":    suc_id,
        }

    def auditar_nomina_pendiente(self,
                                  dias_aviso: int = 2) -> List[Dict]:
        """
        Detecta empleados cuyo periodo de pago está vencido o por vencer.
        Publica PAYROLL_DUE para cada caso.
        """
        hoy = date.today()
        pendientes: List[Dict] = []

        tbl = getattr(self, "_emp_table", "personal")
        try:
            rows = self.db.execute(f"""
                SELECT p.id, p.nombre, p.apellidos, p.sucursal_id,
                       MAX(np.fecha) AS ultimo_pago
                FROM {tbl} p
                LEFT JOIN nomina_pagos np
                       ON np.empleado_id = p.id AND np.estado = 'pagado'
                WHERE p.activo = 1
                GROUP BY p.id
            """).fetchall()
        except Exception as e:
            logger.debug("auditar_nomina: %s", e)
            return []

        for r in rows:
            emp_id, nombre, apellidos, suc_id, ultimo_pago = (
                r[0], r[1], r[2], r[3], r[4])
            nombre_completo = f"{nombre} {apellidos or ''}".strip()

            if ultimo_pago:
                ultimo_dt = _parse_date(ultimo_pago[:10])
                if not ultimo_dt:
                    continue
                dias_transcurridos = (hoy - ultimo_dt).days
                dias_faltantes = PAYROLL_PERIOD_DAYS - dias_transcurridos
            else:
                # Nunca ha recibido pago
                dias_faltantes = -PAYROLL_PERIOD_DAYS

            if dias_faltantes <= dias_aviso:
                info = {
                    "empleado_id":      emp_id,
                    "nombre":           nombre_completo,
                    "sucursal_id":      suc_id or 0,
                    "ultimo_pago":      ultimo_pago,
                    "dias_vencimiento": dias_faltantes,
                    "vencida":          dias_faltantes < 0,
                }
                pendientes.append(info)
                self._publish_payroll_due(info)

        return pendientes

    def verificar_horas_semanales(self, empleado_id: int,
                                   semana_inicio: Optional[str] = None) -> Dict:
        """
        Verifica si el empleado supera MAX_WEEKLY_HOURS en la semana.
        """
        hoy = date.today()
        lunes = hoy - timedelta(days=hoy.weekday())
        df = _parse_date(semana_inicio) or lunes
        dt = df + timedelta(days=6)

        try:
            row = self.db.execute("""
                SELECT COALESCE(SUM(horas_trabajadas), 0)
                FROM asistencias
                WHERE personal_id = ?
                  AND estado IN ('PRESENTE', 'RETARDO')
                  AND fecha BETWEEN ? AND ?
            """, (empleado_id, df.isoformat(), dt.isoformat())).fetchone()
            horas = float(row[0]) if row else 0.0
        except Exception:
            horas = 0.0

        excede = horas > MAX_WEEKLY_HOURS
        horas_extra = max(0.0, horas - MAX_WEEKLY_HOURS)

        return {
            "empleado_id":  empleado_id,
            "semana_inicio": df.isoformat(),
            "semana_fin":    dt.isoformat(),
            "horas_totales": round(horas, 1),
            "max_legal":     MAX_WEEKLY_HOURS,
            "horas_extra":   round(horas_extra, 1),
            "excede_limite": excede,
        }

    def validar_cobertura(self, sucursal_id: int,
                           fecha: Optional[str] = None) -> Dict:
        """
        Valida que la sucursal tenga cobertura mínima para la fecha dada.
        """
        fecha_obj = _parse_date(fecha) or date.today()
        activos = self._empleados_activos_hoy(sucursal_id, fecha_obj)
        ok = activos >= MIN_COVERAGE

        return {
            "sucursal_id":   sucursal_id,
            "fecha":         fecha_obj.isoformat(),
            "empleados_activos": activos,
            "cobertura_minima":  MIN_COVERAGE,
            "cobertura_ok":      ok,
        }

    def registrar_pago_auditado(self, empleado_id: int, nombre: str,
                                 periodo: str, total: float,
                                 sucursal_id: int = 0) -> None:
        """
        Llamado desde RRHHService al completar un pago.
        Registra en audit log y publica PAYROLL_GENERATED.
        """
        self._persist_pago(empleado_id, nombre, periodo, total, sucursal_id)
        if self._bus:
            try:
                from core.events.event_bus import PAYROLL_GENERATED
                self._bus.publish(PAYROLL_GENERATED, {
                    "empleado_id": empleado_id,
                    "nombre":      nombre,
                    "periodo":     periodo,
                    "total":       total,
                    "sucursal_id": sucursal_id,
                }, async_=True)
            except Exception:
                pass

    # ══════════════════════════════════════════════════════════════════════════
    #  Internals — Cálculos
    # ══════════════════════════════════════════════════════════════════════════

    def _dias_consecutivos(self, empleado_id: int, hasta: date) -> int:
        """
        Cuenta días laborales consecutivos hacia atrás desde `hasta`.
        Un día es laboral si tiene registro PRESENTE o RETARDO.
        """
        consecutivos = 0
        dia = hasta
        for _ in range(MAX_CONSECUTIVE_DAYS + 5):  # límite seguro
            try:
                row = self.db.execute("""
                    SELECT COUNT(*) FROM asistencias
                    WHERE personal_id = ?
                      AND fecha = ?
                      AND estado IN ('PRESENTE', 'RETARDO')
                """, (empleado_id, dia.isoformat())).fetchone()
                if row and row[0] > 0:
                    consecutivos += 1
                    dia -= timedelta(days=1)
                else:
                    break
            except Exception:
                break
        return consecutivos

    def _sugerir_descanso(self, empleado_id: int, hoy: date,
                           sucursal_id: int,
                           todos_empleados: List[Dict]) -> Optional[Dict]:
        """
        Sugiere el próximo día de descanso evitando concentrar múltiples descansos.
        """
        emp = self._get_empleado(empleado_id)
        if not emp:
            return None

        # Buscar el primer día donde no haya más del 50% de empleados descansando
        for delta in range(1, 8):
            candidato = hoy + timedelta(days=delta)
            descansando = self._empleados_con_descanso(sucursal_id, candidato)
            total = len(todos_empleados)
            if descansando < total * 0.5:
                self._publish_rest_day(emp, candidato, sucursal_id)
                return {
                    "empleado_id":    empleado_id,
                    "nombre":         emp.get("nombre", ""),
                    "fecha_descanso": candidato.isoformat(),
                    "sucursal_id":    sucursal_id,
                }
        return None

    def _empleados_con_descanso(self, sucursal_id: int, fecha: date) -> int:
        """Cuenta empleados programados para descansar en una fecha."""
        tbl = getattr(self, "_emp_table", "personal")
        try:
            row = self.db.execute(f"""
                SELECT COUNT(*) FROM asistencias a
                JOIN {tbl} p ON p.id = a.personal_id
                WHERE p.sucursal_id = ?
                  AND a.fecha = ?
                  AND a.estado = 'DESCANSO'
            """, (sucursal_id, fecha.isoformat())).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    def _empleados_activos_hoy(self, sucursal_id: int, fecha: date) -> int:
        """Cuenta empleados activos (no en descanso) en la sucursal para una fecha."""
        tbl = getattr(self, "_emp_table", "personal")
        try:
            row = self.db.execute(f"""
                SELECT COUNT(*) FROM {tbl} p
                WHERE p.sucursal_id = ? AND p.activo = 1
                  AND p.id NOT IN (
                      SELECT personal_id FROM asistencias
                      WHERE fecha = ? AND estado = 'DESCANSO'
                  )
            """, (sucursal_id, fecha.isoformat())).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return 0

    # ══════════════════════════════════════════════════════════════════════════
    #  Internals — DB helpers
    # ══════════════════════════════════════════════════════════════════════════

    # ── Detección dinámica de tabla de empleados ─────────────────────────────
    # El schema puede usar 'personal' (v13) o 'empleados' (legacy). Detectamos
    # en __init__ cuál existe y la usamos de forma consistente.

    def _detect_emp_table(self) -> str:
        """Detecta qué tabla existe: 'personal' (preferida) o 'empleados' (legacy)."""
        if not self.db:
            return "personal"
        for tbl in ("personal", "empleados"):
            try:
                self.db.execute(f"SELECT 1 FROM {tbl} LIMIT 1")
                return tbl
            except Exception:
                continue
        return "personal"  # fallback — error se mostrará en tiempo de consulta

    def _get_empleados(self, sucursal_id: int) -> List[Dict]:
        tbl = getattr(self, "_emp_table", "personal")
        try:
            rows = self.db.execute(f"""
                SELECT id, nombre, apellidos, sucursal_id
                FROM {tbl} WHERE sucursal_id = ? AND activo = 1
            """, (sucursal_id,)).fetchall()
            return [{"id": r[0], "nombre": f"{r[1]} {r[2] or ''}".strip(),
                     "sucursal_id": r[3]} for r in rows]
        except Exception:
            return []

    def _get_empleado(self, empleado_id: int) -> Optional[Dict]:
        tbl = getattr(self, "_emp_table", "personal")
        try:
            row = self.db.execute(f"""
                SELECT id, nombre, apellidos, sucursal_id
                FROM {tbl} WHERE id = ?
            """, (empleado_id,)).fetchone()
            if row:
                return {"id": row[0],
                        "nombre": f"{row[1]} {row[2] or ''}".strip(),
                        "sucursal_id": row[3]}
        except Exception:
            pass
        return None

    def _ensure_tables(self) -> None:
        if not self.db:
            return
        try:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS hr_auditoria_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    sucursal_id INTEGER NOT NULL,
                    fecha       TEXT    NOT NULL,
                    overwork_count INTEGER DEFAULT 0,
                    descansos_sugeridos INTEGER DEFAULT 0,
                    cobertura_ok INTEGER DEFAULT 1,
                    payload     TEXT    DEFAULT '{}',
                    created_at  TEXT    DEFAULT (datetime('now'))
                )
            """)
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS hr_pago_log (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    empleado_id INTEGER NOT NULL,
                    nombre      TEXT    DEFAULT '',
                    periodo     TEXT    DEFAULT '',
                    total       REAL    DEFAULT 0,
                    sucursal_id INTEGER DEFAULT 0,
                    created_at  TEXT    DEFAULT (datetime('now'))
                )
            """)
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception:
            pass

    def _persist_auditoria(self, sucursal_id: int, fecha: date,
                            resultado: Dict) -> None:
        if not self.db:
            return
        import json
        try:
            self.db.execute("""
                INSERT INTO hr_auditoria_log
                    (sucursal_id, fecha, overwork_count,
                     descansos_sugeridos, cobertura_ok, payload)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                sucursal_id,
                fecha.isoformat(),
                len(resultado.get("overwork", [])),
                len(resultado.get("descansos_sugeridos", [])),
                1 if resultado.get("cobertura_ok") else 0,
                json.dumps(resultado, default=str)[:3000],
            ))
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception:
            pass

    def _persist_pago(self, empleado_id: int, nombre: str,
                       periodo: str, total: float, sucursal_id: int) -> None:
        if not self.db:
            return
        try:
            self.db.execute("""
                INSERT INTO hr_pago_log (empleado_id, nombre, periodo, total, sucursal_id)
                VALUES (?, ?, ?, ?, ?)
            """, (empleado_id, nombre[:200], periodo[:100], total, sucursal_id))
            try:
                self.db.commit()
            except Exception:
                pass
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════════════
    #  Internals — Publicación de eventos
    # ══════════════════════════════════════════════════════════════════════════

    def _publish_overwork(self, emp: Dict, dias: int, sucursal_id: int) -> None:
        if not self._bus:
            return
        try:
            from core.events.event_bus import EMPLOYEE_OVERWORK
            self._bus.publish(EMPLOYEE_OVERWORK, {
                "empleado_id":      emp["id"],
                "nombre":           emp.get("nombre", ""),
                "dias_consecutivos": dias,
                "max_permitido":    MAX_CONSECUTIVE_DAYS,
                "sucursal_id":      sucursal_id,
            }, async_=True)
        except Exception:
            pass

    def _publish_rest_day(self, emp: Dict, fecha: date, sucursal_id: int) -> None:
        if not self._bus:
            return
        try:
            from core.events.event_bus import EMPLOYEE_REST_DAY
            self._bus.publish(EMPLOYEE_REST_DAY, {
                "empleado_id":   emp["id"],
                "nombre":        emp.get("nombre", ""),
                "fecha_descanso": fecha.isoformat(),
                "sucursal_id":   sucursal_id,
            }, async_=True)
        except Exception:
            pass

    def _publish_payroll_due(self, info: Dict) -> None:
        if not self._bus:
            return
        try:
            from core.events.event_bus import PAYROLL_DUE
            self._bus.publish(PAYROLL_DUE, info, async_=True)
        except Exception:
            pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(s: Optional[str]) -> Optional[date]:
    """Convierte string ISO 'YYYY-MM-DD' a date, retorna None si falla."""
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None
