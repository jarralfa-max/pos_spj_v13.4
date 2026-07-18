"""INV-1 (§61.11) — the canonical inventory context uses granular permissions only.

Legacy general permissions (INVENTARIO, ADMIN_INVENTARIO, PUEDE_AJUSTAR_STOCK,
PUEDE_TRANSFERIR) must not be referenced by the new bounded context; every
sensitive action is gated by an INVENTORY_* granular permission.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INVENTORY_ROOTS = [
    REPO / "backend" / "domain" / "inventory",
    REPO / "backend" / "application" / "inventory",
    REPO / "backend" / "infrastructure" / "db" / "repositories" / "inventory",
    REPO / "frontend" / "desktop" / "modules" / "inventory",
]

_LEGACY_PERM = re.compile(
    r"[\"'](?:ADMIN_INVENTARIO|PUEDE_AJUSTAR_STOCK|PUEDE_TRANSFERIR"
    r"|INVENTARIO_ADMIN)[\"']"
    r"|[\"']INVENTARIO[\"']")


def _files():
    for root in INVENTORY_ROOTS:
        if root.is_dir():
            for p in root.rglob("*.py"):
                if "__pycache__" not in p.parts:
                    yield p


def test_inventory_does_not_use_legacy_permissions():
    offenders = []
    for path in _files():
        for m in _LEGACY_PERM.finditer(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.relative_to(REPO)}: {m.group(0)}")
    assert not offenders, (
        "Inventario usa permisos granulares INVENTORY_*, no permisos generales:\n"
        + "\n".join(offenders))
