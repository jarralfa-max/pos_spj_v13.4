
# migrations/032_bi_tables.py
# ── FASE 7: Tablas de Agregación BI ──────────────────────────────────────────
#
# Para rendimiento en dashboards CEO, se crean tablas de agregación:
#   ventas_diarias     — snapshot diario por sucursal
#   inventario_diario  — snapshot de stock por producto+sucursal
#   clientes_diarios   — métricas de clientes por día
#
# Triggers actualizan ventas_diarias automáticamente.

import logging, sqlite3
logger = logging.getLogger("spj.migrations.032")

def run(conn: sqlite3.Connection) -> None:
    import logging as _l032
    _log = _l032.getLogger("spj.migrations.032")
    _steps = [
        _create_ventas_diarias,
        _create_inventario_diario,
        _create_clientes_diarios,
        _create_reporte_exports,
        _create_production_batches,
        _create_production_outputs,
        _create_production_yield_analysis,
        _create_production_alerts,
        _create_production_cost_ledger,
        _patch_recetas_for_production,
        _create_kpi_snapshots,
        _create_export_log,
    ]
    for _step in _steps:
        try:
            _step(conn)
        except Exception as _e:
            _log.debug("032 %s: %s", _step.__name__, _e)
    # Safe indexes
    for _idx in [
        "CREATE INDEX IF NOT EXISTS idx_vd_fecha_suc ON ventas_diarias(fecha, sucursal_id)",
        "CREATE INDEX IF NOT EXISTS idx_id_fecha ON inventario_diario(fecha)",
        "CREATE INDEX IF NOT EXISTS idx_cd_fecha_suc ON clientes_diarios(fecha, sucursal_id)",
        "CREATE INDEX IF NOT EXISTS idx_kpi_snap_fecha ON kpi_snapshots(snapshot_date)",
        "CREATE INDEX IF NOT EXISTS idx_kpi_snap_suc ON kpi_snapshots(branch_id)",
        "CREATE INDEX IF NOT EXISTS idx_export_log_tipo ON report_export_log(tipo)",
        "CREATE INDEX IF NOT EXISTS idx_export_log_fecha ON report_export_log(created_at)",
    ]:
        try:
            conn.execute(_idx)
        except Exception:
            pass
    try: conn.commit()
    except Exception: pass
    logger.info("Migración 032 completada.")

def _create_ventas_diarias(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ventas_diarias (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha           DATE    NOT NULL,
            sucursal_id     INTEGER NOT NULL,
            total_ventas    REAL    NOT NULL DEFAULT 0,
            total_costo     REAL    NOT NULL DEFAULT 0,
            total_descuento REAL    NOT NULL DEFAULT 0,
            num_tickets     INTEGER NOT NULL DEFAULT 0,
            num_clientes    INTEGER NOT NULL DEFAULT 0,
            ticket_promedio REAL    NOT NULL DEFAULT 0,
            margen_bruto    REAL    NOT NULL DEFAULT 0,
            margen_pct      REAL    NOT NULL DEFAULT 0,
            updated_at      TEXT    DEFAULT (datetime('now')),
            UNIQUE(fecha, sucursal_id),
            FOREIGN KEY (sucursal_id) REFERENCES sucursales(id) ON DELETE RESTRICT
        )
    """)
    logger.info("ventas_diarias creada/verificada.")

def _create_inventario_diario(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS inventario_diario (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha           DATE    NOT NULL,
            producto_id     INTEGER NOT NULL,
            sucursal_id     INTEGER NOT NULL,
            cantidad        REAL    NOT NULL DEFAULT 0,
            valor           REAL    NOT NULL DEFAULT 0,
            updated_at      TEXT    DEFAULT (datetime('now')),
            UNIQUE(fecha, producto_id, sucursal_id),
            FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE RESTRICT,
            FOREIGN KEY (sucursal_id) REFERENCES sucursales(id) ON DELETE RESTRICT
        )
    """)
    logger.info("inventario_diario creada/verificada.")

