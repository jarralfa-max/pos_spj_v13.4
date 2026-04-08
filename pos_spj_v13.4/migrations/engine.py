
# migrations/engine.py — SPJ POS v12
# ── Motor de Migraciones ──────────────────────────────────────────────────────
# Ejecuta todas las migraciones en orden garantizado.
# Idempotente: usa CREATE TABLE IF NOT EXISTS y ALTER TABLE seguro.
# Registra cada migración ejecutada en la tabla schema_migrations.
import logging, sqlite3
logger = logging.getLogger("spj.migrations")

# Orden estricto de ejecución — NO reordenar
MIGRATIONS = [
    ("m000", "migrations.m000_base_schema"),
    ("m001", "migrations.m001_enterprise_ajustes"),
    ("016",  "migrations.standalone.016_concurrency_events"),
    ("018",  "migrations.standalone.018_sync_industrial_extension"),
    ("019",  "migrations.standalone.019_margin_protection"),
    ("020",  "migrations.standalone.020_system_integrity"),
    ("021",  "migrations.standalone.021_db_hardening"),
    ("022",  "migrations.standalone.022_industrial_hardening"),
    ("023",  "migrations.standalone.023_enterprise_upgrade"),
    ("024",  "migrations.standalone.024_enterprise_blocks_5_8"),
    ("025",  "migrations.standalone.025_sync_batch_log"),
    ("026",  "migrations.standalone.026_final_structural_hardening"),
    ("027",  "migrations.standalone.027_inventory_hardening"),
    ("028",  "migrations.standalone.028_sales_transaction_hardening"),
    ("029",  "migrations.standalone.029_reversals_hardening"),
    ("030",  "migrations.standalone.030_recetas_industriales"),   # fusionado 030a+030b
    ("031",  "migrations.standalone.031_inventory_engine"),       # fusionado 031a+031b
    ("032",  "migrations.standalone.032_bi_tables"),              # fusionado 032+034+meat
    ("033",  "migrations.standalone.033_demand_forecast"),
    ("035",  "migrations.standalone.035_finance_erp"),
    ("036",  "migrations.standalone.036_whatsapp_rasa"),
    ("037",  "migrations.standalone.037_product_images"),
    ("038",  "migrations.standalone.038_transfer_suggestions"),
    ("039",  "migrations.standalone.039_branch_products"),
    ("040",  "migrations.standalone.040_qr_reception"),
    ("041",  "migrations.standalone.041_notification_inbox"),
    ("042",  "migrations.standalone.042_whatsapp_multicanal"),
    ("043",  "migrations.standalone.043_price_history"),
    ("044",  "migrations.standalone.044_cotizaciones"),
    ("045",  "migrations.standalone.045_performance_indexes"),
    ("046",  "migrations.standalone.046_comisiones_happy_hour"),
    ("047",  "migrations.standalone.047_v13_schema"),
    ("048",  "migrations.standalone.048_v131_hardening"),
    ("049",  "migrations.standalone.049_v134_intelligent_erp"),  # FASE 13: tablas ERP inteligente
    ("050",  "migrations.standalone.050_wa_integration"),        # FASE WA: tablas orquestación WA↔ERP
    ("051",  "migrations.standalone.051_fix_kpi_snapshots"),     # FIX: kpi_snapshots faltante por error 032
    ("052",  "migrations.standalone.052_financial_event_log"),  # v13.4: audit trail financiero doble entrada
    ("053",  "migrations.standalone.053_meat_production_tables"),  # v13.4: tablas cárnicas huérfanas de 032
    ("054",  "migrations.standalone.054_sync_improvements_orphan"),  # v13.4: columnas sync huérfanas de 048
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

    for version, module_path in MIGRATIONS:
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
                logger.info("✅ Migración %s ejecutada.", version)
                executed += 1
            else:
                logger.warning("Migración %s: no se encontró run()/up().", version)
        except ImportError:
            logger.debug("Migración %s: módulo no disponible (omitido).", version)
        except Exception as e:
            logger.error("❌ Migración %s falló: %s — haciendo rollback.", version, e)
            try: db_conn.rollback()
            except Exception: pass

    if executed:
        logger.info("Migraciones completadas: %d ejecutadas.", executed)
    else:
        logger.info("Base de datos al día — sin migraciones pendientes.")

# Alias para compatibilidad con código que llame crear_tablas()
crear_tablas = up
