"""BI-23 guardrails — mirrors
`tests/architecture/test_losses_sidebar_navigation.py` exactly, scoped to
the new `frontend/desktop/modules/business_intelligence/` module.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_DIR = ROOT / "frontend/desktop/modules/business_intelligence"

_EMOJI_PATTERN = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F02F]"
)


def test_view_uses_sidebar_and_stack_not_horizontal_tabs():
    source = (MODULE_DIR / "business_intelligence_view.py").read_text(encoding="utf-8")
    assert "BusinessIntelligenceSidebarWidget" in source
    assert "QStackedWidget" in source
    assert "QTabWidget" not in source


def test_pages_do_not_access_database_or_repositories():
    offenders = []
    for path in MODULE_DIR.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if any(needle in source for needle in ("sqlite3", ".execute(", ".commit(", "repositories")):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders


def test_no_legacy_design_system_imports_or_inline_styles():
    forbidden = ("modulos.design_tokens", "modulos.ui_components", "modulos.spj_styles",
                "setStyleSheet", "QTableWidget")
    offenders = []
    for path in MODULE_DIR.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for needle in forbidden:
            if needle in source:
                offenders.append(f"{path.relative_to(ROOT)}: {needle}")
    assert not offenders


def test_no_emoji_icons_in_module_source():
    offenders = []
    for path in MODULE_DIR.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if _EMOJI_PATTERN.search(source):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders


def test_nav_entries_use_registered_analytics_permissions():
    from backend.application.analytics.permissions import ALL_ANALYTICS_PERMISSIONS
    from frontend.desktop.modules.business_intelligence.navigation.business_intelligence_sidebar import (
        BUSINESS_INTELLIGENCE_NAV,
    )
    for entry in BUSINESS_INTELLIGENCE_NAV:
        assert entry.permission in ALL_ANALYTICS_PERMISSIONS, (
            f"{entry.page_id} references unregistered permission {entry.permission}")


def test_the_module_is_reachable_from_the_canonical_shell():
    """Antes comprobaba lo contrario, y contra un archivo que ya no existe.

    Leia `interfaz/main_window.py` para verificar que BI NO estuviera cableado
    en el shell legacy — una decision de coexistencia deliberada en su momento.
    Ese shell se borro en la reconstruccion, asi que la prueba llevaba fallando
    con `FileNotFoundError`: un fallo que no dice nada de BI.

    El corte ya ocurrio y BI vive en el shell canonico. Lo que hay que vigilar
    ahora es lo opuesto: que siga siendo ALCANZABLE. Un modulo construido sin
    entrada de menu no falla nunca, simplemente no existe para el usuario.
    """
    from frontend.desktop.shell.sidebar.migrated_modules_navigation import (
        MIGRATED_MODULES_NAVIGATION_ITEMS,
    )

    entradas = {item.item_id for item in MIGRATED_MODULES_NAVIGATION_ITEMS}
    assert "nav.business_intelligence" in entradas

    assert not (ROOT / "interfaz" / "main_window.py").exists(), (
        "Volvio el shell legacy: habria que decidir de nuevo la coexistencia.")
