"""FASE 0 — architecture guard-rail baseline for the DELIVERY module (Fase A).

DELIVERY's UI carries no raw executable SQL but holds arbitrary sucursal=1
defaults and two int(branch) casts. This ratchet freezes the baseline; the
Fase A increment drives identity casts and branch defaults to zero. Numbers may
shrink, never grow.
"""

from __future__ import annotations

import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]

UI_FILES = ["modulos/delivery.py"]
SCOPE_FILES = UI_FILES

PATTERNS: dict[str, re.Pattern[str]] = {
    "cursor_execute": re.compile(r"(self\.conexion|self\.db|self\.conn|\bdb|conn|cursor)\.execute\("),
    "commit": re.compile(r"\.commit\(\)"),
    "rollback": re.compile(r"\.rollback\(\)"),
    "sql_select": re.compile(r"\bSELECT\s", re.I),
    "sql_insert": re.compile(r"\bINSERT\s+INTO", re.I),
    "sql_update": re.compile(r"\bUPDATE\s+\w", re.I),
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
    "modulos/delivery.py": {
        # Identity casts + branch defaults removed (Fase A). The residual
        # sql_select prose match was removed (1->0); the sql_update matches are
        # comments/prose, not executable SQL.
        "sql_update": 2,
    },
}


def _measure(relative: str) -> dict[str, int]:
    text = (PACKAGE_ROOT / relative).read_text(encoding="utf-8", errors="ignore")
    return {name: len(rx.findall(text)) for name, rx in PATTERNS.items() if rx.findall(text)}


def test_delivery_scope_files_exist():
    missing = [r for r in SCOPE_FILES if not (PACKAGE_ROOT / r).exists()]
    assert not missing, f"missing scope files: {missing}"


def test_delivery_scope_has_no_new_violations():
    regressions = []
    for rel in SCOPE_FILES:
        base = BASELINE.get(rel, {})
        for pattern, count in _measure(rel).items():
            if count > base.get(pattern, 0):
                regressions.append(f"{rel}: '{pattern}' {count} > baseline {base.get(pattern, 0)}")
    assert not regressions, "new DELIVERY violations:\n" + "\n".join(regressions)


def test_delivery_documented_findings_snapshot():
    drift = []
    for rel in SCOPE_FILES:
        live, base = _measure(rel), BASELINE.get(rel, {})
        for pattern in sorted(set(live) | set(base)):
            if live.get(pattern, 0) != base.get(pattern, 0):
                drift.append(f"{rel}: '{pattern}' live={live.get(pattern, 0)} baseline={base.get(pattern, 0)}")
    assert not drift, "DELIVERY snapshot drift — ratchet baseline:\n" + "\n".join(drift)
