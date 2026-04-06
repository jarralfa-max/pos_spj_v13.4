# migrations/standalone/049_v134_intelligent_erp.py
# ── FASE 13 — Migración: tablas del ERP Inteligente v13.4 ────────────────────
#
# Crea las tablas persistentes introducidas en FASES 1-12:
#   • module_toggles    — toggles de módulos (ModuleConfig / FASE 1)
#   • decision_log      — sugerencias persistidas (DecisionEngine / FASE 5)
#   • hr_auditoria_log  — auditorías laborales (HRRuleEngine / FASE 11)
#   • hr_pago_log       — registros de nómina auditada (HRRuleEngine / FASE 11)
#
# IDEMPOTENTE: todas las sentencias usan IF NOT EXISTS / OR IGNORE.

import logging

logger = logging.getLogger("spj.migrations.049")


def run(conn) -> None:
    """Aplica migración 049 — tablas ERP inteligente v13.4."""

    # ── module_toggles ────────────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS module_toggles (
            clave       TEXT    PRIMARY KEY,
            activo      INTEGER DEFAULT 1,
            descripcion TEXT    DEFAULT ''
        )
    """)

    # Defaults para los toggles del spec (INSERT OR IGNORE — no pisa valores existentes)
    defaults = [
        ("printing_enabled",             1),
        ("loyalty_enabled",              1),
        ("finance_enabled",              1),
        ("treasury_central_enabled",     0),
        ("alerts_enabled",               1),
        ("decisions_enabled",            0),
        ("forecasting_enabled",          1),
        ("simulation_enabled",           0),
        ("ai_enabled",                   0),
        ("franchise_mode_enabled",       0),
        ("whatsapp_integration_enabled", 0),
        ("rrhh_enabled",                 1),
    ]
    for clave, activo in defaults:
        conn.execute(
            "INSERT OR IGNORE INTO module_toggles(clave, activo) VALUES(?, ?)",
            (clave, activo),
        )

    # ── decision_log ──────────────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS decision_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo            TEXT    NOT NULL,
            prioridad       TEXT    NOT NULL DEFAULT 'normal',
            titulo          TEXT    NOT NULL,
            detalle         TEXT    DEFAULT '',
            impacto_est     TEXT    DEFAULT '',
            accion          TEXT    DEFAULT '',
            sucursal_id     INTEGER DEFAULT 1,
            created_at      TEXT    DEFAULT (datetime('now'))
        )
    """)

    # Índices para consultas frecuentes
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_decision_log_prioridad
        ON decision_log(prioridad, created_at DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_decision_log_sucursal
        ON decision_log(sucursal_id, created_at DESC)
    """)

    # ── hr_auditoria_log ──────────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hr_auditoria_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado_id     INTEGER NOT NULL,
            tipo            TEXT    NOT NULL,   -- 'dias_consecutivos' | 'horas_semanales' | 'cobertura'
            detalle         TEXT    DEFAULT '',
            sucursal_id     INTEGER DEFAULT 1,
            created_at      TEXT    DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_hr_auditoria_empleado
        ON hr_auditoria_log(empleado_id, created_at DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_hr_auditoria_sucursal
        ON hr_auditoria_log(sucursal_id, created_at DESC)
    """)

    # ── hr_pago_log ───────────────────────────────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS hr_pago_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            empleado_id     INTEGER NOT NULL,
            periodo         TEXT    NOT NULL,   -- 'YYYY-WNN' o 'YYYY-MM'
            total           REAL    NOT NULL DEFAULT 0.0,
            estado          TEXT    NOT NULL DEFAULT 'auditado',  -- 'auditado' | 'pagado' | 'rechazado'
            referencia_pago INTEGER DEFAULT NULL,  -- FK a movimientos_caja si aplica
            sucursal_id     INTEGER DEFAULT 1,
            created_at      TEXT    DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_hr_pago_empleado
        ON hr_pago_log(empleado_id, periodo DESC)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_hr_pago_sucursal
        ON hr_pago_log(sucursal_id, created_at DESC)
    """)

    try:
        conn.commit()
    except Exception:
        pass

    logger.info("Migración 049: tablas ERP inteligente v13.4 creadas/verificadas.")
