"""INV-25 guardrails — the enterprise inventory UI is presentation-only.

No SQL, no raw sqlite, no direct connection use in the module; navigation
permissions are granular INVENTORY_* codes.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.application.inventory.permissions import ALL_INVENTORY_PERMISSIONS
from frontend.desktop.modules.inventory.navigation import INVENTORY_NAV

MODULE_DIR = (Path(__file__).resolve().parents[2]
              / "frontend" / "desktop" / "modules" / "inventory")

# Raw data access — NOT use-case/service ``.execute()`` delegation, which is how
# the presenter is meant to reach the backend.
_SQL_RE = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\s", re.IGNORECASE)
_FORBIDDEN = ("sqlite3", ".commit(", ".rollback(", ".cursor(")


def _module_files():
    return [p for p in MODULE_DIR.rglob("*.py") if "__pycache__" not in p.parts]


def test_no_sql_or_db_access_in_inventory_ui():
    offenders = []
    for path in _module_files():
        text = path.read_text(encoding="utf-8")
        if _SQL_RE.search(text) or any(tok in text for tok in _FORBIDDEN):
            offenders.append(str(path.name))
    assert not offenders, f"UI de inventario con acceso a datos/SQL: {offenders}"


def test_nav_permissions_are_granular_inventory_codes():
    assert INVENTORY_NAV
    for entry in INVENTORY_NAV:
        assert entry.permission in ALL_INVENTORY_PERMISSIONS
        assert entry.permission.startswith("INVENTORY_")


def test_module_files_present():
    names = {p.name for p in _module_files()}
    assert {"presenter.py", "view_models.py", "navigation.py"} <= names