def _create_clientes_diarios(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clientes_diarios (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha           DATE    NOT NULL,
            sucursal_id     INTEGER NOT NULL,
            clientes_activos INTEGER NOT NULL DEFAULT 0,
            clientes_nuevos  INTEGER NOT NULL DEFAULT 0,
            ventas_con_fidelidad INTEGER NOT NULL DEFAULT 0,
            puntos_emitidos  INTEGER NOT NULL DEFAULT 0,
            puntos_canjeados INTEGER NOT NULL DEFAULT 0,
            updated_at      TEXT    DEFAULT (datetime('now')),
            UNIQUE(fecha, sucursal_id),
            FOREIGN KEY (sucursal_id) REFERENCES sucursales(id) ON DELETE RESTRICT
        )
    """)
    logger.info("clientes_diarios creada/verificada.")

def _create_reporte_exports(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reporte_exports (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo        TEXT NOT NULL,
            formato     TEXT NOT NULL,
            ruta        TEXT,
            usuario     TEXT,
            parametros  TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)

def _create_indexes(conn):
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vd_fecha_suc ON ventas_diarias(fecha, sucursal_id)")
    except Exception: pass
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_id_fecha ON inventario_diario(fecha)")
    except Exception: pass
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_cd_fecha_suc ON clientes_diarios(fecha, sucursal_id)")
    except Exception: pass


# ── Helpers fusionados desde 032_meat_production.py ─────────────────────────

# migrations/032_meat_production.py
# ── FASE 9: Enterprise Meat Production Engine ─────────────────────────────────
#
# Tablas nuevas:
#   1. production_batches       — lote de procesamiento (pollo, marinados, etc.)
#   2. production_outputs       — subproductos generados por lote
#   3. production_yield_analysis — análisis de rendimiento real vs esperado
#   4. production_alerts        — alertas de merma excesiva
#   5. production_cost_ledger   — distribución de costo por subproducto
#
# Todas idempotentes (CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS).

import logging
import sqlite3

logger = logging.getLogger("spj.migrations.032")

TOLERANCE_PCT = 0.5   # 0.5% tolerancia matemática


def _create_production_batches(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS production_batches (
            id                  TEXT    PRIMARY KEY,
            folio               TEXT    NOT NULL,
            product_source_id   INTEGER NOT NULL,
            source_weight       REAL    NOT NULL CHECK(source_weight > 0),
            processed_weight    REAL    NOT NULL DEFAULT 0 CHECK(processed_weight >= 0),
            waste_weight        REAL    NOT NULL DEFAULT 0 CHECK(waste_weight >= 0),
            usable_weight       REAL    GENERATED ALWAYS AS
                                (processed_weight) VIRTUAL,
            waste_pct           REAL    GENERATED ALWAYS AS
                                (CASE WHEN source_weight > 0
                                 THEN ROUND(waste_weight * 100.0 / source_weight, 4)
                                 ELSE 0 END) VIRTUAL,
            source_cost_total   REAL    NOT NULL DEFAULT 0 CHECK(source_cost_total >= 0),
            cost_per_kg         REAL    GENERATED ALWAYS AS
                                (CASE WHEN source_weight > 0
                                 THEN ROUND(source_cost_total / source_weight, 6)
                                 ELSE 0 END) VIRTUAL,
            branch_id           INTEGER NOT NULL,
            receta_id           INTEGER,
            estado              TEXT    NOT NULL DEFAULT 'abierto'
                                CHECK(estado IN ('abierto','cerrado','cancelado')),
            created_by          TEXT    NOT NULL,
            closed_by           TEXT,
            created_at          DATETIME DEFAULT (datetime('now')),
            closed_at           DATETIME,
            operation_id        TEXT    NOT NULL,
            notas               TEXT,
            FOREIGN KEY (product_source_id) REFERENCES productos(id) ON DELETE RESTRICT,
            FOREIGN KEY (branch_id)         REFERENCES sucursales(id) ON DELETE RESTRICT,
            FOREIGN KEY (receta_id)         REFERENCES recetas(id)    ON DELETE SET NULL
        )
    """)
    logger.info("production_batches creada/verificada.")


