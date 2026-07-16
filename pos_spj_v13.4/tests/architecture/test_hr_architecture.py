"""FASE 11 — architecture guardrails for the HR bounded context.

The HR module must obey clean architecture and the born-clean identity rules:
- The UI (frontend/desktop/modules/hr) executes no SQL, imports no sqlite3, no
  repositories, no DB connection and no legacy HR services.
- No legacy HR implementation survives: no logic in modulos/rrhh*.py, no
  core/rrhh package, no core/services/rrhh*.py, no core/use_cases/nomina.py.
- Every HR schema table is born with a TEXT UUIDv7 primary key.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
HR_UI = REPO / "frontend/desktop/modules/hr"

_FORBIDDEN_UI_IMPORTS = re.compile(
    r"^\s*(?:import\s+sqlite3"
    r"|from\s+sqlite3\b"
    r"|from\s+core\.db\b"
    r"|import\s+core\.db\b"
    r"|from\s+backend\.infrastructure\.db\.repositories"
    r"|from\s+core\.services\.rrhh"
    r"|from\s+core\.rrhh\b"
    r"|from\s+core\.use_cases\.nomina\b)",
    re.MULTILINE,
)
_SQL = re.compile(r"\b(SELECT|INSERT\s+INTO|UPDATE\s+\w|DELETE\s+FROM|CREATE\s+TABLE|"
                  r"ALTER\s+TABLE|DROP\s+TABLE)\b", re.IGNORECASE)
_COMMIT_ROLLBACK = re.compile(r"\.(commit|rollback)\s*\(")


def _hr_ui_files() -> list[Path]:
    return [p for p in HR_UI.rglob("*.py") if "__pycache__" not in p.parts]


def test_hr_ui_module_exists_in_target_structure():
    assert HR_UI.is_dir(), "HR UI must live in frontend/desktop/modules/hr/"
    assert (HR_UI / "hr_view.py").exists()
    assert (HR_UI / "hr_presenter.py").exists()
    assert (HR_UI / "hr_routes.py").exists()


def test_hr_ui_does_not_import_sql_or_repositories():
    offenders = []
    for path in _hr_ui_files():
        text = path.read_text(encoding="utf-8")
        if _FORBIDDEN_UI_IMPORTS.search(text):
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, f"HR UI imports forbidden infrastructure: {offenders}"


def test_hr_ui_has_no_sql_or_transactions():
    offenders = []
    for path in _hr_ui_files():
        text = path.read_text(encoding="utf-8")
        if _SQL.search(text) or _COMMIT_ROLLBACK.search(text):
            offenders.append(str(path.relative_to(REPO)))
    assert not offenders, f"HR UI contains SQL or commit/rollback: {offenders}"


def test_legacy_hr_implementation_is_removed():
    assert not (REPO / "core/rrhh").exists()
    assert not (REPO / "core/services/rrhh_service.py").exists()
    assert not (REPO / "core/services/rrhh_catalog_service.py").exists()
    assert not (REPO / "core/services/rrhh_turnos_service.py").exists()
    assert not (REPO / "core/services/hr_rule_engine.py").exists()
    assert not (REPO / "core/use_cases/nomina.py").exists()
    assert not (REPO / "modulos/rrhh_turnos.py").exists()


def test_modulos_rrhh_is_a_thin_wrapper():
    """modulos/rrhh.py may only re-export the new view; no logic, SQL or styles."""
    text = (REPO / "modulos/rrhh.py").read_text(encoding="utf-8")
    assert "create_hr_view" in text
    assert _SQL.search(text) is None
    assert "QWidget" not in text or text.count("\n") < 40  # no rich UI, just a wrapper
    assert len(text.splitlines()) < 40


def test_hr_schema_tables_are_born_clean_uuid_identity():
    from backend.infrastructure.db.schema.hr_schema import HR_TABLES, create_hr_schema

    conn = sqlite3.connect(":memory:")
    create_hr_schema(conn)
    for table in HR_TABLES:
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        # r = (cid, name, type, notnull, default, pk)
        pk_cols = [(r[1], r[2].upper()) for r in info if r[5] > 0]
        assert len(pk_cols) == 1, f"{table} must have exactly one primary key column"
        name, col_type = pk_cols[0]
        assert col_type == "TEXT", f"{table}.{name} PK must be TEXT UUIDv7, got {col_type}"
    conn.close()


def test_hr_use_cases_mint_uuid_not_lastrowid():
    uc_dir = REPO / "backend/application/use_cases/hr"
    for path in uc_dir.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        assert "lastrowid" not in text, f"{path.name} must not use lastrowid identity"
