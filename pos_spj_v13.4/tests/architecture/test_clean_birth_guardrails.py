"""Plan B — Desarrollo limpio sin migraciones legacy: guardrails.

These tests enforce the "born-clean UUIDv7" direction (REGLA DE DESARROLLO — SIN
CONSERVACIÓN DE DATOS LEGACY in docs/skills/SPJ_REFACTOR_SKILL.md):

  * HARD LOCKS pin the already-clean pieces (alertas tables/service, the badge
    refresh) so the legacy patterns cannot come back.
  * DEBT CEILINGS bound the still-pending legacy surface (INTEGER PK tables in
    the base schema, services that emit DDL, ``lastrowid`` usage). The target for
    every ceiling is ZERO — the born-clean base schema is the terminal step of
    FASE 7 and can only be reached once each module mints UUIDs explicitly; until
    then these numbers must only shrink, never grow.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _fresh_base_schema() -> sqlite3.Connection:
    import migrations.m000_base_schema as base

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    return conn


# ── HARD LOCKS — already born clean, must stay clean ────────────────────────────

def test_alertas_tables_are_text_pk_in_base_schema():
    conn = _fresh_base_schema()
    for table in ("alertas_config", "alertas_log"):
        cols = {r[1]: r for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        # PRAGMA columns: (cid, name, type, notnull, dflt_value, pk)
        assert cols["id"][2].upper() == "TEXT", f"{table}.id must be TEXT"
        assert cols["id"][5] == 1, f"{table}.id must be PRIMARY KEY"
        assert cols["sucursal_id"][2].upper() == "TEXT", f"{table}.sucursal_id must be TEXT"


def test_alertas_service_emits_no_ddl_and_no_default_one():
    src = (REPO / "core" / "services" / "alertas_service.py").read_text(encoding="utf-8")
    for ddl in ("CREATE TABLE", "ALTER TABLE", "DROP TABLE", "executescript", "AUTOINCREMENT"):
        assert ddl not in src, f"alertas_service.py must not contain {ddl!r}"
    assert "DEFAULT 1" not in src
    assert "sucursal_id: int" not in src
    assert "from backend.shared.ids import new_uuid" in src


def test_alertas_service_requires_uuid_branch_and_mints_uuid():
    import uuid

    from core.services.alertas_service import AlertasService

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE alertas_config(id TEXT PRIMARY KEY, tipo TEXT, activa INTEGER DEFAULT 1,
            umbral REAL, canal TEXT, sucursal_id TEXT, descripcion TEXT);
        CREATE TABLE alertas_log(id TEXT PRIMARY KEY, tipo TEXT, titulo TEXT, mensaje TEXT,
            datos TEXT, leida INTEGER DEFAULT 0, canal_enviado TEXT, sucursal_id TEXT, fecha TEXT);
        """
    )
    conn.commit()

    with pytest.raises(ValueError):
        AlertasService(conn=conn, sucursal_id=None)  # no arbitrary default branch

    branch = str(uuid.uuid4())
    svc = AlertasService(conn=conn, sucursal_id=branch)
    svc.seed_defaults()
    assert svc.disparar("stock_bajo", "x") is True
    row = conn.execute("SELECT id, sucursal_id FROM alertas_log").fetchone()
    assert uuid.UUID(row["id"])              # log identity is UUIDv7
    assert row["sucursal_id"] == branch      # branch FK is the UUID string


def test_bi_tables_are_born_clean_after_full_migration_chain():
    """kpi_snapshots / reporte_exports carry no integer surrogate identity.

    kpi_snapshots is keyed by its natural (branch_id, snapshot_date) — the same
    columns report_engine upserts on — with branch_id as a UUIDv7 TEXT string.
    Validated against the FULL chain because migrations 023/024/032/051 each
    (re)create kpi_snapshots.
    """
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()

    kpi = {r[1]: (r[2], r[5]) for r in conn.execute("PRAGMA table_info(kpi_snapshots)").fetchall()}
    assert "id" not in kpi                       # no integer surrogate
    assert kpi["branch_id"][0].upper() == "TEXT"
    assert kpi["branch_id"][1] >= 1              # part of the composite primary key
    assert kpi["snapshot_date"][1] >= 1

    rep = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(reporte_exports)").fetchall()}
    assert rep["id"] == "TEXT"