# ── 2. production_outputs ─────────────────────────────────────────────────────

def _create_production_outputs(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS production_outputs (
            id                  TEXT    PRIMARY KEY,
            batch_id            TEXT    NOT NULL,
            product_id          INTEGER NOT NULL,
            weight              REAL    NOT NULL CHECK(weight >= 0),
            expected_weight     REAL    NOT NULL DEFAULT 0 CHECK(expected_weight >= 0),
            expected_pct        REAL    NOT NULL DEFAULT 0 CHECK(expected_pct >= 0),
            real_pct            REAL    NOT NULL DEFAULT 0,
            cost_allocated      REAL    NOT NULL DEFAULT 0 CHECK(cost_allocated >= 0),
            is_waste            INTEGER NOT NULL DEFAULT 0,
            created_at          DATETIME DEFAULT (datetime('now')),
            FOREIGN KEY (batch_id)    REFERENCES production_batches(id) ON DELETE RESTRICT,
            FOREIGN KEY (product_id)  REFERENCES productos(id)          ON DELETE RESTRICT,
            UNIQUE (batch_id, product_id)
        )
    """)
    logger.info("production_outputs creada/verificada.")


# ── 3. production_yield_analysis ──────────────────────────────────────────────

def _create_production_yield_analysis(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS production_yield_analysis (
            id              TEXT    PRIMARY KEY,
            batch_id        TEXT    NOT NULL UNIQUE,
            expected_yield  REAL    NOT NULL,
            real_yield      REAL    NOT NULL,
            variance        REAL    GENERATED ALWAYS AS
                            (ROUND(real_yield - expected_yield, 6)) VIRTUAL,
            waste_expected  REAL    NOT NULL DEFAULT 0,
            waste_real      REAL    NOT NULL DEFAULT 0,
            waste_variance  REAL    GENERATED ALWAYS AS
                            (ROUND(waste_real - waste_expected, 6)) VIRTUAL,
            efficiency_pct  REAL    GENERATED ALWAYS AS
                            (CASE WHEN expected_yield > 0
                             THEN ROUND(real_yield * 100.0 / expected_yield, 4)
                             ELSE 0 END) VIRTUAL,
            alerta_merma    INTEGER NOT NULL DEFAULT 0,
            created_at      DATETIME DEFAULT (datetime('now')),
            FOREIGN KEY (batch_id) REFERENCES production_batches(id) ON DELETE CASCADE
        )
    """)
    logger.info("production_yield_analysis creada/verificada.")


# ── 4. production_alerts ──────────────────────────────────────────────────────

def _create_production_alerts(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS production_alerts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id        TEXT    NOT NULL,
            tipo            TEXT    NOT NULL,
            mensaje         TEXT    NOT NULL,
            valor_esperado  REAL,
            valor_real      REAL,
            varianza        REAL,
            resuelta        INTEGER NOT NULL DEFAULT 0,
            created_at      DATETIME DEFAULT (datetime('now')),
            FOREIGN KEY (batch_id) REFERENCES production_batches(id) ON DELETE CASCADE
        )
    """)
    logger.info("production_alerts creada/verificada.")


# ── 5. production_cost_ledger ─────────────────────────────────────────────────

def _create_production_cost_ledger(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS production_cost_ledger (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id        TEXT    NOT NULL,
            output_id       TEXT    NOT NULL,
            product_id      INTEGER NOT NULL,
            weight          REAL    NOT NULL,
            pct_utilizable  REAL    NOT NULL,
            cost_total      REAL    NOT NULL,
            cost_per_kg     REAL    NOT NULL,
            created_at      DATETIME DEFAULT (datetime('now')),
            FOREIGN KEY (batch_id)   REFERENCES production_batches(id)  ON DELETE CASCADE,
            FOREIGN KEY (output_id)  REFERENCES production_outputs(id)  ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES productos(id)           ON DELETE RESTRICT
        )
    """)
    logger.info("production_cost_ledger creada/verificada.")


# ── 6. Índices ────────────────────────────────────────────────────────────────

