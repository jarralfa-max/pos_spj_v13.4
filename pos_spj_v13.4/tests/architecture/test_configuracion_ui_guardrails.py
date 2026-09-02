"""UI/UX phase guardrails — the Configuración desktop UI is
presentation-only. No SQL, no raw sqlite, no direct connection use in the
module; navigation permissions come from the real, shipped catalog
(`core/security/permission_catalog.py`). Mirrors
`tests/architecture/test_inventory_ui_guardrails.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.application.configuracion.permissions import ALL_CONFIGURACION_PERMISSIONS
from frontend.desktop.modules.configuracion.navigation.configuracion_sidebar import CONFIGURACION_NAV

_ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = _ROOT / "frontend" / "desktop" / "modules" / "configuracion"

_SQL_RE = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\s", re.IGNORECASE)
_FORBIDDEN = ("sqlite3", ".commit(", ".rollback(", ".cursor(")
# Inline literal colors — a hex triplet/sextet, the pattern DS-10 forbids
# ("Sin colores literales ni setStyleSheet con color").
_HEX_COLOR_RE = re.compile(r"#[0-9A-Fa-f]{3,8}\b")


def _module_files():
    return [p for p in MODULE_DIR.rglob("*.py") if "__pycache__" not in p.parts]


def test_no_sql_or_db_access_in_configuracion_ui():
    offenders = []
    for path in _module_files():
        text = path.read_text(encoding="utf-8")
        if _SQL_RE.search(text) or any(tok in text for tok in _FORBIDDEN):
            offenders.append(str(path.relative_to(_ROOT)))
    assert not offenders, f"UI de Configuración con acceso a datos/SQL: {offenders}"


def test_no_literal_hex_colors_in_configuracion_ui():
    offenders = []
    for path in _module_files():
        text = path.read_text(encoding="utf-8")
        if _HEX_COLOR_RE.search(text):
            offenders.append(str(path.relative_to(_ROOT)))
    assert not offenders, f"UI de Configuración con colores literales: {offenders}"


def test_no_inline_stylesheet_calls_in_configuracion_ui():
    offenders = []
    for path in _module_files():
        text = path.read_text(encoding="utf-8")
        if "setStyleSheet(" in text:
            offenders.append(str(path.relative_to(_ROOT)))
    assert not offenders, f"UI de Configuración con estilos inline: {offenders}"


def test_pages_and_dialogs_only_use_standard_design_system_dialog_base():
    """Every dialog must derive from `StandardDialog`/`FormDialog`/
    `ConfirmationDialog` (imported from `frontend.desktop.components`),
    never a raw `QDialog` subclass declared directly in this module."""
    dialogs_dir = MODULE_DIR / "dialogs"
    offenders = []
    for path in dialogs_dir.glob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"class \w+\(QDialog\)", text):
            offenders.append(str(path.relative_to(_ROOT)))
    assert not offenders, f"Diálogos que heredan de QDialog en vez de StandardDialog/FormDialog: {offenders}"


def test_nav_permissions_come_from_the_real_shipped_catalog():
    assert CONFIGURACION_NAV
    for entry in CONFIGURACION_NAV:
        assert entry.permission in ALL_CONFIGURACION_PERMISSIONS


def test_module_files_present():
    names = {p.name for p in _module_files()}
    assert {
        "configuracion_view.py", "configuracion_presenter.py", "configuracion_routes.py",
        "shell_registration.py",
    } <= names


def test_shell_registration_is_not_wired_into_the_legacy_shell_yet():
    """Documented scope boundary (same as finance/cash_register/inventory's
    own `shell_registration.py` files): this phase builds the module but
    does not switch it on in `main.py`/`MainWindow`/`menu_lateral.py` —
    that belongs to the SHELL-N track, which owns the actual cutover."""
    for legacy_file in ("main.py", "interfaz/main_window.py", "interfaz/menu_lateral.py"):
        path = _ROOT / legacy_file
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        assert "configuracion.shell_registration" not in text
        assert "ConfiguracionModuleActivator" not in text
