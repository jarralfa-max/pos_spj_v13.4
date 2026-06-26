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
INTEGER_PK_TABLE_CEILING = 157
SERVICES_WITH_DDL_CEILING = 23
LASTROWID_FILE_CEILING = 39


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