def _create_indexes(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE INDEX IF NOT EXISTS idx_production_batches_branch  ON production_batches(branch_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_production_batches_estado  ON production_batches(estado)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_production_batches_fecha   ON production_batches(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_production_batches_source  ON production_batches(product_source_id)")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_production_batches_op ON production_batches(operation_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_production_outputs_batch   ON production_outputs(batch_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_production_outputs_product ON production_outputs(product_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_yield_analysis_batch       ON production_yield_analysis(batch_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_prod_alerts_batch          ON production_alerts(batch_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_prod_alerts_resuelta       ON production_alerts(resuelta)")
    logger.info("Índices de producción cárnica creados/verificados.")


# ── 7. Parche a recetas: columna rendimiento_esperado_pct ─────────────────────

def _patch_recetas_for_production(conn: sqlite3.Connection) -> None:
    existing = {r[1] for r in conn.execute("PRAGMA table_info(recetas)").fetchall()}
    if "rendimiento_esperado_pct" not in existing:
        conn.execute("ALTER TABLE recetas ADD COLUMN rendimiento_esperado_pct REAL DEFAULT 0")
    if "merma_esperada_pct" not in existing:
        conn.execute("ALTER TABLE recetas ADD COLUMN merma_esperada_pct REAL DEFAULT 0")
    # receta_componentes: columna tipo para distinguir subproducto vs insumo adicional
    existing2 = {r[1] for r in conn.execute("PRAGMA table_info(receta_componentes)").fetchall()}
    if "tipo_componente" not in existing2:
        conn.execute("ALTER TABLE receta_componentes ADD COLUMN tipo_componente TEXT DEFAULT 'subproducto'")
    logger.info("recetas + receta_componentes parchadas para rendimiento esperado.")

# ── Helpers fusionados desde 034_bi_tables.py ────────────────────────────────

# migrations/034_bi_tables.py
# ── FASE 7: Business Intelligence — Tablas de Agregación ─────────────────────
#
# Propósito: evitar queries pesadas en tiempo real.
# Las tablas de agregación se populan automáticamente tras cada venta
# y via snapshot nocturno del Scheduler.
#
# Tablas:
#   1. ventas_diarias           — ya existe, solo asegura columnas
#   2. inventario_diario        — ya existe, solo asegura columnas
#   3. clientes_diarios         — nuevos registros diarios de clientes
#   4. report_export_log        — historial de exportaciones (PDF/Excel/CSV)
#   5. kpi_snapshots            — snapshots históricos de KPIs para tendencias

import logging
import sqlite3

logger = logging.getLogger("spj.migrations.034")



def _patch_ventas_diarias(conn):
    """Asegura columnas adicionales en ventas_diarias."""
    existing = {r[1] for r in conn.execute("PRAGMA table_info(ventas_diarias)").fetchall()}
    patches = [
        ("total_descuento_pct",  "REAL    DEFAULT 0"),
        ("clientes_nuevos",      "INTEGER DEFAULT 0"),
        ("productos_distintos",  "INTEGER DEFAULT 0"),
    ]
    for col, defn in patches:
        if col not in existing:
            conn.execute(f"ALTER TABLE ventas_diarias ADD COLUMN {col} {defn}")
    # UNIQUE index para evitar duplicados
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ventas_diarias_fecha_suc
        ON ventas_diarias(fecha, sucursal_id)
    """)


def _patch_inventario_diario(conn):
    """Asegura UNIQUE index en inventario_diario."""
    existing = {r[1] for r in conn.execute("PRAGMA table_info(inventario_diario)").fetchall()}
    patches = [
        ("costo_promedio",   "REAL DEFAULT 0"),
        ("alerta",           "TEXT DEFAULT 'OK'"),
    ]
    for col, defn in patches:
        if col not in existing:
            conn.execute(f"ALTER TABLE inventario_diario ADD COLUMN {col} {defn}")
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_inventario_diario_uk
        ON inventario_diario(fecha, producto_id, sucursal_id)
    """)


def _create_clientes_diarios(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clientes_diarios (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha       DATE    NOT NULL,
            sucursal_id INTEGER NOT NULL,
            nuevos      INTEGER NOT NULL DEFAULT 0,
            activos     INTEGER NOT NULL DEFAULT 0,
            recurrentes INTEGER NOT NULL DEFAULT 0,
            inactivos30 INTEGER NOT NULL DEFAULT 0,
            updated_at  DATETIME DEFAULT (datetime('now')),
            UNIQUE (fecha, sucursal_id)
        )
    """)


def _create_export_log(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS report_export_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo        TEXT    NOT NULL,
            formato     TEXT    NOT NULL CHECK(formato IN ('PDF','Excel','CSV')),
            branch_id   INTEGER,
            fecha_desde DATE,
            fecha_hasta DATE,
            filepath    TEXT,
            size_bytes  INTEGER DEFAULT 0,
            usuario     TEXT,
            created_at  DATETIME DEFAULT (datetime('now'))
        )
    """)
    
    

def _create_kpi_snapshots(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS kpi_snapshots (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id        INTEGER NOT NULL,
            snapshot_date    DATE    NOT NULL,
            total_revenue    REAL    NOT NULL DEFAULT 0,
            total_cost       REAL    NOT NULL DEFAULT 0,
            gross_margin     REAL    NOT NULL DEFAULT 0,
            gross_margin_pct REAL    NOT NULL DEFAULT 0,
            ticket_count     INTEGER NOT NULL DEFAULT 0,
            avg_ticket       REAL    NOT NULL DEFAULT 0,
            active_clients   INTEGER NOT NULL DEFAULT 0,
            new_clients      INTEGER NOT NULL DEFAULT 0,
            points_issued    INTEGER NOT NULL DEFAULT 0,
            inventory_value  REAL    NOT NULL DEFAULT 0,
            computed_at      DATETIME NOT NULL DEFAULT (datetime('now')),
            UNIQUE (branch_id, snapshot_date)
        )
    """)


def _create_indexes(conn):
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kpi_snap_fecha   ON kpi_snapshots(snapshot_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_kpi_snap_suc     ON kpi_snapshots(branch_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_export_log_tipo  ON report_export_log(tipo)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_export_log_fecha ON report_export_log(created_at)")

def up(conn):
    """Safe wrapper for run() — all sub-steps use try/except."""
    import logging as _l
    _log = _l.getLogger("spj.migrations.032")
    steps = [
        _create_ventas_diarias,
        _create_inventario_diario,
        _create_clientes_diarios,
        _create_reporte_exports,
        _create_production_batches,
        _create_production_outputs,
        _create_production_yield_analysis,
        _create_production_alerts,
        _create_production_cost_ledger,
        _patch_recetas_for_production,
        _patch_ventas_diarias,
        _patch_inventario_diario,
        _create_export_log,
        _create_kpi_snapshots,
    ]
    for step in steps:
        try:
            step(conn)
        except Exception as e:
            _log.debug("032 step %s: %s", step.__name__, e)
    # Safe indexes
    for idx_sql in [
        "CREATE INDEX IF NOT EXISTS idx_vd_fecha_suc ON ventas_diarias(fecha, sucursal_id)",
        "CREATE INDEX IF NOT EXISTS idx_id_fecha ON inventario_diario(fecha)",
        "CREATE INDEX IF NOT EXISTS idx_cd_fecha_suc ON clientes_diarios(fecha, sucursal_id)",
        "CREATE INDEX IF NOT EXISTS idx_kpi_snap_fecha ON kpi_snapshots(snapshot_date)",
        "CREATE INDEX IF NOT EXISTS idx_kpi_snap_suc ON kpi_snapshots(branch_id)",
        "CREATE INDEX IF NOT EXISTS idx_export_log_tipo ON report_export_log(tipo)",
        "CREATE INDEX IF NOT EXISTS idx_export_log_fecha ON report_export_log(created_at)",
    ]:
        try:
            conn.execute(idx_sql)
        except Exception:
            pass
    _log.info("032 done")
