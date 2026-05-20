
# migrations/engine.py — SPJ POS v12
# ── Motor de Migraciones ──────────────────────────────────────────────────────
# Ejecuta todas las migraciones en orden garantizado.
# Idempotente: usa CREATE TABLE IF NOT EXISTS y ALTER TABLE seguro.
# Registra cada migración ejecutada en la tabla schema_migrations.
import logging, sqlite3
from collections import namedtuple
logger = logging.getLogger("spj.migrations")

# Named tuple so MIGRATIONS entries have a .version attribute
_Migration = namedtuple("_Migration", ["version", "module"])

# Orden estricto de ejecución — NO reordenar
MIGRATIONS = [
    _Migration("000", "migrations.m000_base_schema"),
    _Migration("001", "migrations.m001_enterprise_ajustes"),
    _Migration("016",  "migrations.standalone.016_concurrency_events"),
    _Migration("018",  "migrations.standalone.018_sync_industrial_extension"),
    _Migration("019",  "migrations.standalone.019_margin_protection"),
    _Migration("020",  "migrations.standalone.020_system_integrity"),
    _Migration("021",  "migrations.standalone.021_db_hardening"),
    _Migration("022",  "migrations.standalone.022_industrial_hardening"),
    _Migration("023",  "migrations.standalone.023_enterprise_upgrade"),
    _Migration("024",  "migrations.standalone.024_enterprise_blocks_5_8"),
    _Migration("025",  "migrations.standalone.025_sync_batch_log"),
    _Migration("026",  "migrations.standalone.026_final_structural_hardening"),
    _Migration("027",  "migrations.standalone.027_inventory_hardening"),
    _Migration("028",  "migrations.standalone.028_sales_transaction_hardening"),
    _Migration("029",  "migrations.standalone.029_reversals_hardening"),
    _Migration("030",  "migrations.standalone.030_recetas_industriales"),   # fusionado 030a+030b
    _Migration("031",  "migrations.standalone.031_inventory_engine"),       # fusionado 031a+031b
    _Migration("032",  "migrations.standalone.032_bi_tables"),              # fusionado 032+034+meat
    _Migration("033",  "migrations.standalone.033_demand_forecast"),
    _Migration("035",  "migrations.standalone.035_finance_erp"),
    _Migration("036",  "migrations.standalone.036_whatsapp_rasa"),
    _Migration("037",  "migrations.standalone.037_product_images"),
    _Migration("038",  "migrations.standalone.038_transfer_suggestions"),
    _Migration("039",  "migrations.standalone.039_branch_products"),
    _Migration("040",  "migrations.standalone.040_qr_reception"),
    _Migration("041",  "migrations.standalone.041_notification_inbox"),
    _Migration("042",  "migrations.standalone.042_whatsapp_multicanal"),
    _Migration("043",  "migrations.standalone.043_price_history"),
    _Migration("044",  "migrations.standalone.044_cotizaciones"),
    _Migration("045",  "migrations.standalone.045_performance_indexes"),
    _Migration("046",  "migrations.standalone.046_comisiones_happy_hour"),
    _Migration("047",  "migrations.standalone.047_v13_schema"),
    _Migration("048",  "migrations.standalone.048_v131_hardening"),
    _Migration("049",  "migrations.standalone.049_v134_intelligent_erp"),  # FASE 13: tablas ERP inteligente
    _Migration("050",  "migrations.standalone.050_wa_integration"),        # FASE WA: tablas orquestación WA↔ERP
    _Migration("051",  "migrations.standalone.051_fix_kpi_snapshots"),     # FIX: kpi_snapshots faltante por error 032
    _Migration("052",  "migrations.standalone.052_financial_event_log"),  # v13.4: audit trail financiero doble entrada
    _Migration("053",  "migrations.standalone.053_meat_production_tables"),  # v13.4: tablas cárnicas huérfanas de 032
    _Migration("054",  "migrations.standalone.054_sync_improvements_orphan"),  # v13.4: columnas sync huérfanas de 048
    _Migration("055",  "migrations.standalone.055_inventario_compat"),  # v13.4: compat tabla/vista inventario
    _Migration("056",  "migrations.standalone.056_print_job_log"),      # v13.4: bitácora de impresión Fase 1
    _Migration("057",  "migrations.standalone.057_loyalty_ledger_unificado"),  # v13.4: ledger unificado fidelización Fase 2
    _Migration("058",  "migrations.standalone.058_scan_event_log"),    # v13.4: auditoría de escaneos Fase 2
    _Migration("059",  "migrations.standalone.059_plan_cuentas"),      # v13.4: plan de cuentas SAT NIF Fase 3
    _Migration("060",  "migrations.standalone.060_depreciacion_acumulada"),  # v13.4: depreciación acumulada Fase 3
    # ERP evolution — additive, non-breaking
    _Migration("061",  "migrations.standalone.061_fix_finanzas_schema"),   # ERP FASE 1: columnas finanzas hotfix
    _Migration("062",  "migrations.standalone.062_bi_analytics_tables"),   # ERP FASE 5: tablas BI analytics
    _Migration("063",  "migrations.standalone.063_audit_log_table"),       # ERP FASE 7: audit_log (inglés)
    _Migration("064",  "migrations.standalone.064_fix_missing_columns"),   # Hotfix: columnas faltantes producción
    _Migration("065",  "migrations.standalone.065_performance_indexes_views"),  # ERP FASE 8: índices + vistas BI
    _Migration("066",  "migrations.standalone.066_unificar_esquema_recetas"),  # Fase E: bridge legacy recetas ↔ product_recipes
    _Migration("067",  "migrations.standalone.067_meat_erp_improvements"),    # v13.5: trazabilidad lotes, merma_log, campos cárnicos
    _Migration("068",  "migrations.standalone.068_fix_branch_inventory_unique"),  # Fix: UNIQUE(product_id, branch_id) en branch_inventory
    _Migration("069",  "migrations.standalone.069_delivery_weight_reservation"),  # v13.5: variable-weight items + reservation columns
    _Migration("070",  "migrations.standalone.070_delivery_enterprise_lifecycle"),  # v13.30: lifecycle columns + driver cuts + indexes
    _Migration("071",  "migrations.standalone.071_compras_condicion_pago"),         # v13.4: condicion_pago + plazo_dias + moneda en compras
    _Migration("072",  "migrations.standalone.072_condicion_pago_check"),           # v13.4: backfill NULLs, enforce valid condicion_pago values
    _Migration("073",  "migrations.standalone.073_temp_purchase_drafts"),           # v13.4: DB-backed cart drafts per user/branch
    _Migration("074",  "migrations.standalone.074_compras_archivo_adjunto"),        # v13.4: optional file attachment per purchase
    _Migration("075",  "migrations.standalone.075_plantillas_compra"),              # Hotfix: plantillas_compra tables missing from schema
    _Migration("076",  "migrations.standalone.076_purchase_requests"),             # Phase 3: tabla purchase_requests (PR)
    _Migration("077",  "migrations.standalone.077_ordenes_compra_erp"),            # Phase 3: extender ordenes_compra con campos ERP
    _Migration("078",  "migrations.standalone.078_compras_po_link"),               # Phase 3: vincular compras con PO (nullable FK)
    _Migration("079",  "migrations.standalone.079_proveedores_condicion_pago"),    # Bugfix: normalizar condicion_pago en proveedores
    _Migration("080",  "migrations.standalone.080_caja_turno_id_link"),           # Caja: turno_id FK en cierres_caja + índices de rendimiento
]

