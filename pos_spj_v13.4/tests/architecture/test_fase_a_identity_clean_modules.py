"""Fase A ratchet for modules cleaned of identity debt (branch defaults + casts).

These UI modules carry no executable SQL; their only identity debt was arbitrary
sucursal=1 defaults (and, for some, int(branch) casts). After the Fase A pass
they must stay at zero. Guards against regressions without a per-module file.
"""

from __future__ import annotations

import re
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]

CLEAN_MODULES = [
    "modulos/caja.py",
    "modulos/inventario_local.py",
    "modulos/transferencias.py",
]

ARBITRARY_BRANCH_DEFAULT = re.compile(
    r"(branch_id|sucursal_id)\s*=\s*1\b"
    r"|(branch_id|sucursal_id)[\"']?\s*,\s*[\"']?1[\"']?"
)
INT_ID_CAST = re.compile(
    r"int\(\s*[\w\.]*_id|int\(\s*getattr\([^,]+,\s*[\"'](sucursal_id|branch_id)"
)


def test_clean_modules_have_no_arbitrary_branch_default():
    offenders = {
        rel: ARBITRARY_BRANCH_DEFAULT.findall((PACKAGE_ROOT / rel).read_text(encoding="utf-8", errors="ignore"))
        for rel in CLEAN_MODULES
    }
    bad = {rel: len(m) for rel, m in offenders.items() if m}
    assert not bad, f"arbitrary sucursal=1 default reintroduced: {bad}"


def test_clean_modules_have_no_int_identity_cast():
    bad = {
        rel: len(INT_ID_CAST.findall((PACKAGE_ROOT / rel).read_text(encoding="utf-8", errors="ignore")))
        for rel in CLEAN_MODULES
        if INT_ID_CAST.findall((PACKAGE_ROOT / rel).read_text(encoding="utf-8", errors="ignore"))
    }
    assert not bad, f"int(_id) identity cast reintroduced: {bad}"
