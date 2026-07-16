from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = ROOT / "frontend" / "desktop" / "components"


def test_enterprise_ui_component_contract_files_exist() -> None:
    expected = {
        "buttons.py",
        "cards.py",
        "chart_view.py",
        "dashboard_grid.py",
        "decimal_input.py",
        "dialogs.py",
        "error_state.py",
        "feedback.py",
        "filter_bar.py",
        "form_field.py",
        "icons.py",
        "kpi_bar.py",
        "kpi_card.py",
        "month_input.py",
        "offline_state.py",
        "page_header.py",
        "permission_state.py",
        "search_input.py",
        "searchable_combo.py",
        "stale_state.py",
        "tables.py",
        "time_input.py",
        "time_range_input.py",
        "tooltip.py",
    }

    missing = sorted(name for name in expected if not (COMPONENTS / name).exists())
    assert not missing


def test_enterprise_ui_components_have_no_local_qss_or_hardcoded_colors() -> None:
    checked = [
        "chart_view.py",
        "dashboard_grid.py",
        "decimal_input.py",
        "dialogs.py",
        "error_state.py",
        "feedback.py",
        "form_field.py",
        "month_input.py",
        "offline_state.py",
        "permission_state.py",
        "search_input.py",
        "searchable_combo.py",
        "stale_state.py",
        "time_input.py",
        "time_range_input.py",
    ]
    forbidden = ("setStyleSheet(", "#", "rgb(", "rgba(")
    violations = []
    for name in checked:
        text = (COMPONENTS / name).read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                violations.append(f"{name}: {token}")

    assert not violations


def test_time_inputs_do_not_use_free_text_line_edits() -> None:
    for name in ("time_input.py", "time_range_input.py"):
        text = (COMPONENTS / name).read_text(encoding="utf-8")
        assert "QLineEdit" not in text
        assert ".text().strip()" not in text


def test_charts_use_html_js_contract_and_not_native_pyqt_charting() -> None:
    text = (COMPONENTS / "chart_view.py").read_text(encoding="utf-8")
    assert "html_js" in text
    assert "QChart" not in text
    assert "matplotlib" not in text
    assert "pyqtgraph" not in text
