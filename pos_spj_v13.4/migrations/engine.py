
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
    _Migration("030",  "migrations.standalone.030_recetas_industriales"),
    _Migration("031",  "migrations.standalone.031_inventory_engine"),
    _Migration("032",  "migrations.standalone.032_bi_tables"),
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
    _Migration("049",  "migrations.standalone.049_v134_intelligent_erp"),
    _Migration("050",  "migrations.standalone.050_wa_integration"),
    _Migration("051",  "migrations.standalone.051_fix_kpi_snapshots"),
    _Migration("052",  "migrations.standalone.052_financial_event_log"),
    _Migration("053",  "migrations.standalone.053_meat_production_tables"),
    _Migration("054",  "migrations.standalone.054_sync_improvements_orphan"),
    _Migration("055",  "migrations.standalone.055_inventario_compat"),
    _Migration("056",  "migrations.standalone.056_print_job_log"),
    _Migration("057",  "migrations.standalone.057_loyalty_ledger_unificado"),
    _Migration("058",  "migrations.standalone.058_scan_event_log"),
    _Migration("059",  "migrations.standalone.059_plan_cuentas"),
    _Migration("060",  "migrations.standalone.060_depreciacion_acumulada"),
    _Migration("061",  "migrations.standalone.061_fix_finanzas_schema"),
    _Migration("062",  "migrations.standalone.062_bi_analytics_tables"),
    _Migration("063",  "migrations.standalone.063_audit_log_table"),
    _Migration("064",  "migrations.standalone.064_fix_missing_columns"),
    _Migration("065",  "migrations.standalone.065_performance_indexes_views"),
    _Migration("066",  "migrations.standalone.066_unificar_esquema_recetas"),
    _Migration("067",  "migrations.standalone.067_meat_erp_improvements"),
    _Migration("068",  "migrations.standalone.068_fix_branch_inventory_unique"),
    _Migration("069",  "migrations.standalone.069_delivery_weight_reservation"),
    _Migration("070",  "migrations.standalone.070_delivery_enterprise_lifecycle"),
    _Migration("071",  "migrations.standalone.071_compras_condicion_pago"),
    _Migration("072",  "migrations.standalone.072_condicion_pago_check"),
    _Migration("073",  "migrations.standalone.073_temp_purchase_drafts"),
    _Migration("074",  "migrations.standalone.074_compras_archivo_adjunto"),
    _Migration("075",  "migrations.standalone.075_plantillas_compra"),
    _Migration("076",  "migrations.standalone.076_purchase_requests"),
    _Migration("077",  "migrations.standalone.077_ordenes_compra_erp"),
    _Migration("078",  "migrations.standalone.078_compras_po_link"),
    _Migration("079",  "migrations.standalone.079_proveedores_condicion_pago"),
    _Migration("080",  "migrations.standalone.080_caja_turno_id_link"),
    _Migration("081",  "migrations.standalone.081_wa_queue_backoff"),
    _Migration("082",  "migrations.standalone.082_treasury_tables"),
    _Migration("083",  "migrations.standalone.083_financial_traceability_tables"),
    _Migration("084",  "migrations.standalone.084_capital_movements"),
    _Migration("085",  "migrations.standalone.085_product_type_flags"),
    _Migration("086",  "migrations.standalone.086_whatsapp_order_sales_columns"),
    _Migration("087",  "migrations.standalone.087_whatsapp_sale_detail_columns"),
    _Migration("088",  "migrations.standalone.088_delivery_adjustment_approval"),
    _Migration("089",  "migrations.standalone.089_notification_inbox_dedupe_key"),
    _Migration("090",  "migrations.standalone.090_whatsapp_delivery_workflow_columns"),
    _Migration("091",  "migrations.standalone.091_scheduled_demand_events"),
    _Migration("092",  "migrations.standalone.092_loyalty_ledger_canonicalization"),
    _Migration("093",  "migrations.standalone.093_rrhh_payroll_traceability"),
    _Migration("094",  "migrations.standalone.094_rrhh_delivery_cleanup_schema"),
    _Migration("095",  "migrations.standalone.095_rrhh_identity_links"),
    _Migration("096",  "migrations.standalone.096_configuration_services_schema"),
    _Migration("097",  "migrations.standalone.097_waste_schema_integrity"),
    _Migration("098",  "migrations.standalone.098_canonical_inventory"),
    _Migration("099",  "migrations.standalone.099_archive_legacy_inventory_sources"),
    _Migration("100",  "migrations.standalone.100_inventory_movements_incremental_columns"),
    _Migration("101",  "migrations.standalone.101_entity_uuid_columns"),
    _Migration("102",  "migrations.standalone.102_extended_uuid_columns"),
    _Migration("103",  "migrations.standalone.103_happy_hour_sucursal_uuid"),
    _Migration("104",  "migrations.standalone.104_rol_permisos_uuid_columns"),
    _Migration("105",  "migrations.standalone.105_movimientos_inventario"),
    _Migration("106",  "migrations.standalone.106_inventario_actual_branch"),
    _Migration("107",  "migrations.standalone.107_productos_costo_column"),
    _Migration("108",  "migrations.standalone.108_sync_inventory_stock"),
    _Migration("109",  "migrations.standalone.109_delivery_driver_cuts_schema"),
    _Migration("110",  "migrations.standalone.110_delivery_status_english"),
    _Migration("111",  "migrations.standalone.111_qr_containers_schema"),
    _Migration("112",  "migrations.standalone.112_card_schema_reconciliation"),
    _Migration("113",  "migrations.standalone.113_raffle_subsystem"),
    _Migration("114",  "migrations.standalone.114_anticipos_schema"),
    _Migration("115",  "migrations.standalone.115_security_lock_and_canonical_kpi_schema"),
    _Migration("116",  "migrations.standalone.116_roles_uuidv7_identity"),
    _Migration("117",  "migrations.standalone.117_finance_bounded_context_schema"),
    _Migration("118",  "migrations.standalone.118_hr_bounded_context_schema"),
    _Migration("119",  "migrations.standalone.119_supplier_bounded_context_schema"),
    _Migration("120",  "migrations.standalone.120_procurement_bounded_context_schema"),
    _Migration("121",  "migrations.standalone.121_inventory_bounded_context_schema"),
    _Migration("122",  "migrations.standalone.122_inventory_lots_schema"),
    _Migration("123",  "migrations.standalone.123_inventory_cold_chain_schema"),
    _Migration("124",  "migrations.standalone.124_inventory_reservations_schema"),
    _Migration("125",  "migrations.standalone.125_inventory_transfers_schema"),
    _Migration("126",  "migrations.standalone.126_inventory_counts_schema"),
    _Migration("127",  "migrations.standalone.127_inventory_adjustments_schema"),
    _Migration("128",  "migrations.standalone.128_inventory_quarantine_schema"),
    _Migration("129",  "migrations.standalone.129_inventory_waste_schema"),
    _Migration("130",  "migrations.standalone.130_inventory_traceability_schema"),
    _Migration("131",  "migrations.standalone.131_inventory_replenishment_schema"),
    _Migration("132",  "migrations.standalone.132_inventory_sync_schema"),
    _Migration("133",  "migrations.standalone.133_inventory_notifications_schema"),
    _Migration("134",  "migrations.standalone.134_inventory_canonical_cutover"),
    _Migration("135",  "migrations.standalone.135_inventory_labels_schema"),
    _Migration("136",  "migrations.standalone.136_products_bounded_context_schema"),
]

def _ensure_tracking_table(conn):
    # Ledger de migraciones: la identidad natural es `version` (única, inmutable).
    # Sin surrogate entero AUTOINCREMENT (REGLA CERO/REGLA 3: el id nunca se lee;
    # alineado con la definición born-clean de la migración 026).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     TEXT NOT NULL PRIMARY KEY,
            executed_at TEXT DEFAULT (datetime('now'))
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
    try:
        conn.execute("SELECT 1 FROM configuraciones LIMIT 1")
        return False
    except Exception:
        return True

def up(db_conn: sqlite3.Connection) -> None:
    _ensure_tracking_table(db_conn)
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
            fn  = getattr(mod, "run", None) or getattr(mod, "up", None) or getattr(mod, "crear_tablas", None)
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

crear_tablas = up
aplicar_migraciones = up