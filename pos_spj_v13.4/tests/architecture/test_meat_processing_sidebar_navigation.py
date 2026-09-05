"""PROC-4 architecture guardrails. Mirrors
tests/architecture/test_losses_sidebar_navigation.py, minus the "cut over the
live app" checks — Meat Processing is NOT wired into interfaz/menu_lateral.py
or interfaz/main_window.py yet (that's PROC-23/PROC-25); the legacy
"PRODUCCION" button keeps opening modulos/produccion.py until then.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_meat_processing_view_uses_sidebar_and_stack_not_horizontal_tabs():
    source = (ROOT / "frontend/desktop/modules/meat_processing/meat_processing_view.py"
              ).read_text(encoding="utf-8")
    assert "MeatProcessingSidebarWidget" in source
    assert "QStackedWidget" in source
    assert "QTabWidget" not in source


def test_meat_processing_pages_do_not_access_database_or_repositories():
    """PROC-23: pages/dialogs/view_models must stay free of DB access — but
    presenters/ (added in PROC-23) legitimately call ``use_case.execute(...)``,
    the sanctioned application-layer entry point (same pattern
    InventoryPresenter/LossRegistrationPresenter already use); only
    ``sqlite3``, direct ``.commit()`` and repository imports are real
    violations there."""
    offenders = []
    module = ROOT / "frontend/desktop/modules/meat_processing"
    for path in module.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        is_presenter = "presenters" in path.relative_to(module).parts
        tokens = (
            ("sqlite3", ".commit(", "repositories") if is_presenter
            else ("sqlite3", ".execute(", ".commit(", "repositories"))
        if any(token in source for token in tokens):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders


def test_meat_processing_module_does_not_use_emoji_icons():
    module = ROOT / "frontend/desktop/modules/meat_processing"
    offenders = []
    for path in module.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if any(ord(char) > 0x2600 for char in source):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders


def test_legacy_produccion_menu_entry_and_module_are_not_touched_yet():
    """PROC-4 builds the new shell standalone; cutover is a later phase."""
    menu_source = (ROOT / "interfaz/menu_lateral.py").read_text(encoding="utf-8")
    assert '_crear_boton("🔪 Procesamiento Cárnico", "PRODUCCION")' in menu_source
    main_window_source = (ROOT / "interfaz/main_window.py").read_text(encoding="utf-8")
    assert "MeatProcessingView" not in main_window_source
    assert "meat_processing" not in main_window_source.lower()


def test_navigation_contract_has_no_pyqt_import():
    """The declarative nav contract must stay importable without initializing Qt
    (§4: pure navigation contracts vs. lazy-imported UI classes)."""
    source = (ROOT / "frontend/desktop/modules/meat_processing/navigation/"
              "meat_processing_sidebar.py").read_text(encoding="utf-8")
    assert "PyQt5" not in source
