"""FASE 0 — architecture guard-rail baseline for the PRODUCTOS module.

Unlike MERMA (which arrived nearly clean), PRODUCTOS is still heavy legacy:
the PyQt UI runs raw SQL + commit(), casts identities with int(...), uses a
hardcoded sucursal default of 1, and an "application service" commits directly.

This ratchet freezes the CURRENT violation counts as a baseline. It does NOT
clean the module — it blocks NEW violations and lets the F7 refactor drive the
numbers down (each reduction must be mirrored here). Pair with behavioural
product tests once they exist.
"""

from __future__ import annotations

import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]

UI_FILES = ["modulos/productos.py"]
BACKEND_FILES = [
    "backend/application/commands/product_commands.py",
    "backend/application/queries/product_query_service.py",
    "backend/application/services/product_catalog_service.py",
    "backend/application/services/product_image_service.py",
    "backend/application/use_cases/create_product_use_case.py",
    "backend/application/use_cases/update_product_use_case.py",
    "backend/application/use_cases/deactivate_product_use_case.py",
    "backend/application/use_cases/restore_product_use_case.py",
    "backend/infrastructure/db/repositories/product_repository.py",
]
SCOPE_FILES = UI_FILES + BACKEND_FILES

PATTERNS: dict[str, re.Pattern[str]] = {
    "cursor_execute": re.compile(
        r"(cursor|cur|conn|self\.db|self\.conn|self\._conn|self\.conexion|self\.container\.db)\.execute"
    ),
    "commit": re.compile(r"\.commit\(\)"),
    "rollback": re.compile(r"\.rollback\(\)"),
    "sql_select": re.compile(r"\bSELECT\s", re.I),
    "sql_insert": re.compile(r"\bINSERT\s+INTO", re.I),
    "sql_update": re.compile(r"\bUPDATE\s+\w", re.I),
    "create_table": re.compile(r"CREATE\s+TABLE", re.I),
    "autoincrement": re.compile(r"AUTOINCREMENT", re.I),
    "integer_pk": re.compile(r"INTEGER\s+PRIMARY\s+KEY", re.I),
    "lastrowid": re.compile(r"lastrowid", re.I),
    "int_id_cast": re.compile(r"int\(\s*[\w\.]*_id|int\(\s*producto_id|int\(\s*item_id"),
    "int_str_contract": re.compile(r"int \| str|str \| int"),
    "uuid4": re.compile(r"uuid4"),
    "arbitrary_branch_default": re.compile(
        r"(branch_id|sucursal_id)\s*=\s*1\b"
        r"|(branch_id|sucursal_id)[\"']?\s*,\s*[\"']?1[\"']?"
    ),
    "external": re.compile(r"\bimport\s+(smtplib|serial|urllib|socket|subprocess)\b"),
}

# Documented FASE 0 baseline (measured 2026-06). Drive every number DOWN.
BASELINE: dict[str, dict[str, int]] = {
    "modulos/productos.py": {
        "cursor_execute": 11,
        "commit": 2,
        "sql_select": 8,
        "sql_insert": 2,
        "sql_update": 2,
        "int_id_cast": 6,
        "uuid4": 5,
        "arbitrary_branch_default": 2,
    },
    "backend/application/commands/product_commands.py": {},
    "backend/application/queries/product_query_service.py": {
        "sql_select": 10,
        "int_str_contract": 3,
    },
    "backend/application/services/product_catalog_service.py": {
        "cursor_execute": 1,
        "commit": 5,
        "rollback": 5,
        "sql_insert": 1,
        "sql_update": 5,
    },
    "backend/application/services/product_image_service.py": {},
    "backend/application/use_cases/create_product_use_case.py": {},
    "backend/application/use_cases/update_product_use_case.py": {},
    "backend/application/use_cases/deactivate_product_use_case.py": {},
    "backend/application/use_cases/restore_product_use_case.py": {},
    "backend/infrastructure/db/repositories/product_repository.py": {
        "commit": 1,
        "rollback": 1,
        "sql_select": 6,
        "sql_insert": 1,
        "sql_update": 1,
        "int_str_contract": 5,
    },
}


def _measure(relative: str) -> dict[str, int]:
    text = (PACKAGE_ROOT / relative).read_text(encoding="utf-8", errors="ignore")
    return {name: len(rx.findall(text)) for name, rx in PATTERNS.items() if rx.findall(text)}


def test_productos_scope_files_exist():
    missing = [r for r in SCOPE_FILES if not (PACKAGE_ROOT / r).exists()]
    assert not missing, f"missing scope files: {missing}"


def test_productos_scope_has_no_new_violations():
    """Ratchet: counts may shrink as the module is refactored, never grow."""
    regressions = []
    for rel in SCOPE_FILES:
        base = BASELINE.get(rel, {})
        for pattern, count in _measure(rel).items():
            if count > base.get(pattern, 0):
                regressions.append(f"{rel}: '{pattern}' {count} > baseline {base.get(pattern, 0)}")
    assert not regressions, "new PRODUCTOS violations:\n" + "\n".join(regressions)


def test_productos_documented_findings_snapshot():
    """When a violation is fixed, ratchet the baseline DOWN here in the same change."""
    drift = []
    for rel in SCOPE_FILES:
        live, base = _measure(rel), BASELINE.get(rel, {})
        for pattern in sorted(set(live) | set(base)):
            if live.get(pattern, 0) != base.get(pattern, 0):
                drift.append(
                    f"{rel}: '{pattern}' live={live.get(pattern, 0)} baseline={base.get(pattern, 0)}"
                )
    assert not drift, "PRODUCTOS snapshot drift — ratchet baseline:\n" + "\n".join(drift)
