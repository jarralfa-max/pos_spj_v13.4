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

from .architecture_guardrails import code_only_source_lines

REPO = Path(__file__).resolve().parents[2]


def _fresh_base_schema() -> sqlite3.Connection:
    import migrations.m000_base_schema as base

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    return conn


# ── de "este escritor acuña el id" a "nadie inserta sin id" ─────────────────────
#
# Muchas pruebas de abajo comprobaban la propiedad leyendo el CÓDIGO de cada
# escritor conocido: que `repositories/cliente_repository.py` usara `new_uuid()`,
# que `integrations/pos_adapter.py` hiciera `INSERT INTO clientes (id,` … Esos
# archivos se borraron en la reconstrucción, así que las pruebas fallaban con
# `FileNotFoundError`, que no dice absolutamente nada sobre identidad.
#
# La propiedad sigue importando y se comprueba mejor al revés. En vez de nombrar
# a los escritores que había, se buscan TODOS los que hay y se exige que ninguno
# inserte sin `id` explícito. Eso cubre además el código que todavía no existe,
# que es justo donde el fallo volvería a aparecer.
#
# Por qué importa: un INSERT sin `id` en una tabla con clave primaria TEXT no
# falla en SQLite — la fila se crea con la clave vacía, se lee sin problema, y
# sólo revienta mucho más tarde al intentar relacionarla con otra.

_PRODUCTION_ROOTS = ("backend", "frontend")

_INSERT_TEMPLATE = r"INSERT\s+(?:OR\s+\w+\s+)?INTO\s+{table}\b[^\n]*"

#: `id` como PRIMERA columna de la lista. Es como se escribe en todo este
#: repositorio, y buscarla así mantiene la comprobación fiable dentro de una
#: sola línea: las listas de columnas largas siguen en la siguiente y un
#: `\bid\b` suelto acabaría encontrando `producto_id` o `branch_id`.
_EXPLICIT_ID = re.compile(r"\(\s*id\b", re.IGNORECASE)


#: Cuantas lineas siguientes se miran para encontrar la lista de columnas. En
#: este repositorio el SQL se parte en cadenas adyacentes y la lista suele caer
#: en la linea de despues; mirando solo la del INSERT se acusa en falso a quien
#: formatea su SQL en varias lineas, que es casi todo el mundo.
_LOOKAHEAD = 3

def _insert_statements(table: str) -> list[tuple[str, int, str, str]]:
    """`(archivo, línea, sentencia, fuente)` por cada INSERT de producción."""
    patron = re.compile(_INSERT_TEMPLATE.format(table=table), re.IGNORECASE)
    hallazgos: list[tuple[str, int, str]] = []
    for raiz in _PRODUCTION_ROOTS:
        for ruta in (REPO / raiz).rglob("*.py"):
            if "__pycache__" in ruta.parts:
                continue
            texto = ruta.read_text(encoding="utf-8", errors="ignore")
            renglones = texto.splitlines()
            for numero, linea in enumerate(renglones, 1):
                encontrado = patron.search(linea)
                if encontrado:
                    # La sentencia se lleva las lineas siguientes: la lista de
                    # columnas casi nunca cabe en la del INSERT.
                    sentencia = " ".join(
                        r.strip() for r in renglones[numero - 1:numero - 1 + _LOOKAHEAD])
                    hallazgos.append(
                        (str(ruta.relative_to(REPO)), numero, sentencia, texto))
    return hallazgos


def _column_list_starts_with_id(sentencia: str, fuente: str) -> bool:
    """¿La lista de columnas del INSERT empieza por `id`?

    Dos formas, y la segunda me hizo acusar en falso a dos repositorios que
    estaban bien: la lista puede venir escrita —`INSERT INTO x (id, ...)`— o
    INTERPOLADA desde una constante del propio archivo —`INSERT INTO x
    ({_COLUMNS})`—. Mirando sólo la primera, cualquier repositorio que factorice
    sus columnas queda señalado por escribirlas mejor.
    """
    if _EXPLICIT_ID.search(sentencia):
        return True
    interpolada = re.search(r"\(\s*\{(\w+)\}", sentencia)
    if not interpolada:
        return False
    constante = re.search(
        rf"^{interpolada.group(1)}\s*=\s*\(?\s*[\"']\s*id\b",
        fuente, re.MULTILINE | re.IGNORECASE)
    return bool(constante)

