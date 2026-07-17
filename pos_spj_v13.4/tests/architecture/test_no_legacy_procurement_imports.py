"""PUR-13.18 — the canonical procurement context imports no legacy modules.

The new bounded context (backend/…/procurement, frontend/…/purchasing, and the
entry wrappers) must import only canonical packages — never the legacy monolith,
its widgets, or the legacy UI toolkit.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CANONICAL_ROOTS = [
    REPO / "backend" / "domain" / "procurement",
    REPO / "backend" / "application" / "procurement",
    REPO / "backend" / "infrastructure" / "db" / "repositories" / "procurement",
    REPO / "frontend" / "desktop" / "modules" / "purchasing",
    REPO / "modulos" / "compra_directa.py",
    REPO / "modulos" / "compras_enterprise.py",
]

_LEGACY_IMPORT = re.compile(
    r"from\s+modulos\.compras_pro\b"
    r"|from\s+modulos\.compras\b"
    r"|import\s+modulos\.compras_pro\b"
    r"|from\s+modulos\.ui_components\b"
    r"|from\s+modulos\.kpi_card\b"
    r"|from\s+modulos\.design_tokens\b"
    r"|from\s+modulos\.spj_styles\b"
    r"|from\s+repositories\.purchase")


def _files():
    for root in CANONICAL_ROOTS:
        if root.is_file():
            yield root
        elif root.is_dir():
            for p in root.rglob("*.py"):
                if "__pycache__" not in p.parts:
                    yield p


def test_no_legacy_procurement_imports():
    offenders = []
    for path in _files():
        for m in _LEGACY_IMPORT.finditer(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.relative_to(REPO)}: {m.group(0)!r}")
    assert not offenders, (
        "El contexto canónico de Compras importa módulos legacy:\n"
        + "\n".join(offenders))
