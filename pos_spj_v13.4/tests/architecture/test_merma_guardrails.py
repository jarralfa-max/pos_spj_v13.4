"""FASE 0 — architecture guard-rail baseline for the MERMA (waste) module.

MERMA arrives already largely refactored (canonical waste backend, UUIDv7
identity, no SQL/commit in the UI). This baseline ratchet locks that clean
state and blocks regressions, complementing the behavioural waste tests
(test_waste_module_refactor / test_waste_uuid_identity / test_merma_*).
"""

from __future__ import annotations

import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]

UI_FILES = ["modulos/merma.py"]
BACKEND_FILES = [
    "backend/application/services/waste_application_service.py",
    "backend/application/use_cases/register_waste_use_case.py",
    "backend/application/commands/waste_commands.py",
    "backend/application/queries/waste_query_service.py",
    "backend/infrastructure/db/repositories/waste_repository.py",
]
SCOPE_FILES = UI_FILES + BACKEND_FILES

PATTERNS: dict[str, re.Pattern[str]] = {
    "cursor_execute": re.compile(r"(cursor|cur|conn|self\.db|self\.conn|self\._conn)\.execute"),
    "commit": re.compile(r"\.commit\(\)"),
    "rollback": re.compile(r"\.rollback\(\)"),
    "sql_select": re.compile(r"\bSELECT\s", re.I),
    "sql_insert": re.compile(r"\bINSERT\s+INTO", re.I),
    "sql_update": re.compile(r"\bUPDATE\s+\w", re.I),
    "create_table": re.compile(r"CREATE\s+TABLE", re.I),
    "autoincrement": re.compile(r"AUTOINCREMENT", re.I),
    "integer_pk": re.compile(r"INTEGER\s+PRIMARY\s+KEY", re.I),
    "lastrowid": re.compile(r"lastrowid", re.I),
    "int_id_cast": re.compile(r"int\(\s*[\w\.]*_id"),
    "cast_as_text": re.compile(r"CAST\([^)]*AS\s+TEXT", re.I),
    "uuid4": re.compile(r"uuid4"),
    "external": re.compile(r"\bimport\s+(smtplib|serial|urllib|socket|subprocess)\b"),
}

# Documented FASE 0 baseline. UI is clean; only the waste repository owns SQL
# and its explicit save_changes()/rollback_changes() transaction methods.
BASELINE: dict[str, dict[str, int]] = {
    "modulos/merma.py": {},
    "backend/application/services/waste_application_service.py": {},
    "backend/application/use_cases/register_waste_use_case.py": {},
    "backend/application/commands/waste_commands.py": {},
    "backend/application/queries/waste_query_service.py": {},
    "backend/infrastructure/db/repositories/waste_repository.py": {
        "sql_select": 6,
        "sql_insert": 1,
        "commit": 1,       # explicit save_changes() — repo-owned tx -> identity cutover phase
        "rollback": 1,     # explicit rollback_changes()
    },
}


def _measure(relative: str) -> dict[str, int]:
    text = (PACKAGE_ROOT / relative).read_text(encoding="utf-8", errors="ignore")
    return {name: len(rx.findall(text)) for name, rx in PATTERNS.items() if rx.findall(text)}


def test_merma_scope_files_exist():
    missing = [r for r in SCOPE_FILES if not (PACKAGE_ROOT / r).exists()]
    assert not missing, f"missing scope files: {missing}"


def test_merma_scope_has_no_new_violations():
    regressions = []
    for rel in SCOPE_FILES:
        base = BASELINE.get(rel, {})
        for pattern, count in _measure(rel).items():
            if count > base.get(pattern, 0):
                regressions.append(f"{rel}: '{pattern}' {count} > baseline {base.get(pattern, 0)}")
    assert not regressions, "new MERMA violations:\n" + "\n".join(regressions)


def test_merma_documented_findings_snapshot():
    drift = []
    for rel in SCOPE_FILES:
        live, base = _measure(rel), BASELINE.get(rel, {})
        for pattern in sorted(set(live) | set(base)):
            if live.get(pattern, 0) != base.get(pattern, 0):
                drift.append(f"{rel}: '{pattern}' live={live.get(pattern, 0)} baseline={base.get(pattern, 0)}")
    assert not drift, "MERMA snapshot drift — ratchet baseline down:\n" + "\n".join(drift)


def test_merma_ui_has_no_sql_commit_or_external_integrations():
    """The PyQt waste UI stays free of SQL, transactions and raw integrations."""
    offenders = []
    for rel in UI_FILES:
        live = _measure(rel)
        for pattern in ("cursor_execute", "sql_insert", "sql_update", "commit",
                        "rollback", "create_table", "lastrowid", "int_id_cast",
                        "uuid4", "external"):
            if live.get(pattern):
                offenders.append(f"{rel}:{pattern}={live[pattern]}")
    assert not offenders, f"MERMA UI regressed: {offenders}"
