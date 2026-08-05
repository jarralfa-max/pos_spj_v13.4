"""PUR-13.15 — the canonical procurement context uses granular permissions only.

Legacy general permissions (COMPRAS, ADMIN_COMPRAS, PUEDE_COMPRAR) must not be
referenced by the new bounded context; every sensitive action is gated by a
PURCHASES_* granular permission validated in the backend.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROCUREMENT_ROOTS = [
    REPO / "backend" / "domain" / "procurement",
    REPO / "backend" / "application" / "procurement",
    REPO / "backend" / "infrastructure" / "db" / "repositories" / "procurement",
    REPO / "frontend" / "desktop" / "modules" / "purchasing",
]

_LEGACY_PERMISSIONS = {
    "ADMIN_COMPRAS", "PUEDE_COMPRAR", "COMPRAS_ADMIN", "COMPRAS",
    "ver_compras", "realizar_compras",
}
_PERMISSION_CALLS = {"require", "can", "tiene_permiso", "has_permission"}


def _files():
    for root in PROCUREMENT_ROOTS:
        if root.is_dir():
            for p in root.rglob("*.py"):
                if "__pycache__" not in p.parts:
                    yield p


def test_procurement_does_not_use_legacy_permissions():
    offenders = []
    for path in _files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
            name = (call.func.attr if isinstance(call.func, ast.Attribute)
                    else call.func.id if isinstance(call.func, ast.Name) else "")
            if name not in _PERMISSION_CALLS:
                continue
            for argument in (*call.args, *(kw.value for kw in call.keywords)):
                if (isinstance(argument, ast.Constant)
                        and argument.value in _LEGACY_PERMISSIONS):
                    offenders.append(
                        f"{path.relative_to(REPO)}:{call.lineno}: {argument.value}")
    assert not offenders, (
        "Compras usa permisos granulares PURCHASES_*, no permisos generales:\n"
        + "\n".join(offenders))


def test_procurement_permissions_are_granular():
    perms = (REPO / "backend/application/procurement/permissions.py").read_text(encoding="utf-8")
    # a representative sample of the granular vocabulary must exist
    for code in ("PURCHASES_DIRECT_CREATE", "PURCHASES_ORDER_APPROVE",
                 "PURCHASES_RECEIPT_COMPLETE", "PURCHASES_INVOICE_MATCH"):
        assert code in perms, f"falta permiso granular {code}"
