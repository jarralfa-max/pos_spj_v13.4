"""PUR-13.15 — the canonical procurement context uses granular permissions only.

Legacy general permissions (COMPRAS, ADMIN_COMPRAS, PUEDE_COMPRAR) must not be
referenced by the new bounded context; every sensitive action is gated by a
PURCHASES_* granular permission validated in the backend.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROCUREMENT_ROOTS = [
    REPO / "backend" / "domain" / "procurement",
    REPO / "backend" / "application" / "procurement",
    REPO / "backend" / "infrastructure" / "db" / "repositories" / "procurement",
    REPO / "frontend" / "desktop" / "modules" / "purchasing",
]

_LEGACY_PERM = re.compile(
    r"[\"'](?:ADMIN_COMPRAS|PUEDE_COMPRAR|COMPRAS_ADMIN)[\"']"
    r"|[\"']COMPRAS[\"']"
    r"|[\"'](?:ver_compras|realizar_compras)[\"']")


def _files():
    for root in PROCUREMENT_ROOTS:
        if root.is_dir():
            for p in root.rglob("*.py"):
                if "__pycache__" not in p.parts:
                    yield p


def test_procurement_does_not_use_legacy_permissions():
    offenders = []
    for path in _files():
        for m in _LEGACY_PERM.finditer(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.relative_to(REPO)}: {m.group(0)}")
    assert not offenders, (
        "Compras usa permisos granulares PURCHASES_*, no permisos generales:\n"
        + "\n".join(offenders))


def test_procurement_permissions_are_granular():
    perms = (REPO / "backend/application/procurement/permissions.py").read_text(encoding="utf-8")
    # a representative sample of the granular vocabulary must exist
    for code in ("PURCHASES_DIRECT_CREATE", "PURCHASES_ORDER_APPROVE",
                 "PURCHASES_RECEIPT_COMPLETE", "PURCHASES_INVOICE_MATCH"):
        assert code in perms, f"falta permiso granular {code}"
