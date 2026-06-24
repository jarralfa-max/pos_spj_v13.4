"""FASE 0 — architecture guard-rail baseline for the VENTAS module (Fase A).

VENTAS is the operational core. Its PyQt UI still runs some raw SQL reads, holds
arbitrary sucursal=1 defaults and one int(branch) cast. Identity writes
(lastrowid) are NOT here — they live in the sales service and are coupled to the
Phase B schema cutover.

This ratchet freezes the current UI violation counts. Numbers may shrink as the
module is refactored (SQL -> QueryService/repo, branch from session, operation_id
via new_uuid), never grow.
"""

from __future__ import annotations

import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]

UI_FILES = ["modulos/ventas.py"]
SCOPE_FILES = UI_FILES

PATTERNS: dict[str, re.Pattern[str]] = {
    "cursor_execute": re.compile(r"(self\.conexion|self\.db|self\.conn|\bdb|conn|cursor)\.execute\("),
    "commit": re.compile(r"\.commit\(\)"),
    "rollback": re.compile(r"\.rollback\(\)"),
    "sql_select": re.compile(r"\bSELECT\s", re.I),
    "sql_insert": re.compile(r"\bINSERT\s+INTO", re.I),
    "sql_update": re.compile(r"\bUPDATE\s+\w", re.I),
    "create_table": re.compile(r"CREATE\s+TABLE", re.I),
    "autoincrement": re.compile(r"AUTOINCREMENT", re.I),
    "lastrowid": re.compile(r"lastrowid", re.I),
    "int_id_cast": re.compile(r"int\(\s*[\w\.]*_id|int\(\s*getattr\([^,]+,\s*[\"'](sucursal_id|branch_id)"),
    "int_str_contract": re.compile(r"int \| str|str \| int"),
    "arbitrary_branch_default": re.compile(
        r"(branch_id|sucursal_id)\s*=\s*1\b"
        r"|(branch_id|sucursal_id)[\"']?\s*,\s*[\"']?1[\"']?"
    ),
}

# Documented Fase 0 baseline (measured 2026-06). Drive every number DOWN.
BASELINE: dict[str, dict[str, int]] = {
    "modulos/ventas.py": {
        # Identity casts + branch defaults removed; all executable read SQL
        # extracted to SalesReadRepository (Fase A). The residual sql_select/
        # sql_update matches are comments/prose, not executable SQL.
        "sql_select": 2,
        "sql_update": 9,
    },
}


def _measure(relative: str) -> dict[str, int]:
    text = (PACKAGE_ROOT / relative).read_text(encoding="utf-8", errors="ignore")
    return {name: len(rx.findall(text)) for name, rx in PATTERNS.items() if rx.findall(text)}


def test_ventas_scope_files_exist():
    missing = [r for r in SCOPE_FILES if not (PACKAGE_ROOT / r).exists()]
    assert not missing, f"missing scope files: {missing}"


def test_ventas_scope_has_no_new_violations():
    regressions = []
    for rel in SCOPE_FILES:
        base = BASELINE.get(rel, {})
        for pattern, count in _measure(rel).items():
            if count > base.get(pattern, 0):
                regressions.append(f"{rel}: '{pattern}' {count} > baseline {base.get(pattern, 0)}")
    assert not regressions, "new VENTAS violations:\n" + "\n".join(regressions)


def test_ventas_documented_findings_snapshot():
    drift = []
    for rel in SCOPE_FILES:
        live, base = _measure(rel), BASELINE.get(rel, {})
        for pattern in sorted(set(live) | set(base)):
            if live.get(pattern, 0) != base.get(pattern, 0):
                drift.append(f"{rel}: '{pattern}' live={live.get(pattern, 0)} baseline={base.get(pattern, 0)}")
    assert not drift, "VENTAS snapshot drift — ratchet baseline:\n" + "\n".join(drift)