def assert_every_writer_mints_the_id(table: str) -> None:
    """Ningún INSERT de producción sobre `table` omite la columna `id`."""
    sin_id = [
        f"{archivo}:{numero}: {sentencia.strip()}"
        for archivo, numero, sentencia, fuente in _insert_statements(table)
        if not _column_list_starts_with_id(sentencia, fuente)
    ]
    assert not sin_id, (
        f"INSERT en `{table}` sin id explícito — la fila nace sin identidad y "
        "sólo falla al relacionarla:\n  " + "\n  ".join(sin_id))


def assert_no_production_writer(table: str) -> None:
    """Nadie escribe ya en `table`.

    Se usa donde el modelo canónico se mudó a otras tablas y la legacy quedó
    sólo como esquema. Afirmarlo es más fuerte que comprobar que el escritor
    que había acuñaba bien el id: lo que hay que impedir es que vuelva a
    escribirse.
    """
    escritores = [f"{a}:{n}: {t.strip()}" for a, n, t, _ in _insert_statements(table)]
    assert not escritores, (
        f"`{table}` volvió a tener escritores; el modelo canónico es otro:\n  "
        + "\n  ".join(escritores))


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


    # Los escritores legacy que esta prueba leía para comprobar que acuñaban
    # el id se borraron; leerlos daba FileNotFoundError, que no dice nada de
    # identidad. Se comprueba sobre los escritores que HAY.
    assert_no_production_writer("bi_transformations")
    assert_no_production_writer("report_export_log")


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
    # Plan B: id TEXT UUIDv7 + unicidad natural (event_id, version); `version`
    # es un ordinal legítimo, no identidad, y ya no forma parte de la PK.
    assert svh["id"] == ("TEXT", 1), "sync_version_history.id debe ser TEXT PK UUIDv7"
    assert svh["event_id"][0] == "TEXT" and svh["version"][0] == "INTEGER"


    # Los escritores legacy que esta prueba leía para comprobar que acuñaban
    # el id se borraron; leerlos daba FileNotFoundError, que no dice nada de
    # identidad. Se comprueba sobre los escritores que HAY.
    assert_no_production_writer("sync_batch_log")
    assert_no_production_writer("sync_version_history")


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


    # Los escritores legacy que esta prueba leía para comprobar que acuñaban
    # el id se borraron; leerlos daba FileNotFoundError, que no dice nada de
    # identidad. Se comprueba sobre los escritores que HAY.
    assert_no_production_writer("loyalty_ledger")


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


    # Los escritores legacy que esta prueba leía para comprobar que acuñaban
    # el id se borraron; leerlos daba FileNotFoundError, que no dice nada de
    # identidad. Se comprueba sobre los escritores que HAY.
    assert_no_production_writer("card_batches")
    assert_every_writer_mints_the_id("tarjetas_fidelidad")


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

    # FASE 20 refactor financiero: journal_entries / journal_lines /
    # financial_documents ahora nacen del bounded context (migración 117) y
    # financial_trace_log fue eliminada (trazabilidad = ledger + outbox).
    for table in ("journal_entries", "journal_lines", "financial_documents",
                  "financial_event_log"):
        cols = {r[1]: (r[2].upper(), r[5]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        assert cols["id"] == ("TEXT", 1), f"{table}.id must be TEXT PRIMARY KEY"
    je = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(journal_entries)").fetchall()}
    assert je["branch_id"] == "TEXT" and je["operation_id"] == "TEXT"
    assert "AUTOINCREMENT" not in (next(iter(conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='journal_entries'").fetchone())) or "").upper()
    fel = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(financial_event_log)").fetchall()}
    assert fel["sucursal_id"] == "TEXT" and fel["referencia_id"] == "TEXT"
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='financial_trace_log'"
    ).fetchone() is None


    # Los servicios legacy que esta prueba leía para verificar que acuñaban
    # el id se borraron en la reconstrucción; leerlos daba FileNotFoundError,
    # que no dice nada sobre identidad. La propiedad se comprueba ahora sobre
    # los escritores que HAY, incluidos los que aún no se han escrito.
    assert_no_production_writer("financial_event_log")
    assert_every_writer_mints_the_id("journal_entries")


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
                  "treasury_movements"):
        cols = {r[1]: (r[2].upper(), r[5]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        assert cols["id"] == ("TEXT", 1), f"{table}.id must be TEXT PRIMARY KEY"

    tl = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(treasury_ledger)").fetchall()}
    assert tl["sucursal_id"] == "TEXT"
    tm = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(treasury_movements)").fetchall()}
    assert tm["branch_id"] == "TEXT" and tm["source_id"] == "TEXT"
    assert tm["financial_document_id"] == "TEXT"


    # Los servicios legacy que esta prueba leía para verificar que acuñaban
    # el id se borraron en la reconstrucción; leerlos daba FileNotFoundError,
    # que no dice nada sobre identidad. La propiedad se comprueba ahora sobre
    # los escritores que HAY, incluidos los que aún no se han escrito.
    assert_no_production_writer("treasury_capital")
    assert_no_production_writer("treasury_ledger")
    assert_no_production_writer("treasury_gastos_fijos")
    assert_no_production_writer("treasury_movements")
    assert_no_production_writer("capital_movements")


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


    # Los servicios legacy que esta prueba leía para verificar que acuñaban
    # el id se borraron en la reconstrucción; leerlos daba FileNotFoundError,
    # que no dice nada sobre identidad. La propiedad se comprueba ahora sobre
    # los escritores que HAY, incluidos los que aún no se han escrito.
    assert_no_production_writer("gastos_fijos")
    assert_no_production_writer("gastos_futuros")


def test_cxp_cxc_tables_are_born_clean_uuid_identity():
    """CxP/CxC born-clean: accounts_payable / accounts_receivable / ap_payments /
    ar_payments (m000 base) y pagos_cobros / pagos_cobros_aplicaciones (082)
    llevan id TEXT UUIDv7. Las FKs a tablas ya flipeadas (cliente_id, sucursal_id,
    ap_id, ar_id, pago_cobro_id, documento_id) y el tercero_id polimórfico van en
    TEXT; supplier_id/venta_id son TEXT (flip global born-clean Plan B).
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
    assert ar["venta_id"] == "TEXT"  # born-clean: ventas ya es TEXT UUIDv7
    ap = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(accounts_payable)").fetchall()}
    assert ap["sucursal_id"] == "TEXT" and ap["supplier_id"] == "TEXT"  # born-clean
    app = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(ap_payments)").fetchall()}
    assert app["ap_id"] == "TEXT"
    pca = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(pagos_cobros_aplicaciones)").fetchall()}
    assert pca["pago_cobro_id"] == "TEXT" and pca["documento_id"] == "TEXT"
    pc = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(pagos_cobros)").fetchall()}
    assert pc["tercero_id"] == "TEXT"


    # Los servicios legacy que esta prueba leía para verificar que acuñaban
    # el id se borraron en la reconstrucción; leerlos daba FileNotFoundError,
    # que no dice nada sobre identidad. La propiedad se comprueba ahora sobre
    # los escritores que HAY, incluidos los que aún no se han escrito.
    assert_no_production_writer("accounts_payable")
    assert_no_production_writer("accounts_receivable")
    assert_no_production_writer("ap_payments")
    assert_no_production_writer("pagos_cobros")


def test_plan_cuentas_natural_key_born_clean():
    """FASE 20 refactor financiero: plan_cuentas fue sustituida por la tabla
    canónica `accounts` del bounded context (código natural único + id UUIDv7).
    Una DB nueva no debe contener plan_cuentas."""
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()

    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='plan_cuentas'"
    ).fetchone() is None, "plan_cuentas debe desaparecer (117)"
    cols = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(accounts)").fetchall()}
    assert cols["id"] == ("TEXT", 1)
    assert cols["code"][0] == "TEXT"

def test_deferred_debt_tables_are_born_clean_uuid_identity():
    """Deuda diferida born-clean (cierre de FINANZAS): activos/depreciación e
    insumos llevan identidad UUIDv7 TEXT. assets/asset_maintenance (base) y
    fixed_assets/asset_depreciation_entries/maintenance_records/
    operating_supplies/reconciliation_records (083) → id TEXT PK; branch_id y
    FKs cruzadas en TEXT (supplier_id incluido: flip global born-clean Plan B).
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
                  "depreciacion_acumulada"):
        cols = {r[1]: (r[2].upper(), r[5]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        assert cols["id"] == ("TEXT", 1), f"{table}.id must be TEXT PRIMARY KEY"

    # FASE 20: fixed_assets pertenece al bounded context financiero (117);
    # las tablas de traza 083 (asset_depreciation_entries, maintenance_records,
    # operating_supplies, reconciliation_records) fueron eliminadas.
    fa = {r[1]: r[2].upper() for r in conn.execute("PRAGMA table_info(fixed_assets)").fetchall()}
    assert fa["branch_id"] == "TEXT" and fa["operation_id"] == "TEXT"
    for gone in ("asset_depreciation_entries", "maintenance_records",
                 "operating_supplies", "reconciliation_records"):
        assert conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (gone,)
        ).fetchone() is None, f"{gone} debe desaparecer (117)"

    # links_pago: clave natural pedido_id (sin identidad dual id+uuid).
    lp = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(links_pago)").fetchall()}
    assert "id" not in lp and "uuid" not in lp, "links_pago no debe tener identidad dual"
    assert lp["pedido_id"] == ("TEXT", 1), "links_pago.pedido_id debe ser TEXT PRIMARY KEY"


    # Los servicios legacy que esta prueba leía para verificar que acuñaban
    # el id se borraron en la reconstrucción; leerlos daba FileNotFoundError,
    # que no dice nada sobre identidad. La propiedad se comprueba ahora sobre
    # los escritores que HAY, incluidos los que aún no se han escrito.
    assert_no_production_writer("links_pago")
    assert_every_writer_mints_the_id("fixed_assets")


def test_rrhh_tables_are_born_clean_uuid_identity():
    """RRHH born-clean: el bounded context de Recursos Humanos
    (backend/domain/hr, backend/infrastructure/db/schema/hr_schema.py) nace con
    identidad TEXT UUIDv7 en todas sus tablas. No hay tablas ni repositorios
    legacy (core/rrhh eliminado); los use cases acuñan new_uuid() sin lastrowid.
    """
    from backend.infrastructure.db.schema.hr_schema import create_hr_schema

    conn = sqlite3.connect(":memory:")
    create_hr_schema(conn)
    conn.commit()

    for table in ("employees", "hr_departments", "hr_positions",
                  "attendance_workdays", "attendance_punches",
                  "attendance_adjustments", "work_shifts", "shift_assignments",
                  "leave_requests", "payroll_runs", "payroll_lines",
                  "payroll_payments"):
        cols = {r[1]: (r[2].upper(), r[5])
                for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        assert cols["id"] == ("TEXT", 1), f"{table}.id must be TEXT PRIMARY KEY"

    # Foreign identities travel as TEXT (never integer functional ids).
    punches = {r[1]: r[2].upper()
               for r in conn.execute("PRAGMA table_info(attendance_punches)").fetchall()}
    assert punches["employee_id"] == "TEXT" and punches["workday_id"] == "TEXT"
    lines = {r[1]: r[2].upper()
             for r in conn.execute("PRAGMA table_info(payroll_lines)").fetchall()}
    assert lines["payroll_run_id"] == "TEXT" and lines["employee_id"] == "TEXT"

    # No legacy HR package survives the migration.
    assert not (REPO / "core/rrhh").exists()
    assert not (REPO / "core/services/rrhh_service.py").exists()

    # Payroll identities are minted with new_uuid(), never lastrowid.
    payroll_src = (REPO / "backend/application/use_cases/hr/payroll_use_cases.py"
                   ).read_text(encoding="utf-8")
    assert "from backend.shared.ids import new_uuid" in payroll_src
    assert "lastrowid" not in payroll_src


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


    # Los escritores legacy que esta prueba leía para comprobar que acuñaban
    # el id se borraron; leerlos daba FileNotFoundError, que no dice nada de
    # identidad. Se comprueba sobre los escritores que HAY.
    assert_every_writer_mints_the_id("notification_inbox")
    assert_no_production_writer("turno_notificaciones_log")


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


    # Los escritores legacy que esta prueba leía para comprobar que acuñaban
    # el id se borraron; leerlos daba FileNotFoundError, que no dice nada de
    # identidad. Se comprueba sobre los escritores que HAY.
    assert_no_production_writer("hardware_config")


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


    # Los escritores legacy que esta prueba leía para comprobar que acuñaban
    # el id se borraron; leerlos daba FileNotFoundError, que no dice nada de
    # identidad. Se comprueba sobre los escritores que HAY.
    assert_no_production_writer("print_job_log")


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


    # Los escritores legacy que esta prueba leía para comprobar que acuñaban
    # el id se borraron; leerlos daba FileNotFoundError, que no dice nada de
    # identidad. Se comprueba sobre los escritores que HAY.
    assert_no_production_writer("pedidos_whatsapp")
    assert_no_production_writer("pedidos_whatsapp_items")


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

    po_src = (REPO / "backend" / "infrastructure" / "db" / "repositories" /
              "procurement" / "purchase_order_repository.py").read_text(encoding="utf-8")
    assert "lastrowid" not in po_src
    assert "from backend.shared.ids import new_uuid" in po_src


    # Los escritores legacy que esta prueba leía para comprobar que acuñaban
    # el id se borraron; leerlos daba FileNotFoundError, que no dice nada de
    # identidad. Se comprueba sobre los escritores que HAY.
    assert_no_production_writer("ordenes_compra")


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

    src = (REPO / "backend" / "infrastructure" / "db" / "repositories" /
           "procurement" / "direct_purchase_repository.py").read_text(encoding="utf-8")
    assert "lastrowid" not in src
    assert "direct_purchases" in src and "direct_purchase_lines" in src


def test_proveedores_table_is_born_clean_uuid_identity():
    """`proveedores` quedo como esquema sin escritores; el proveedor vive en
    `supplier_master`.

    Esta prueba leia `core/services/enterprise/finance_service.py` para
    comprobar que su `create_supplier` acunaba el id. Ese archivo se borro, y
    con el el ultimo escritor: hoy NADIE inserta en `proveedores` en todo el
    arbol de produccion. El contexto canonico de proveedores tiene sus propias
    16 tablas (`supplier_master` y companhia) con sus repositorios.

    Asi que lo que hay que vigilar cambio de sitio: que la tabla legacy no
    vuelva a escribirse por detras, en paralelo al modelo canonico. Eso son dos
    fuentes de verdad para el mismo proveedor, y no da ningun error.
    """
    conn = _fresh_base_schema()
    prov = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(proveedores)").fetchall()}
    assert prov["id"] == ("TEXT", 1)
    assert "categoria" in prov and "notas" in prov     # plegadas al base (sin DDL en servicio)

    # FASE 20: third_party_service fue eliminado (terceros viven en el
    # bounded context financiero); no debe reaparecer.
    assert not (REPO / "core" / "services" / "finance" / "third_party_service.py").exists()

    assert_no_production_writer("proveedores")


def test_clientes_table_is_born_clean_uuid_identity():
    """`clientes.id` es TEXT UUIDv7 y ningun escritor inserta sin id.

    Antes esto se comprobaba leyendo el codigo de los escritores que habia
    —`repositories/cliente_repository.py`, `integrations/pos_adapter.py`,
    `api/routers/clientes.py`—, los tres borrados. La propiedad se comprueba
    ahora sobre los escritores que HAY, sean cuales sean: hoy
    `create_customer_use_case.py` y el puente de identidad legacy, y manana
    los que se escriban.
    """
    conn = _fresh_base_schema()
    cli = {r[1]: (r[2].upper(), r[5]) for r in conn.execute("PRAGMA table_info(clientes)").fetchall()}
    assert cli["id"] == ("TEXT", 1)
    assert cli["sucursal_id"][0] == "TEXT"        # TEXT sin DEFAULT 1 arbitrario

    assert_every_writer_mints_the_id("clientes")

    # Debe haber AL MENOS uno: si la tabla se quedara sin escritores, la
    # comprobacion de arriba pasaria sin mirar nada y este test se volveria
    # decorativo sin avisar.
    assert _insert_statements("clientes"), (
        "Nadie inserta ya en `clientes`: si el modelo canonico se mudo, cambia "
        "esta prueba por `assert_no_production_writer`.")


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


    # Los escritores legacy que esta prueba leía para comprobar que acuñaban
    # el id se borraron; leerlos daba FileNotFoundError, que no dice nada de
    # identidad. Se comprueba sobre los escritores que HAY.
    assert_no_production_writer("activos")
    assert_no_production_writer("depreciacion_acumulada")
    assert_no_production_writer("mantenimientos")


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


    # Los escritores legacy que esta prueba leía para comprobar que acuñaban
    # el id se borraron; leerlos daba FileNotFoundError, que no dice nada de
    # identidad. Se comprueba sobre los escritores que HAY.
    assert_no_production_writer("cotizaciones")
    assert_no_production_writer("cotizaciones_detalle")


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


    # Los escritores legacy que esta prueba leía para comprobar que acuñaban
    # el id se borraron; leerlos daba FileNotFoundError, que no dice nada de
    # identidad. Se comprueba sobre los escritores que HAY.
    assert_no_production_writer("product_forecast_config")


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


    # Los escritores legacy que esta prueba leía para comprobar que acuñaban
    # el id se borraron; leerlos daba FileNotFoundError, que no dice nada de
    # identidad. Se comprueba sobre los escritores que HAY.
    assert_no_production_writer("produccion_detalle")
    assert_no_production_writer("producciones")


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


    # Los escritores legacy que esta prueba leía para comprobar que acuñaban
    # el id se borraron; leerlos daba FileNotFoundError, que no dice nada de
    # identidad. Se comprueba sobre los escritores que HAY.
    assert_no_production_writer("product_recipe_components")
    assert_no_production_writer("product_recipes")
    assert_no_production_writer("recipe_dependency_graph")


def test_refresh_order_badges_does_not_int_cast_identity():
    src = (REPO / "interfaz" / "main_window.py").read_text(encoding="utf-8")
    start = src.index("def _refresh_order_badges")
    body = src[start:src.index("\n    def ", start + 1)]
    assert "int(self.usuario_actual" not in body
    assert 'int(self.usuario_actual.get("sucursal_id"' not in body
    assert "branch_id=str(branch_id)" in body


# ── CERO TOLERANCIA — Plan B born-clean UUIDv7 (sin techos de deuda) ─────────────
#
# Los antiguos techos (INTEGER_PK_TABLE_CEILING / SERVICES_WITH_DDL_CEILING /
# LASTROWID_FILE_CEILING) fueron reemplazados por criterio CERO: una DB nueva
# debe nacer UUIDv7 limpia y find_integer_pks(conn) debe devolver {} tras el
# bootstrap normal. No hay deuda tolerada; toda excepción vive en una allowlist
# mínima, explícita y justificada.

# Columnas *_id que NO son identidad de dominio (ordinales/técnicas), por tabla.
_NON_IDENTITY_ID_COLS = {
    "device_version", "event_version",
}

# DDL fuera de migrations/ permitido SOLO aquí (bootstrap centralizado aprobado
# o herramienta excepcional), con justificación:
DDL_ALLOWLIST = {
    # Herramienta excepcional de conservación de datos (producción); NO es el
    # flujo normal de desarrollo. Reescribe tablas por diseño.
    "backend/infrastructure/db/uuid_cutover.py",
    # Bootstrap centralizado aprobado: espejo del esquema canónico para
    # conexiones nuevas (invoca migraciones, no define entidades propias).
    # Migrador de esquema delivery: infra de schema (pendiente de fusión a
    # migrations/), no lógica de negocio.
    # DDL canónico del bounded context financiero: única definición del esquema,
    # ejecutado exclusivamente por migrations/standalone/117.
    "backend/infrastructure/db/schema/finance_schema.py",
    # DDL canónico del bounded context de Recursos Humanos: única definición del
    # esquema, ejecutado exclusivamente por migrations/standalone/118.
    "backend/infrastructure/db/schema/hr_schema.py",
    # DDL canónico del bounded context de Proveedores: única definición del
    # esquema, ejecutado exclusivamente por migrations/standalone/119.
    "backend/infrastructure/db/schema/supplier_schema.py",
    # DDL canónico del bounded context de Compras/Procurement: única definición
    # del esquema, ejecutado exclusivamente por migrations/standalone/120.
    "backend/infrastructure/db/schema/procurement_schema.py",
}

# lastrowid permitido SOLO aquí (nunca como identidad de dominio):
LASTROWID_ALLOWLIST: set[str] = set()

# int(..._id)/int(..sucursal/branch..) permitido SOLO aquí:
INT_CAST_ALLOWLIST: set[str] = set()

_DOMAIN_ROOTS = (
    "core", "repositories", "backend", "application",
    "modulos", "interfaz", "sync", "webapp", "delivery", "services", "security",
)


def _bootstrap_full() -> sqlite3.Connection:
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()
    return conn


def _domain_files():
    for root in _DOMAIN_ROOTS:
        base = REPO / root
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if "__pycache__" in p.parts or "test" in p.name:
                continue
            yield p


def _is_functional_fk(col: str) -> bool:
    c = col.lower()
    return c != "id" and c.endswith("_id") and c not in _NON_IDENTITY_ID_COLS


def test_fresh_base_schema_has_no_integer_primary_keys():
    """CERO: m000_base_schema.up sola no debe producir ninguna PK entera."""
    from backend.infrastructure.db.uuid_cutover import find_integer_pks

    conn = _fresh_base_schema()
    bad = find_integer_pks(conn)
    assert bad == {}, (
        f"{len(bad)} tablas con PK entera tras m000 (deben ser 0): {sorted(bad)}"
    )


def test_full_migration_chain_has_no_integer_primary_keys():
    """CERO: bootstrap normal completo (m000 + engine) sin PK enteras."""
    from backend.infrastructure.db.uuid_cutover import find_integer_pks

    conn = _bootstrap_full()
    bad = find_integer_pks(conn)
    assert bad == {}, (
        f"{len(bad)} tablas con PK entera tras la cadena completa (deben ser 0): {sorted(bad)}"
    )


def test_active_schema_has_no_autoincrement():
    """CERO: ninguna tabla del schema activo usa AUTOINCREMENT."""
    conn = _bootstrap_full()
    offenders = [
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE '%AUTOINCREMENT%'"
        ).fetchall()
    ]
    assert not offenders, f"AUTOINCREMENT en schema activo: {sorted(offenders)}"


def test_active_schema_has_no_functional_integer_fks():
    """CERO: ninguna columna funcional *_id es INTEGER/INT en el schema activo."""
    conn = _bootstrap_full()
    offenders: list[str] = []
    for (table,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        " AND name NOT LIKE 'schema_%'"
    ).fetchall():
        for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall():
            col, ctype = row[1], (row[2] or "").upper()
            if _is_functional_fk(col) and ctype in ("INTEGER", "INT"):
                offenders.append(f"{table}.{col}")
    assert not offenders, (
        f"{len(offenders)} FK funcionales INTEGER (deben ser 0): {sorted(offenders)}"
    )


def test_active_schema_has_no_default_one_on_functional_fks():
    """CERO: ninguna FK funcional lleva DEFAULT 1 (centinela arbitrario)."""
    conn = _bootstrap_full()
    offenders: list[str] = []
    for (table,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        " AND name NOT LIKE 'schema_%'"
    ).fetchall():
        for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall():
            col, dflt = row[1], row[4]
            if _is_functional_fk(col) and dflt is not None:
                if str(dflt).strip("()\"' ") == "1":
                    offenders.append(f"{table}.{col}")
    assert not offenders, (
        f"FK funcionales con DEFAULT 1 (deben ser 0): {sorted(offenders)}"
    )


def test_domain_code_has_no_lastrowid_identity():
    """CERO: lastrowid no existe en código de dominio (identidad = new_uuid())."""
    hits = []
    for p in _domain_files():
        rel = p.relative_to(REPO).as_posix()      # mismo motivo que arriba
        if rel in LASTROWID_ALLOWLIST:
            continue
        # Sin comentarios ni cadenas: `meat_processing_schema.py` PROMETE en su
        # docstring "no lastrowid" y la guardia contaba la promesa como el uso.
        # Es el mismo vicio que ya corrigio `code_only_source_lines` en su
        # propio docstring: los guardrails de IDENTIFICADOR deben usarlo.
        codigo = chr(10).join(t for _n, t in code_only_source_lines(p))
        if "lastrowid" in codigo:
            hits.append(rel)
    assert not hits, (
        f"{len(hits)} archivos de dominio usan lastrowid (deben ser 0):\n"
        + "\n".join(sorted(hits))
    )


def test_domain_code_has_no_integer_casts_for_entity_ids():
    """CERO: sin int(..._id) ni int(..sucursal/branch..) sobre identidades."""
    rx_id = re.compile(r"(?<![\w])int\(\s*[^)\n]*_id\b")
    rx_branch = re.compile(r"(?<![\w])int\(\s*[^)\n]*(?:sucursal|branch)")
    hits = []
    for p in _domain_files():
        rel = str(p.relative_to(REPO))
        if rel in INT_CAST_ALLOWLIST:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for i, line in enumerate(text.splitlines(), 1):
            if rx_id.search(line) or rx_branch.search(line):
                hits.append(f"{rel}:{i}: {line.strip()[:100]}")
    assert not hits, (
        f"{len(hits)} casts int() sobre identidades (deben ser 0):\n"
        + "\n".join(hits[:60])
    )


#: El hogar declarado del DDL. Cada archivo de ahí existe PARA definir tablas y
#: lo dice en su propio docstring ("Only a migration in migrations/ may execute
#: this DDL"). Incluirlos en la regla "servicios/repositorios/UI no crean
#: esquema" señalaba 36 archivos por hacer aquello para lo que fueron escritos,
#: y ahogaba los 4 hallazgos de verdad entre ellos.
#:
#: La regla que SÍ les aplica es la de abajo: definir DDL es su trabajo,
#: EJECUTARLO fuera de una migración no.
_SCHEMA_PACKAGE = "backend/infrastructure/db/schema/"

#: Llamadas a `create_*_schema(...)` en código de producción, fuera de
#: `migrations/`. Medidas hoy; sólo pueden DESAPARECER.
#:
#: Las dos son el mismo atajo, y su comentario lo dice sin disimulo: "idempotent
#: bootstrap so the schema exists even on a dev DB opened before migration N
#: ran". Crea las tablas al abrir la pantalla, así que `schema_version` no las
#: registra y la migración que no corrió deja de notarse — que es justo lo que
#: hace falta notar. Y una comodidad de desarrollo queda corriendo en producción.
_RUNTIME_SCHEMA_BOOTSTRAPS = frozenset({
    "frontend/desktop/modules/finance/suppliers/supplier_routes.py",
    "frontend/desktop/modules/hr/hr_routes.py",
})

_SCHEMA_CALL = re.compile(r"\bcreate_[a-z_]+_schema\s*\(")


def test_only_migrations_execute_schema_creation():
    """Definir DDL es trabajo del paquete de esquema; ejecutarlo, de migrations/.

    Una pantalla que crea sus propias tablas al abrirse no falla nunca: la
    primera vez las crea y a partir de ahí todo funciona. Lo que se pierde es
    la señal — si la migración no corrió, nadie se entera, y el esquema pasa a
    depender de qué pantallas se hayan abierto y en qué orden.
    """
    llamadores = set()
    for raiz in ("backend", "frontend"):
        for ruta in (REPO / raiz).rglob("*.py"):
            if "__pycache__" in ruta.parts:
                continue
            rel = str(ruta.relative_to(REPO)).replace("\\", "/")
            if rel.startswith(_SCHEMA_PACKAGE):
                continue                      # ahí se DEFINEN, no se ejecutan
            texto = ruta.read_text(encoding="utf-8", errors="ignore")
            for linea in texto.splitlines():
                if _SCHEMA_CALL.search(linea) and not linea.lstrip().startswith(
                        ("def ", "#", "from ", "import ")):
                    llamadores.add(rel)
                    break

    nuevos = sorted(llamadores - _RUNTIME_SCHEMA_BOOTSTRAPS)
    assert not nuevos, (
        "Código de producción que crea esquema al vuelo, fuera de migrations/:\n  "
        + "\n  ".join(nuevos))

    resueltos = sorted(_RUNTIME_SCHEMA_BOOTSTRAPS - llamadores)
    assert not resueltos, (
        "Ya no crean esquema al vuelo; quítalos de _RUNTIME_SCHEMA_BOOTSTRAPS "
        f"para que el trinquete baje: {resueltos}")


def test_services_repositories_ui_do_not_create_schema():
    """CERO: DDL vive en migrations/ (o allowlist aprobada), nunca en
    servicios/repositorios/UI/módulos."""
    # Exige un NOMBRE detras del DDL y que `executescript` sea una LLAMADA.
    # Sin lo primero se marcaba la prosa que HABLA de DDL — un docstring que
    # promete "never a CREATE TABLE/INSERT/UPDATE against it" contaba como si lo
    # hiciera. Sin lo segundo se marcaba `def executescript(...)`, que son
    # metodos pasarela de la conexion, no esquema.
    ddl = re.compile(
        r"(?:CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE)\s+"
        # `(?!IF\b)`: sin el, `CREATE TABLE IF NOT EXISTS` escrito en prosa
        # casaba con la `I` de "IF", porque el grupo opcional simplemente no se
        # consumia. La guardia marcaba docstrings que EXPLICAN el DDL.
        r"(?:IF\s+(?:NOT\s+)?EXISTS\s+)?(?!IF\b)[\w\"'{\[]"
        r"|CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?[\w\"'{\[]"
    )
    # `executescript(` ya no se busca por si mismo. Marcaba tres cosas que no
    # son esquema: el bloque de PRAGMAs con el que la conexion se configura, y
    # dos metodos PASARELA que reenvian la llamada (`return
    # self._conn.executescript(*args, **kwargs)`). Un `executescript` que SI
    # lleve DDL lo caza igualmente la expresion de arriba, este donde este
    # escrito — asi que no se pierde nada y se dejan de acusar tuberias.
    hits = []
    for p in _domain_files():
        # Barras NORMALES: las listas se escriben con "/" y en Windows
        # `relative_to` devuelve "\\". La comparacion no coincidia nunca, asi
        # que la lista de excepciones llevaba siendo INERTE en Windows y la
        # guardia reportaba archivos ya aprobados —`uuid_cutover.py` entre
        # ellos— ahogando los hallazgos de verdad.
        rel = p.relative_to(REPO).as_posix()
        if rel in DDL_ALLOWLIST:
            continue
        if rel.startswith(_SCHEMA_PACKAGE):
            continue   # su trabajo es definir DDL; ver la regla de ejecucion
        if ddl.search(p.read_text(encoding="utf-8", errors="ignore")):
            hits.append(rel)
    assert not hits, (
        f"{len(hits)} archivos de dominio emiten DDL (deben ser 0):\n"
        + "\n".join(sorted(hits))
    )
