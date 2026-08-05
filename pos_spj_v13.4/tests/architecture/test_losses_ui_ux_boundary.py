"""Static guardrails for LOSS-21's presentation boundary."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LOSS_UI = ROOT / "frontend/desktop/modules/losses"


def test_losses_ui_uses_canonical_theme_tooltips_and_view_states():
    sidebar = (LOSS_UI / "widgets/losses_sidebar_widget.py").read_text(encoding="utf-8")
    placeholder = (LOSS_UI / "pages/placeholder_page.py").read_text(encoding="utf-8")
    view = (LOSS_UI / "losses_view.py").read_text(encoding="utf-8")
    assert 'setProperty("role", "nav")' in sidebar
    assert "apply_tooltip" in placeholder
    assert "ViewState.EMPTY" in placeholder
    assert "ResponsiveBreakpoints" in view


def test_losses_ui_has_no_inline_styles_or_data_access():
    offenders = []
    forbidden = ("setStyleSheet(", "sqlite3", ".commit(", "SELECT ", "INSERT INTO ")
    presentation_files = [LOSS_UI / "losses_view.py"]
    presentation_files.extend((LOSS_UI / "pages").rglob("*.py"))
    presentation_files.extend((LOSS_UI / "widgets").rglob("*.py"))
    for path in presentation_files:
        source = path.read_text(encoding="utf-8")
        if any(token in source for token in forbidden):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders
