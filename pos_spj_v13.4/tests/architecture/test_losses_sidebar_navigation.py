from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_losses_view_uses_sidebar_and_stack_not_horizontal_tabs():
    source = (ROOT / "frontend/desktop/modules/losses/losses_view.py").read_text(encoding="utf-8")
    assert "LossesSidebarWidget" in source
    assert "QStackedWidget" in source
    assert "QTabWidget" not in source


def test_main_window_uses_only_canonical_losses_host():
    source = (ROOT / "interfaz/main_window.py").read_text(encoding="utf-8")
    assert "from backend.infrastructure.desktop.losses_factory import LossesModuleHost" in source
    assert 'self._conectar("MERMAS",' in source
    assert "ModuloMerma" not in source
    assert 'self._conectar("MERMA",' not in source


def test_global_sidebar_has_one_mermas_entry_without_emoji():
    source = (ROOT / "interfaz/menu_lateral.py").read_text(encoding="utf-8")
    assert source.count('self._crear_boton("Mermas", "MERMAS")') == 1
    assert '"MERMA"' not in source


def test_losses_pages_do_not_access_database_or_repositories():
    offenders = []
    module = ROOT / "frontend/desktop/modules/losses"
    for path in module.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if any(token in source for token in ("sqlite3", ".execute(", ".commit(", "repositories")):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders
