"""FASE 0 — architecture guard-rail baseline for the COMPRAS module (Fase A).

compras_pro.py is the largest UI module and the heaviest remaining SQL-in-UI
offender (purchasing). It still runs raw SELECT/INSERT/UPDATE/DELETE, commits,
and even creates tables (_ensure_qr_schema — schema work that belongs in
migrations). This ratchet freezes the post-tanda-1 baseline; each extraction
batch must drive the numbers down, never up.
"""

from __future__ import annotations

import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]

UI_FILES = ["modulos/compras_pro.py"]
SCOPE_FILES = UI_FILES

PATTERNS: dict[str, re.Pattern[str]] = {
    "cursor_execute": re.compile(
        r"(self\.conexion|self\.db|self\.conn|\bdb|conn|cursor|self\.container\.db)\.execute\("
    ),
    "commit": re.compile(r"\.commit\(\)"),
    "rollback": re.compile(r"\.rollback\(\)"),
    "sql_select": re.compile(r"\bSELECT\s", re.I),
    "sql_insert": re.compile(r"\bINSERT\s+INTO", re.I),
    "sql_update": re.compile(r"\bUPDATE\s+\w", re.I),
    "sql_delete": re.compile(r"\bDELETE\s+FROM", re.I),
    "create_table": re.compile(r"CREATE\s+TABLE", re.I),
    "lastrowid": re.compile(r"lastrowid", re.I),
}

# PUR-13: el monolito compras_pro.py fue reemplazado por un wrapper canónico
# (delega en ModuloComprasEnterprise). El ratchet llegó a su meta: cero patrones
# SQL/commit/schema en el archivo. Baseline vacío = el wrapper no puede
# reintroducir nada.
BASELINE: dict[str, dict[str, int]] = {
    "modulos/compras_pro.py": {},
}


def _measure(relative: str) -> dict[str, int]:
    text = (PACKAGE_ROOT / relative).read_text(encoding="utf-8", errors="ignore")
    return {name: len(rx.findall(text)) for name, rx in PATTERNS.items() if rx.findall(text)}


def test_compras_scope_files_exist():
    missing = [r for r in SCOPE_FILES if not (PACKAGE_ROOT / r).exists()]
    assert not missing, f"missing scope files: {missing}"


def test_compras_scope_has_no_new_violations():
    regressions = []
    for rel in SCOPE_FILES:
        base = BASELINE.get(rel, {})
        for pattern, count in _measure(rel).items():
            if count > base.get(pattern, 0):
                regressions.append(f"{rel}: '{pattern}' {count} > baseline {base.get(pattern, 0)}")
    assert not regressions, "new COMPRAS violations:\n" + "\n".join(regressions)


def test_compras_ui_has_no_executable_sql_or_commit():
    """compras_pro.py must run no raw SQL and own no transaction (regla 8/9)."""
    live = _measure("modulos/compras_pro.py")
    for pattern in ("cursor_execute", "commit", "rollback", "sql_insert",
                    "sql_delete", "create_table", "lastrowid"):
        assert live.get(pattern, 0) == 0, f"compras_pro.py regained '{pattern}'={live[pattern]}"


def test_compras_documented_findings_snapshot():
    drift = []
    for rel in SCOPE_FILES:
        live, base = _measure(rel), BASELINE.get(rel, {})
        for pattern in sorted(set(live) | set(base)):
            if live.get(pattern, 0) != base.get(pattern, 0):
                drift.append(f"{rel}: '{pattern}' live={live.get(pattern, 0)} baseline={base.get(pattern, 0)}")
    assert not drift, "COMPRAS snapshot drift — ratchet baseline:\n" + "\n".join(drift)