def _ensure_tracking_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            version     TEXT    NOT NULL UNIQUE,
            executed_at TEXT    DEFAULT (datetime('now'))
        )""")
    try: conn.commit()
    except Exception: pass

def _already_run(conn, version):
    try:
        r = conn.execute(
            "SELECT 1 FROM schema_migrations WHERE version=?", (version,)
        ).fetchone()
        return r is not None
    except Exception:
        return False

def _mark_done(conn, version):
    try:
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version) VALUES(?)", (version,))
        conn.commit()
    except Exception: pass

def _schema_needs_bootstrap(conn: sqlite3.Connection) -> bool:
    """Return True if essential tables are missing (DB not initialized)."""
    try:
        conn.execute("SELECT 1 FROM configuraciones LIMIT 1")
        return False
    except Exception:
        return True

def up(db_conn: sqlite3.Connection) -> None:
    """
    Ejecuta todas las migraciones pendientes en orden.
    Seguro de llamar en cada arranque de la aplicación.
    """
    _ensure_tracking_table(db_conn)

    # Si las tablas esenciales no existen aunque m000 esté marcada como hecha,
    # borrar el registro y forzar re-ejecución (DB vacía / corrupta / reemplazada).
    if _schema_needs_bootstrap(db_conn):
        try:
            db_conn.execute("DELETE FROM schema_migrations WHERE version='m000'")
            db_conn.commit()
            logger.warning("Schema vacío detectado — forzando re-ejecución de m000.")
        except Exception:
            pass

    executed = 0

    for migration in MIGRATIONS:
        version = migration.version
        module_path = migration.module
        if _already_run(db_conn, version):
            continue
        try:
            import importlib
            mod = importlib.import_module(module_path)
            fn  = getattr(mod, "run", None) or getattr(mod, "up", None) \
                  or getattr(mod, "crear_tablas", None)
            if fn:
                fn(db_conn)
                _mark_done(db_conn, version)
                logger.info("Migración %s ejecutada.", version)
                executed += 1
            else:
                logger.warning("Migración %s: no se encontró run()/up().", version)
        except ImportError:
            logger.debug("Migración %s: módulo no disponible (omitido).", version)
        except Exception as e:
            logger.error("Migración %s falló: %s — haciendo rollback.", version, e)
            try: db_conn.rollback()
            except Exception: pass

    if executed:
        logger.info("Migraciones completadas: %d ejecutadas.", executed)
    else:
        logger.info("Base de datos al día — sin migraciones pendientes.")

# Alias para compatibilidad con código que llame crear_tablas() o aplicar_migraciones()
crear_tablas = up
aplicar_migraciones = up