def test_reportes_analytics_tables_are_born_clean():
    """REPORTES/BI born-clean: report_export_log (base) lleva id TEXT UUIDv7 con
    branch_id TEXT; las tablas analíticas bi_sales_daily / bi_product_profit /
    bi_branch_ranking (062) usan identidad natural compuesta (sin surrogate,
    patrón kpi_snapshots) y bi_transformations (bitácora append) lleva id TEXT
    UUIDv7. AnalyticsEngine y ReportEngine acuñan UUID / no castean sucursal_id.
    """
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()

    rel = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(report_export_log)").fetchall()}
    assert rel["id"] == "TEXT" and rel["branch_id"] == "TEXT"

    # bi_transformations: bitácora append con id TEXT UUIDv7.
    bt = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(bi_transformations)").fetchall()}
    assert bt["id"] == ("TEXT", 1) and bt["sucursal_id"][0] == "TEXT"

    # bi_sales_daily / bi_product_profit / bi_branch_ranking: clave natural
    # compuesta, sin surrogate id entero.
    for table, key_cols in (("bi_sales_daily", ("fecha", "sucursal_id")),
                            ("bi_product_profit", ("fecha", "producto_id")),
                            ("bi_branch_ranking", ("fecha", "sucursal_id"))):
        cols = {r[1]: (r[2].upper(), r[5]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        assert "id" not in cols, f"{table} no debe tener surrogate id entero"
        for kc in key_cols:
            assert cols[kc][1] >= 1, f"{table}.{kc} debe ser parte de la PK natural"
            assert cols[kc][0] == "TEXT", f"{table}.{kc} debe ser TEXT"

    ae_src = (REPO / "core/services/analytics/analytics_engine.py").read_text(encoding="utf-8")
    assert "from backend.shared.ids import new_uuid" in ae_src
    assert "INSERT INTO bi_transformations\n                    (id," in ae_src
    assert "int(data.get(\"sucursal_id\"" not in ae_src
    re_src = (REPO / "core/services/enterprise/report_engine.py").read_text(encoding="utf-8")
    assert "INSERT INTO report_export_log (\n                    id," in re_src


def test_api_webapp_treats_identity_as_uuid_no_int_casts():
    """La API REST (webapp) trata las identidades como UUIDv7 TEXT: api_pedidos
    no castea producto_id/sucursal_id a entero ni asume DEFAULT 1; ItemPedido
    declara producto_id como str. api_dashboard solo castea agregados (counts),
    no identidades.
    """
    pat = re.compile(r"int\s*\(\s*(?:producto|sucursal|cliente|venta|pedido|order|branch)_id")
    for path in ("webapp/api_pedidos.py", "webapp/api_dashboard.py"):
        src = (REPO / path).read_text(encoding="utf-8")
        assert not pat.search(src), f"{path} no debe castear identidades a int"
    api_src = (REPO / "webapp/api_pedidos.py").read_text(encoding="utf-8")
    assert 'int(body.get("sucursal_id"' not in api_src
    assert 'int(i.get("id"' not in api_src
    uc_src = (REPO / "core/use_cases/pedido_wa.py").read_text(encoding="utf-8")
    assert "producto_id: str" in uc_src


def test_sincronizacion_tables_are_born_clean_single_uuid_identity():
    """SINCRONIZACION born-clean (REGLA CERO): las tablas del motor offline-first
    llevan identidad UUIDv7 TEXT única — sin columna uuid dual, sin surrogate
    entero, sin DEFAULT 1:
      - sync_outbox / sync_inbox / event_log: id TEXT PRIMARY KEY (sin uuid dual),
        registro_id/entidad_id/sucursal_id/sucursal_origen TEXT.
      - sync_batch_log: identidad natural batch_id TEXT (sin surrogate id).
      - sync_version_history: PK compuesta (event_id, version) (sin surrogate id).
    Los writers acuñan new_uuid() y NO usan lastrowid como identidad; el protocolo
    de sync expone id AS uuid (compatibilidad de wire sin columna dual).
    """
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()

    # Tablas con id TEXT PK único (sin columna uuid dual).
    for table, fk_cols in (
        ("sync_outbox", ("registro_id", "sucursal_id")),
        ("sync_inbox", ("registro_id", "sucursal_origen")),
        ("event_log", ("entidad_id", "sucursal_id")),
    ):
        cols = {r[1]: (r[2].upper(), r[4], r[5]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        assert cols["id"][0] == "TEXT", f"{table}.id debe ser TEXT"
        assert cols["id"][2] == 1, f"{table}.id debe ser PRIMARY KEY"
        assert "uuid" not in cols, f"{table} no debe tener columna uuid dual"
        for fk in fk_cols:
            assert cols[fk][0] == "TEXT", f"{table}.{fk} debe ser TEXT"
        # sucursal_id no debe traer DEFAULT 1.
        if "sucursal_id" in cols:
            assert cols["sucursal_id"][1] not in (1, "1"), f"{table}.sucursal_id no debe tener DEFAULT 1"

    # sync_batch_log: identidad natural batch_id TEXT, sin surrogate id.
    sbl = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(sync_batch_log)").fetchall()}
    assert "id" not in sbl, "sync_batch_log no debe tener surrogate id entero"
    assert sbl["batch_id"] == ("TEXT", 1), "sync_batch_log.batch_id debe ser TEXT PRIMARY KEY"

    # sync_version_history: PK natural compuesta (event_id, version), sin surrogate.
    svh = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(sync_version_history)").fetchall()}
    assert "id" not in svh, "sync_version_history no debe tener surrogate id entero"
    assert svh["event_id"][1] >= 1 and svh["version"][1] >= 1, "PK compuesta (event_id, version)"

    # Writers acuñan UUIDv7 y no usan lastrowid como identidad.
    se_src = (REPO / "sync/sync_engine.py").read_text(encoding="utf-8")
    assert "from backend.shared.ids import new_uuid" in se_src
    assert "AUTOINCREMENT" not in se_src
    el_src = (REPO / "sync/event_logger.py").read_text(encoding="utf-8")
    assert "event_uuid   = new_uuid()" in el_src
    assert "cur.lastrowid" not in el_src
    ss_src = (REPO / "core/services/sync_service.py").read_text(encoding="utf-8")
    assert "new_uuid()" in ss_src
    # El protocolo de sync preserva el wire alias id AS uuid (sin columna dual).
    assert "id AS uuid" in se_src
    sw_src = (REPO / "sync/sync_worker.py").read_text(encoding="utf-8")
    assert "id AS uuid" in sw_src


def test_loyalty_ledger_born_clean_and_dead_points_tables_removed():
    """The canonical loyalty_ledger carries a TEXT UUIDv7 id (minted by the repo,
    not autoincrement) with TEXT cliente_id/sucursal_id, and the dead points
    tables (puntos, loyalty_points_log) are gone from the schema.
    """
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()

    led = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(loyalty_ledger)").fetchall()}
    assert led["id"] == "TEXT"
    assert led["cliente_id"] == "TEXT"
    assert led["sucursal_id"] == "TEXT"

    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "puntos" not in tables
    assert "loyalty_points_log" not in tables

    # The loyalty_ledger insert mints a UUIDv7 id and inserts it explicitly.
    src = (REPO / "repositories" / "loyalty_repository.py").read_text(encoding="utf-8")
    assert "from backend.shared.ids import new_uuid" in src
    assert "INSERT INTO loyalty_ledger\n            (id, cliente_id" in src
    assert "new_uuid()," in src


def test_raffle_subsystem_born_clean_and_ddl_lives_in_migration():
    """The raffle subsystem (migration 113) is born-clean: every table carries a
    TEXT UUIDv7 primary key and TEXT functional FKs, the schema lives in
    migrations/ (REGLA 11) — LoyaltyRepository.ensure_raffle_tables delegates to
    the migration instead of emitting inline DDL — and identities are minted as
    UUIDv7, never captured from autoincrement.
    """
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()

    text_pk = {
        "raffles": (),
        "raffle_tickets": ("raffle_id", "cliente_id", "venta_id"),
        "raffle_financial_ledger": ("raffle_id",),
        "raffle_winners": ("raffle_id", "ticket_id", "prize_id", "cliente_id"),
        "raffle_rules": ("raffle_id",),
        "raffle_prizes": ("raffle_id",),
        "raffle_eligible_products": ("raffle_id", "product_id"),
        "raffle_eligible_categories": ("raffle_id", "category_id"),
        "raffle_eligible_branches": ("raffle_id", "sucursal_id"),
    }
    for table, fks in text_pk.items():
        cols = {r[1]: (r[2].upper(), r[5]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        assert cols, f"{table} missing after migration 113"
        assert cols["id"] == ("TEXT", 1), f"{table}.id must be TEXT PRIMARY KEY"
        for fk in fks:
            assert cols[fk][0] == "TEXT", f"{table}.{fk} must be TEXT (no integer surrogate)"

    # Migration 113 is registered in the engine chain.
    versions = {m.version for m in migrator.MIGRATIONS}
    assert "113" in versions

    # The repo holds no inline raffle DDL; it delegates to the migration and mints UUIDs.
    src = (REPO / "repositories" / "loyalty_repository.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS raffles" not in src
    assert "migrations.standalone.113_raffle_subsystem" in src
    assert "INSERT OR IGNORE INTO raffle_winners\n            (id, raffle_id" in src


def test_card_subsystem_tables_are_born_clean_single_uuid_identity():
    """The loyalty-card subsystem is born-clean: tarjetas_fidelidad / card_batches
    / card_assignment_history / historico_tarjetas carry a single TEXT UUIDv7 id
    (no integer surrogate, no separate `uuid` column on card_batches), functional
    FKs are TEXT, and neither CardBatchEngine nor TarjetaRepository derive identity
    from autoincrement (no lastrowid, no random integer ids).
    """
    conn = _fresh_base_schema()

    tf = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(tarjetas_fidelidad)").fetchall()}
    assert tf["id"] == ("TEXT", 1)
    assert tf["id_cliente"][0] == "TEXT"
    assert tf["batch_id"][0] == "TEXT"

    cb = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(card_batches)").fetchall()}
    assert cb["id"] == ("TEXT", 1)
    assert "uuid" not in cb                           # doble identidad eliminada

    for table, fk in (("card_assignment_history", "tarjeta_id"), ("historico_tarjetas", "id_tarjeta")):
        cols = {r[1]: (r[2].upper(), r[5]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        assert cols["id"] == ("TEXT", 1)
        assert cols[fk][0] == "TEXT"

    eng_src = (REPO / "core" / "services" / "card_batch_engine.py").read_text(encoding="utf-8")
    assert "from backend.shared.ids import new_uuid" in eng_src
    assert "lastrowid" not in eng_src
    assert "(id, nombre, codigo_inicio, codigo_fin, cantidad," in eng_src  # insert sin columna uuid
    assert "batch_uuid" not in eng_src                                     # doble identidad eliminada

    repo_src = (REPO / "repositories" / "tarjetas.py").read_text(encoding="utf-8")
    assert "from backend.shared.ids import new_uuid" in repo_src
    assert "return new_uuid()" in repo_src
    # La identidad ya no se sortea con un entero aleatorio (el viejo bucle de
    # colisión que sondeaba la DB por un candidate int desapareció).
    assert "candidate = random.randint" not in repo_src


def test_accounting_core_tables_are_born_clean_uuid_identity():
    """El núcleo contable es born-clean: journal_entries / financial_documents /
    financial_trace_log (migración 083) y financial_event_log (052) llevan id TEXT
    UUIDv7 con branch_id/sucursal_id TEXT (sin DEFAULT 1). Los 5 servicios
    canónicos acuñan id con new_uuid() en vez de capturar lastrowid.
    """
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()

    for table in ("journal_entries", "financial_documents", "financial_trace_log", "financial_event_log"):
        cols = {r[1]: (r[2].upper(), r[5]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        assert cols["id"] == ("TEXT", 1), f"{table}.id must be TEXT PRIMARY KEY"
    je = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(journal_entries)").fetchall()}
    assert je["branch_id"] == "TEXT" and je["source_id"] == "TEXT"
    fel = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(financial_event_log)").fetchall()}
    assert fel["sucursal_id"] == "TEXT" and fel["referencia_id"] == "TEXT"

    for path in ("core/services/finance/journal_entry_service.py",
                 "core/services/finance/general_ledger_service.py",
                 "core/services/finance/financial_trace_service.py",
                 "core/services/finance/financial_document_service.py"):
        src = (REPO / path).read_text(encoding="utf-8")
        assert "from backend.shared.ids import new_uuid" in src, path
        assert "new_uuid()" in src and "cur.lastrowid" not in src, path


def test_treasury_tables_are_born_clean_uuid_identity():
    """Tesorería born-clean: treasury_capital / treasury_ledger /
    treasury_gastos_fijos (082), treasury_movements (083) y capital_movements
    (084) llevan id TEXT UUIDv7 con sucursal_id/branch_id y FKs cruzadas
    (source_id, financial_document_id, partner_id, journal_entry_id,
    treasury_movement_id) en TEXT, sin DEFAULT 1. Los 3 servicios de tesorería
    acuñan id con new_uuid() en vez de capturar lastrowid.
    """
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()

    for table in ("treasury_capital", "treasury_ledger", "treasury_gastos_fijos",
                  "treasury_movements", "capital_movements"):
        cols = {r[1]: (r[2].upper(), r[5]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        assert cols["id"] == ("TEXT", 1), f"{table}.id must be TEXT PRIMARY KEY"

    tl = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(treasury_ledger)").fetchall()}
    assert tl["sucursal_id"] == "TEXT"
    tm = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(treasury_movements)").fetchall()}
    assert tm["branch_id"] == "TEXT" and tm["source_id"] == "TEXT"
    assert tm["financial_document_id"] == "TEXT"
    cm = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(capital_movements)").fetchall()}
    assert cm["branch_id"] == "TEXT" and cm["partner_id"] == "TEXT"
    assert cm["journal_entry_id"] == "TEXT" and cm["treasury_movement_id"] == "TEXT"

    # treasury_service.py es multi-tabla: las escrituras de tesorería (capital,
    # ledger, gastos_fijos) acuñan new_uuid(); conserva lastrowid solo en las
    # tablas diferidas (pagos_cobros) de sub-pases posteriores.
    ts_src = (REPO / "core/services/finance/treasury_service.py").read_text(encoding="utf-8")
    assert "from backend.shared.ids import new_uuid" in ts_src
    assert "INSERT INTO treasury_capital" in ts_src and "INSERT INTO treasury_ledger" in ts_src
    # Los dos servicios mono-tabla quedan totalmente born-clean (sin lastrowid).
    for path in ("core/services/finance/treasury_movement_service.py",
                 "core/services/finance/capital_service.py"):
        src = (REPO / path).read_text(encoding="utf-8")
        assert "from backend.shared.ids import new_uuid" in src, path
        assert "new_uuid()" in src, path
        assert "cur.lastrowid" not in src, path
        assert 'int(existing["id"])' not in src, path


def test_gastos_tables_are_born_clean_uuid_identity():
    """Gastos born-clean: gastos / gastos_futuros / gastos_fijos (m000 base)
    llevan id TEXT UUIDv7 con sucursal_id TEXT (sin DEFAULT 1). dia_del_mes
    permanece INTEGER (día-del-mes semántico, no identidad). Los escritores de
    gastos en TreasuryService acuñan new_uuid() y gastos_futuros se define una
    sola vez (la migración 082 ya no la duplica). El CRUD muerto de gastos en
    finance_service (proveedor_id/activo fantasma) fue eliminado (REGLA 3).
    """
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()

    for table in ("gastos", "gastos_futuros", "gastos_fijos"):
        cols = {r[1]: (r[2].upper(), r[5]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        assert cols["id"] == ("TEXT", 1), f"{table}.id must be TEXT PRIMARY KEY"

    gfu = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(gastos_futuros)").fetchall()}
    assert gfu["sucursal_id"] == "TEXT"
    gfi = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(gastos_fijos)").fetchall()}
    assert gfi["sucursal_id"] == "TEXT"
    assert gfi["dia_del_mes"] == "INTEGER"  # día-del-mes semántico, no identidad

    # La migración 082 ya no crea/duplica gastos_futuros.
    mig082 = (REPO / "migrations/standalone/082_treasury_tables.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS gastos_futuros" not in mig082

    # Escritores de gastos en TreasuryService acuñan UUID y no usan lastrowid.
    ts_src = (REPO / "core/services/finance/treasury_service.py").read_text(encoding="utf-8")
    assert "INSERT INTO gastos_futuros(id," in ts_src
    assert "INSERT INTO gastos_fijos" in ts_src and "INSERT INTO gastos (id," in ts_src

    # El CRUD muerto de gastos fue removido de finance_service.
    fs_src = (REPO / "core/services/enterprise/finance_service.py").read_text(encoding="utf-8")
    assert "def upsert_expense" not in fs_src
    assert "g.proveedor_id" not in fs_src


def test_cxp_cxc_tables_are_born_clean_uuid_identity():
    """CxP/CxC born-clean: accounts_payable / accounts_receivable / ap_payments /
    ar_payments (m000 base) y pagos_cobros / pagos_cobros_aplicaciones (082)
    llevan id TEXT UUIDv7. Las FKs a tablas ya flipeadas (cliente_id, sucursal_id,
    ap_id, ar_id, pago_cobro_id, documento_id) y el tercero_id polimórfico van en
    TEXT; supplier_id/venta_id se conservan INTEGER (suppliers/ventas diferidas).
    Los servicios de CxP/CxC acuñan new_uuid() (sin lastrowid) y TreasuryService
    escribe en las tablas canónicas ap_payments/ar_payments (no en las fantasma
    cxp_payments/cxc_payments).
    """
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()

    for table in ("accounts_payable", "accounts_receivable", "ap_payments",
                  "ar_payments", "pagos_cobros", "pagos_cobros_aplicaciones"):
        cols = {r[1]: (r[2].upper(), r[5]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        assert cols["id"] == ("TEXT", 1), f"{table}.id must be TEXT PRIMARY KEY"

    ar = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(accounts_receivable)").fetchall()}
    assert ar["cliente_id"] == "TEXT" and ar["sucursal_id"] == "TEXT"
    assert ar["venta_id"] == "INTEGER"  # ventas diferida
    ap = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(accounts_payable)").fetchall()}
    assert ap["sucursal_id"] == "TEXT" and ap["supplier_id"] == "INTEGER"  # suppliers diferida
    app = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(ap_payments)").fetchall()}
    assert app["ap_id"] == "TEXT"
    pca = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(pagos_cobros_aplicaciones)").fetchall()}
    assert pca["pago_cobro_id"] == "TEXT" and pca["documento_id"] == "TEXT"
    pc = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(pagos_cobros)").fetchall()}
    assert pc["tercero_id"] == "TEXT"

    for path in ("core/services/finance/accounts_payable_service.py",
                 "core/services/finance/accounts_receivable_service.py"):
        src = (REPO / path).read_text(encoding="utf-8")
        assert "from backend.shared.ids import new_uuid" in src, path
        assert "new_uuid()" in src and "cur.lastrowid" not in src, path

    # TreasuryService consolida en las tablas de pago canónicas (no fantasma).
    ts_src = (REPO / "core/services/finance/treasury_service.py").read_text(encoding="utf-8")
    assert "INSERT INTO ap_payments" in ts_src and "INSERT INTO ar_payments" in ts_src
    assert "cxp_payments" not in ts_src and "cxc_payments" not in ts_src
    assert "INSERT INTO pagos_cobros(id," in ts_src


def test_plan_cuentas_natural_key_born_clean():
    """El plan de cuentas (migración 059) es born-clean por clave natural: la
    identidad es codigo_sat (clave SAT) como TEXT PRIMARY KEY, sin surrogate
    entero ni AUTOINCREMENT. El self-ref jerárquico usa padre_codigo (TEXT) hacia
    codigo_sat. El catálogo se siembra por código (sin lastrowid/MAX(id)+1).
    """
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()

    cols = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(plan_cuentas)").fetchall()}
    assert cols, "plan_cuentas missing after migration 059"
    assert "id" not in cols, "no integer surrogate — codigo_sat es la identidad"
    assert cols["codigo_sat"] == ("TEXT", 1), "codigo_sat must be TEXT PRIMARY KEY"
    assert cols["padre_codigo"][0] == "TEXT", "padre_codigo must be TEXT (ref codigo_sat)"

    src = (REPO / "migrations/standalone/059_plan_cuentas.py").read_text(encoding="utf-8")
    assert "AUTOINCREMENT" not in src
    assert "codigo_sat   TEXT    PRIMARY KEY" in src
    assert "lastrowid" not in src


def test_deferred_debt_tables_are_born_clean_uuid_identity():
    """Deuda diferida born-clean (cierre de FINANZAS): activos/depreciación e
    insumos llevan identidad UUIDv7 TEXT. assets/asset_maintenance (base) y
    fixed_assets/asset_depreciation_entries/maintenance_records/
    operating_supplies/reconciliation_records (083) → id TEXT PK; branch_id y
    FKs cruzadas en TEXT (supplier_id se conserva INTEGER, suppliers diferida).
    links_pago abandona la identidad dual (id entero + uuid) por clave natural
    pedido_id TEXT. depreciacion_acumulada (060) ya es UUIDv7. Los 3 servicios
    de trazabilidad acuñan new_uuid() y el CRUD muerto de activos en
    finance_service fue eliminado (REGLA 3).
    """
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()

    for table in ("assets", "asset_maintenance", "fixed_assets",
                  "asset_depreciation_entries", "maintenance_records",
                  "operating_supplies", "reconciliation_records",
                  "depreciacion_acumulada"):
        cols = {r[1]: (r[2].upper(), r[5]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        assert cols["id"] == ("TEXT", 1), f"{table}.id must be TEXT PRIMARY KEY"

    fa = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(fixed_assets)").fetchall()}
    assert fa["branch_id"] == "TEXT" and fa["financial_document_id"] == "TEXT"
    assert fa["supplier_id"] == "INTEGER"  # suppliers diferida
    ade = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(asset_depreciation_entries)").fetchall()}
    assert ade["asset_id"] == "TEXT"

    # links_pago: clave natural pedido_id (sin identidad dual id+uuid).
    lp = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(links_pago)").fetchall()}
    assert "id" not in lp and "uuid" not in lp, "links_pago no debe tener identidad dual"
    assert lp["pedido_id"] == ("TEXT", 1), "links_pago.pedido_id debe ser TEXT PRIMARY KEY"

    for path in ("core/services/finance/fixed_asset_service.py",
                 "core/services/finance/maintenance_finance_service.py",
                 "core/services/finance/operating_supplies_service.py"):
        s = (REPO / path).read_text(encoding="utf-8")
        assert "from backend.shared.ids import new_uuid" in s, path
        assert "new_uuid()" in s and "cur.lastrowid" not in s, path
        assert 'int(existing["id"])' not in s, path

    # El CRUD muerto de activos (phantom cols) fue removido de finance_service.
    fs_src = (REPO / "core/services/enterprise/finance_service.py").read_text(encoding="utf-8")
    assert "def upsert_asset" not in fs_src
    assert "INSERT INTO assets" not in fs_src


def test_rrhh_tables_are_born_clean_uuid_identity():
    """RRHH born-clean: personal / asistencias / nomina_records / nomina_pagos /
    evaluaciones_personal / turno_roles / turno_asignaciones (base) y
    vacaciones_personal / puestos (094) llevan id TEXT UUIDv7. Las FKs
    personal_id / empleado_id / turno_rol_id van en TEXT. Los repositorios
    canónicos (core/rrhh) acuñan new_uuid() (sin lastrowid) y la validación de
    eventos exige identidad TEXT (no entero positivo).
    """
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()

    for table in ("personal", "asistencias", "nomina_records", "nomina_pagos",
                  "evaluaciones_personal", "turno_roles", "turno_asignaciones",
                  "vacaciones_personal", "puestos"):
        cols = {r[1]: (r[2].upper(), r[5]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        assert cols["id"] == ("TEXT", 1), f"{table}.id must be TEXT PRIMARY KEY"

    asis = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(asistencias)").fetchall()}
    assert asis["personal_id"] == "TEXT"
    nom = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(nomina_pagos)").fetchall()}
    assert nom["empleado_id"] == "TEXT"
    asg = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(turno_asignaciones)").fetchall()}
    assert asg["personal_id"] == "TEXT" and asg["turno_rol_id"] == "TEXT"

    repo_src = (REPO / "core/rrhh/infrastructure/sqlite_repositories.py").read_text(encoding="utf-8")
    assert "from backend.shared.ids import new_uuid" in repo_src
    assert "new_uuid()" in repo_src and "int(cur.lastrowid)" not in repo_src

    # La validación de eventos RRHH exige identidad TEXT (no entero positivo).
    events_src = (REPO / "core/rrhh/events.py").read_text(encoding="utf-8")
    assert "_ensure_positive_int" not in events_src


def test_whatsapp_messaging_tables_are_born_clean_uuid_identity():
    """Las tablas de mensajería WhatsApp son born-clean: whatsapp_queue /
    whatsapp_numeros (base) y wa_reminder_queue (migración 050) llevan id TEXT
    UUIDv7. MessageQueue.enqueue y WhatsAppConfigRepository.save_numero acuñan id
    con new_uuid() (sin lastrowid).
    """
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()

    for table in ("whatsapp_queue", "whatsapp_numeros", "wa_reminder_queue"):
        cols = {r[1]: (r[2].upper(), r[5]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        assert cols["id"] == ("TEXT", 1), f"{table}.id must be TEXT PRIMARY KEY"

    wa_src = (REPO / "core" / "services" / "whatsapp_service.py").read_text(encoding="utf-8")
    assert "INSERT INTO whatsapp_queue" in wa_src and "new_uuid()" in wa_src
    assert "return cur.lastrowid" not in wa_src
    repo_src = (REPO / "core" / "repositories" / "whatsapp_config_repository.py").read_text(encoding="utf-8")
    assert "new_uuid()" in repo_src


def test_notification_tables_are_born_clean_uuid_identity():
    """El subsistema de notificaciones es born-clean: notification_inbox y
    turno_notificaciones_log llevan id TEXT UUIDv7, empleado_id/personal_id TEXT y
    sucursal_id TEXT sin DEFAULT 1. Los escritores acuñan id con new_uuid() y el
    CREATE de desktop_notification_service usa el mismo esquema TEXT.
    """
    conn = _fresh_base_schema()
    inbox = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(notification_inbox)").fetchall()}
    assert inbox["id"] == ("TEXT", 1)
    assert inbox["empleado_id"][0] == "TEXT"
    assert inbox["sucursal_id"][0] == "TEXT"

    turno = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(turno_notificaciones_log)").fetchall()}
    assert turno["id"] == ("TEXT", 1)
    assert turno["personal_id"][0] == "TEXT"

    for path in ("core/services/notification_service.py",
                 "core/services/notifications/notification_dispatcher.py",
                 "core/services/desktop_notification_service.py"):
        src = (REPO / path).read_text(encoding="utf-8")
        assert "from backend.shared.ids import new_uuid" in src, path
        assert "INSERT INTO notification_inbox\n            (id," in src or \
               "INSERT INTO notification_inbox\n                   (id," in src, path
    # El CREATE self-heal de desktop usa id TEXT, no autoincrement.
    dsrc = (REPO / "core" / "services" / "desktop_notification_service.py").read_text(encoding="utf-8")
    assert "id TEXT PRIMARY KEY" in dsrc
    assert "id INTEGER PRIMARY KEY AUTOINCREMENT" not in dsrc


def test_hardware_config_keyed_by_natural_tipo():
    """hardware_config es born-clean por clave natural: `tipo` TEXT es la PRIMARY KEY
    (sin surrogate entero), sucursal_id es TEXT sin DEFAULT 1, y las tres
    definiciones del esquema (base, m050, repo.ensure_schema) coinciden.
    """
    conn = _fresh_base_schema()
    hw = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(hardware_config)").fetchall()}
    assert "id" not in hw                             # surrogate entero eliminado
    assert hw["tipo"] == ("TEXT", 1)                  # clave natural es la PK
    assert hw["sucursal_id"][0] == "TEXT"             # sin DEFAULT 1 arbitrario

    repo_src = (REPO / "core" / "repositories" / "hardware_config_repository.py").read_text(encoding="utf-8")
    assert "tipo TEXT PRIMARY KEY" in repo_src
    assert "INTEGER PRIMARY KEY AUTOINCREMENT" not in repo_src
    m050_src = (REPO / "migrations" / "m050_hardware_config_canonical.py").read_text(encoding="utf-8")
    assert "tipo TEXT PRIMARY KEY" in m050_src
    assert "INTEGER PRIMARY KEY AUTOINCREMENT" not in m050_src


def test_etiquetas_module_is_read_only_presentation():
    """El módulo de etiquetas es presentación pura (genera etiquetas imprimibles a
    partir de productos ya migrados): sin tablas propias, sin escrituras ni DDL en
    la UI, y sin casts de identidad. No hay entidad que voltear — se fija así.
    """
    src = (REPO / "modulos" / "etiquetas.py").read_text(encoding="utf-8")
    for forbidden in ("INSERT INTO", "UPDATE ", "DELETE FROM", "CREATE TABLE",
                      "ALTER TABLE", ".commit()"):
        assert forbidden not in src, f"etiquetas.py debe ser solo-lectura: {forbidden!r}"
    # No castea identidades de producto a int (productos.id es UUIDv7 TEXT).
    assert "int(r[0])" not in src
    assert "int(producto" not in src


def test_tickets_print_log_born_clean_and_dead_design_table_removed():
    """The ticket/print surface is born-clean: print_job_log (migración 056) carries
    a TEXT UUIDv7 id minted by printer_service (no autoincrement), and the dead
    ticket_design_config table (0 referencias en código) fue eliminada del base.
    """
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "ticket_design_config" not in tables          # tabla muerta eliminada (REGLA 3)

    migrator.up(conn)
    conn.commit()
    pj = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(print_job_log)").fetchall()}
    assert pj["id"] == ("TEXT", 1)
    assert pj["sucursal_id"][0] == "TEXT"                 # sin DEFAULT 1 arbitrario

    src = (REPO / "core" / "services" / "printer_service.py").read_text(encoding="utf-8")
    assert "from backend.shared.ids import new_uuid" in src
    assert "INSERT INTO print_job_log\n                    (id, job_id" in src


def test_pedidos_whatsapp_tables_are_born_clean_uuid_identity():
    """The WhatsApp order entity is born-clean: pedidos_whatsapp / pedidos_whatsapp_items
    carry a single TEXT UUIDv7 id (the parallel `uuid` column was dropped), FKs are
    TEXT, and all three writers (pedido_wa UC, bot_pedidos, rasa) mint ids with
    new_uuid() instead of capturing lastrowid.
    """
    conn = _fresh_base_schema()
    ped = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(pedidos_whatsapp)").fetchall()}
    assert ped["id"] == ("TEXT", 1)
    assert "uuid" not in ped                          # doble identidad eliminada
    assert ped["cliente_id"][0] == "TEXT"

    it = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(pedidos_whatsapp_items)").fetchall()}
    assert it["id"] == ("TEXT", 1)
    assert it["pedido_id"][0] == "TEXT"

    uc_src = (REPO / "core" / "use_cases" / "pedido_wa.py").read_text(encoding="utf-8")
    assert "lastrowid" not in uc_src
    assert "pedido_id = new_uuid()" in uc_src
    for w in (REPO / "services" / "bot_pedidos.py", REPO / "rasa" / "actions" / "actions.py"):
        src = w.read_text(encoding="utf-8")
        assert "lower(hex(randomblob(16)))" not in src   # ya no se autogenera uuid paralelo
        assert "new_uuid()" in src


def test_reception_tables_are_born_clean_uuid_identity():
    """The reception subsystem is born-clean: recepciones / recepcion_items /
    ordenes_compra / ordenes_compra_items / scan_event_log carry a single TEXT
    UUIDv7 id (ordenes_compra dropped its parallel `uuid` column), and the writers
    (purchase_order_repository, qr_parser_service) mint ids with new_uuid().
    """
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()

    for table, fks in (
        ("recepciones", ("proveedor_id", "sucursal_id")),
        ("recepcion_items", ("recepcion_id", "producto_id")),
        ("ordenes_compra", ("proveedor_id",)),
        ("ordenes_compra_items", ("orden_id", "producto_id")),
        ("scan_event_log", ()),
    ):
        cols = {r[1]: (r[2].upper(), r[5]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        assert cols["id"] == ("TEXT", 1), f"{table}.id must be TEXT PRIMARY KEY"
        for fk in fks:
            assert cols[fk][0] == "TEXT", f"{table}.{fk} must be TEXT"
    oc = {r[1] for r in conn.execute("PRAGMA table_info(ordenes_compra)").fetchall()}
    assert "uuid" not in oc                           # doble identidad eliminada

    po_src = (REPO / "repositories" / "purchase_order_repository.py").read_text(encoding="utf-8")
    assert "lastrowid" not in po_src
    assert "from backend.shared.ids import new_uuid" in po_src

    qr_src = (REPO / "core" / "services" / "qr_parser_service.py").read_text(encoding="utf-8")
    assert "INSERT INTO scan_event_log\n                       (id," in qr_src


def test_compras_tables_are_born_clean_uuid_identity():
    """The purchase transaction is born-clean: compras.id and detalles_compra.id are
    TEXT UUIDv7 primary keys (no autoincrement), the detalle FK compra_id is TEXT,
    and PurchaseRepository mints both ids with new_uuid() (no lastrowid).
    """
    conn = _fresh_base_schema()
    com = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(compras)").fetchall()}
    assert com["id"] == ("TEXT", 1)
    assert com["proveedor_id"][0] == "TEXT"

    det = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(detalles_compra)").fetchall()}
    assert det["id"] == ("TEXT", 1)
    assert det["compra_id"][0] == "TEXT"

    src = (REPO / "repositories" / "purchase_repository.py").read_text(encoding="utf-8")
    assert "lastrowid" not in src
    assert "from backend.shared.ids import new_uuid" in src
    assert "INSERT INTO compras" in src and "INSERT INTO detalles_compra (id," in src


def test_proveedores_table_is_born_clean_uuid_identity():
    """The proveedor entity is born-clean: proveedores.id is a TEXT UUIDv7 primary
    key (no autoincrement), categoria/notas live in the base schema (no DDL emitted
    from UnifiedThirdPartyService — REGLA 11), and both writers (third-party service
    and finance create_supplier_if_not_exists) mint the id with new_uuid().
    """
    conn = _fresh_base_schema()
    prov = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(proveedores)").fetchall()}
    assert prov["id"] == ("TEXT", 1)
    assert "categoria" in prov and "notas" in prov     # plegadas al base (sin DDL en servicio)

    tp_src = (REPO / "core" / "services" / "finance" / "third_party_service.py").read_text(encoding="utf-8")
    assert "ALTER TABLE proveedores" not in tp_src      # DDL fuera del servicio
    assert "_ensure_proveedor_columns" not in tp_src
    assert "INSERT INTO proveedores" in tp_src and "new_uuid" in tp_src

    fin_src = (REPO / "core" / "services" / "enterprise" / "finance_service.py").read_text(encoding="utf-8")
    assert "INSERT INTO proveedores (id, nombre)" in fin_src   # create_supplier acuña id


def test_clientes_table_is_born_clean_uuid_identity():
    """The core customer entity is born-clean: clientes.id is a TEXT UUIDv7 primary
    key (no autoincrement), sucursal_id is TEXT without the arbitrary DEFAULT 1, and
    every writer mints the id with new_uuid() (repo, api, pos_adapter, finance
    dashboard) instead of lastrowid / random integers.
    """
    conn = _fresh_base_schema()
    cli = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(clientes)").fetchall()}
    assert cli["id"] == ("TEXT", 1)
    assert cli["sucursal_id"][0] == "TEXT"        # TEXT sin DEFAULT 1 arbitrario

    repo_src = (REPO / "repositories" / "cliente_repository.py").read_text(encoding="utf-8")
    assert "lastrowid" not in repo_src
    assert "(id, nombre, telefono, email, direccion, notas," in repo_src   # insert con id explícito
    assert "new_uuid()" in repo_src

    # Ningún writer del id de cliente inserta sin id explícito.
    for w in (REPO / "api" / "routers" / "clientes.py",
              REPO / "integrations" / "pos_adapter.py",
              REPO / "core" / "services" / "finance" / "financial_dashboard_service.py"):
        src = w.read_text(encoding="utf-8")
        assert ("INSERT INTO clientes (id," in src) or ("INSERT INTO clientes(id," in src), w.name

    ui_src = (REPO / "modulos" / "clientes.py").read_text(encoding="utf-8")
    assert "QRandomGenerator.global_().bounded(1000, 10000)" not in ui_src   # id aleatorio eliminado
    assert "int(self.tabla_clientes.item(" not in ui_src                     # casts de identidad eliminados


def test_activos_tables_are_born_clean_uuid_identity():
    """The canonical Activos path is born-clean: activos / mantenimientos (base)
    and depreciacion_acumulada (migración 060) carry a TEXT UUIDv7 id with TEXT
    functional FKs, and AssetService mints every id with new_uuid() (no
    autoincrement, no lastrowid). El default arbitrario vida_util_anios=5 se quitó.
    """
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()

    act = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(activos)").fetchall()}
    assert act["id"] == ("TEXT", 1)
    assert act["responsable_id"][0] == "TEXT"

    man = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(mantenimientos)").fetchall()}
    assert man["id"] == ("TEXT", 1)
    assert man["activo_id"][0] == "TEXT"

    dep = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(depreciacion_acumulada)").fetchall()}
    assert dep["id"] == ("TEXT", 1)
    assert dep["activo_id"][0] == "TEXT"

    src = (REPO / "core" / "services" / "asset_service.py").read_text(encoding="utf-8")
    assert "lastrowid" not in src
    assert "INSERT INTO activos (id, nombre" in src
    assert "INSERT INTO mantenimientos (id, activo_id" in src
    assert "INSERT INTO depreciacion_acumulada\n                           (id, activo_id" in src

    base_src = (REPO / "migrations" / "m000_base_schema.py").read_text(encoding="utf-8")
    assert "vida_util_anios     INTEGER DEFAULT 5" not in base_src   # default arbitrario eliminado


def test_cotizaciones_tables_are_born_clean_single_uuid_identity():
    """cotizaciones / cotizaciones_detalle carry a single TEXT UUIDv7 id (no
    integer surrogate, no separate legacy uuid column), FK columns are TEXT, and
    CotizacionService no longer emits DDL nor captures lastrowid.
    """
    conn = _fresh_base_schema()
    cot = {r[1]: (r[2], r[5]) for r in conn.execute("PRAGMA table_info(cotizaciones)").fetchall()}
    assert cot["id"][0].upper() == "TEXT" and cot["id"][1] == 1
    assert "uuid" not in cot                          # dual identity removed
    assert cot["cliente_id"][0].upper() == "TEXT"
    assert cot["sucursal_id"][0].upper() == "TEXT"

    det = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(cotizaciones_detalle)").fetchall()}
    assert det["id"] == "TEXT"
    assert det["cotizacion_id"] == "TEXT"

    src = (REPO / "core" / "services" / "cotizacion_service.py").read_text(encoding="utf-8")
    for ddl in ("CREATE TABLE", "ALTER TABLE", "executescript"):
        assert ddl not in src
    assert "lastrowid" not in src
    assert "cid = new_uuid()" in src


def test_planning_tables_are_born_clean_and_dead_legacy_removed():
    """product_forecast_config is keyed by its natural (product_id, branch_id) as
    TEXT, the dead forecast_cache table is gone, and ScheduledDemandService no
    longer emits DDL (schema belongs to migrations 091/050).
    """
    conn = _fresh_base_schema()
    cfg = {r[1]: (r[2], r[5]) for r in conn.execute("PRAGMA table_info(product_forecast_config)").fetchall()}
    assert "id" not in cfg                            # no integer surrogate
    assert cfg["product_id"][0].upper() == "TEXT" and cfg["product_id"][1] >= 1
    assert cfg["branch_id"][0].upper() == "TEXT"

    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "forecast_cache" not in tables             # dead legacy removed

    src = (REPO / "core" / "services" / "scheduled_demand_service.py").read_text(encoding="utf-8")
    for ddl in ("CREATE TABLE", "ALTER TABLE", "executescript"):
        assert ddl not in src
    assert "new_uuid()" in src                        # wa_event_log id is UUIDv7


def test_production_tables_are_born_clean_and_dead_legacy_removed():
    """producciones / produccion_detalle carry TEXT UUIDv7 identity with no
    arbitrary DEFAULT 1 branch, recipe_engine mints their ids, and the dead
    legacy recetas_consumo* tables are gone from the schema.
    """
    conn = _fresh_base_schema()
    prod = {r[1]: (r[2], r[5], r[4]) for r in conn.execute("PRAGMA table_info(producciones)").fetchall()}
    assert prod["id"][0].upper() == "TEXT" and prod["id"][1] == 1
    assert prod["receta_id"][0].upper() == "TEXT"
    assert prod["sucursal_id"][0].upper() == "TEXT"
    assert prod["sucursal_id"][2] is None       # no arbitrary DEFAULT 1

    det = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(produccion_detalle)").fetchall()}
    assert det["id"] == "TEXT"
    assert det["produccion_id"] == "TEXT"

    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert "recetas_consumo" not in tables           # dead legacy removed
    assert "recetas_consumo_detalle" not in tables

    src = (REPO / "core" / "services" / "recipe_engine.py").read_text(encoding="utf-8")
    assert "produccion_id = new_uuid()" in src


def test_recipe_tables_are_born_clean_and_repo_mints_uuid():
    """product_recipes / product_recipe_components carry TEXT UUIDv7 identity,
    recipe_dependency_graph keys on TEXT, and the recetas repository mints the
    recipe id with new_uuid() — never lastrowid / MAX(id)+1.
    """
    conn = _fresh_base_schema()
    pr = {r[1]: (r[2], r[5]) for r in conn.execute("PRAGMA table_info(product_recipes)").fetchall()}
    assert pr["id"][0].upper() == "TEXT" and pr["id"][1] == 1
    assert pr["product_id"][0].upper() == "TEXT"

    prc = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(product_recipe_components)").fetchall()}
    assert prc["id"] == "TEXT"
    assert prc["recipe_id"] == "TEXT"
    assert prc["component_product_id"] == "TEXT"

    dep = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(recipe_dependency_graph)").fetchall()}
    assert dep["parent_recipe_id"] == "TEXT"

    src = (REPO / "repositories" / "recetas.py").read_text(encoding="utf-8")
    assert "lastrowid" not in src
    assert "from backend.shared.ids import new_uuid" in src
    assert "receta_id = new_uuid()" in src


def test_refresh_order_badges_does_not_int_cast_identity():
    src = (REPO / "interfaz" / "main_window.py").read_text(encoding="utf-8")
    start = src.index("def _refresh_order_badges")
    body = src[start:src.index("\n    def ", start + 1)]
    assert "int(self.usuario_actual" not in body
    assert 'int(self.usuario_actual.get("sucursal_id"' not in body
    assert "branch_id=str(branch_id)" in body


# ── DEBT CEILINGS — must only shrink toward 0 (born-clean) ───────────────────────

# Current measured legacy surface. Lower these as the born-clean rewrite advances.
# Target for all three is 0; raising any of them is a regression and must fail.
INTEGER_PK_TABLE_CEILING = 129
SERVICES_WITH_DDL_CEILING = 20
LASTROWID_FILE_CEILING = 31


def test_integer_pk_tables_in_base_schema_do_not_grow():
    from backend.infrastructure.db.uuid_cutover import find_integer_pks

    conn = _fresh_base_schema()
    count = len(find_integer_pks(conn))
    assert count <= INTEGER_PK_TABLE_CEILING, (
        f"INTEGER PK tables grew to {count} (ceiling {INTEGER_PK_TABLE_CEILING}). "
        "Born-clean target is 0; new tables must be TEXT PRIMARY KEY."
    )


def _service_files_with_ddl() -> list[str]:
    ddl = re.compile(r"CREATE TABLE|ALTER TABLE|DROP TABLE|executescript")
    roots = [REPO / "core" / "services", REPO / "application" / "services"]
    hits = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            if ddl.search(p.read_text(encoding="utf-8")):
                hits.append(str(p.relative_to(REPO)))
    return sorted(hits)


def test_services_emitting_ddl_do_not_grow():
    hits = _service_files_with_ddl()
    assert len(hits) <= SERVICES_WITH_DDL_CEILING, (
        f"Services emitting DDL grew to {len(hits)} (ceiling {SERVICES_WITH_DDL_CEILING}). "
        "Schema belongs in migrations/, not services.\n" + "\n".join(hits)
    )


def test_lastrowid_usage_does_not_grow():
    roots = [REPO / "core", REPO / "repositories", REPO / "application", REPO / "backend"]
    hits = set()
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if "__pycache__" in p.parts or "test" in p.name:
                continue
            if "lastrowid" in p.read_text(encoding="utf-8"):
                hits.add(str(p.relative_to(REPO)))
    assert len(hits) <= LASTROWID_FILE_CEILING, (
        f"lastrowid usage grew to {len(hits)} files (ceiling {LASTROWID_FILE_CEILING}). "
        "Identity must come from backend.shared.ids.new_uuid(), never lastrowid."
    )
