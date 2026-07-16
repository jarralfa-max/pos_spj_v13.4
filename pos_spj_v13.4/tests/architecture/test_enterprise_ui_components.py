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


def test_chart_pipeline_contract_files_exist() -> None:
    charts_dir = ROOT / "frontend" / "desktop" / "charts"
    dto_dir = ROOT / "backend" / "application" / "dto" / "charts"
    expected = [
        charts_dir / "chart_bridge.py",
        charts_dir / "templates" / "chart_base.html",
        charts_dir / "renderers" / "echarts_renderer.js",
        dto_dir / "chart_data_dto.py",
    ]

    missing = [str(path.relative_to(ROOT)) for path in expected if not path.exists()]
    assert not missing


def test_chart_dto_has_no_visual_code_or_hardcoded_colors() -> None:
    text = (ROOT / "backend" / "application" / "dto" / "charts" / "chart_data_dto.py").read_text(encoding="utf-8")
    forbidden = ("html", "css", "javascript", "setStyleSheet", "rgb(", "rgba(")

    violations = [token for token in forbidden if token in text.lower()]
    assert not violations


def test_chart_bridge_uses_single_template_and_echarts_renderer() -> None:
    bridge = (ROOT / "frontend" / "desktop" / "charts" / "chart_bridge.py").read_text(encoding="utf-8")
    renderer = (ROOT / "frontend" / "desktop" / "charts" / "renderers" / "echarts_renderer.js").read_text(encoding="utf-8")

    assert "chart_base.html" in bridge
    assert "echarts_renderer.js" in bridge
    assert "echarts" in renderer
    assert "QChart" not in bridge + renderer
    assert "matplotlib" not in bridge + renderer
    assert "pyqtgraph" not in bridge + renderer


def test_hr_tables_use_standard_table_helpers_not_raw_items_or_widgets() -> None:
    pages = ROOT / "frontend" / "desktop" / "modules" / "hr" / "pages"
    checked = [
        pages / "employees_page.py",
        pages / "attendance_page.py",
        pages / "leave_page.py",
        pages / "schedules_page.py",
        pages / "payroll_page.py",
    ]
    violations = []
    for path in checked:
        text = path.read_text(encoding="utf-8")
        for token in ("QTableWidgetItem", "setItem(", "setCellWidget("):
            if token in text:
                violations.append(f"{path.name}: {token}")
        assert "StandardTable" in text
        assert "configure_headers" in text
        assert "HIDDEN_HEADERS" in text

    assert not violations


def test_table_filter_status_and_pagination_components_are_canonical() -> None:
    table_text = (COMPONENTS / "tables.py").read_text(encoding="utf-8")
    filter_text = (COMPONENTS / "filter_bar.py").read_text(encoding="utf-8")
    status_text = (COMPONENTS / "status_badge.py").read_text(encoding="utf-8")
    pagination_text = (COMPONENTS / "pagination_bar.py").read_text(encoding="utf-8")

    assert "hide_columns_by_header" in table_text
    assert "set_status_badge" in table_text
    assert "set_action_button" in table_text
    assert "Tooltip.attach" in table_text
    assert "set_result_count" in filter_text
    assert "add_clear_action" in filter_text
    assert "Tooltip.attach" in status_text
    assert "StandardButton" in pagination_text
    assert "QPushButton" not in pagination_text


def test_forms_and_dialogs_use_canonical_standard_components() -> None:
    form_text = (COMPONENTS / "form_field.py").read_text(encoding="utf-8")
    dialog_text = (COMPONENTS / "dialogs.py").read_text(encoding="utf-8")

    assert "class StandardForm" in form_text
    assert "class FormField" in form_text
    assert "set_error" in form_text
    assert "focus_first_error" in form_text
    assert "Tooltip.attach" in form_text
    assert "class StandardDialog" in dialog_text
    assert "set_initial_focus" in dialog_text
    assert "Guardar" in dialog_text
    assert "Cancelar" in dialog_text


def test_hr_dialogs_use_standard_dialog_form_fields_and_specialized_inputs() -> None:
    dialogs_dir = ROOT / "frontend" / "desktop" / "modules" / "hr" / "dialogs"
    checked = [path for path in dialogs_dir.glob("*.py") if path.name != "__init__.py"]
    violations = []
    for path in checked:
        text = path.read_text(encoding="utf-8")
        if "StandardDialog" not in text:
            violations.append(f"{path.name}: StandardDialog")
        if "QFormLayout" in text or "QDialogButtonBox(" in text and "StandardDialog" not in text:
            violations.append(f"{path.name}: local form/dialog layout")

    employee_dialog = (dialogs_dir / "employee_dialog.py").read_text(encoding="utf-8")
    attendance_dialog = (dialogs_dir / "attendance_dialog.py").read_text(encoding="utf-8")
    assert "StandardForm" in employee_dialog
    assert "FormField" in employee_dialog
    assert "PhoneInput" in employee_dialog
    assert "DecimalInput" in employee_dialog
    assert "SearchableComboBox" in employee_dialog
    assert "def accept" in employee_dialog
    assert "focus_first_error" in employee_dialog
    assert "StandardForm" in attendance_dialog
    assert "FormField" in attendance_dialog
    assert "SearchableComboBox" in attendance_dialog
    assert "def accept" in attendance_dialog
    assert "focus_first_error" in attendance_dialog
    assert not violations


def test_view_state_and_feedback_components_cover_phase_ui9_contracts() -> None:
    expected = {
        "loading_state.py": "LOADING",
        "empty_state.py": "EMPTY",
        "error_state.py": "ERROR",
        "offline_state.py": "OFFLINE",
        "stale_state.py": "STALE",
        "permission_state.py": "NO_PERMISSION",
        "partial_state.py": "PARTIAL_DATA",
        "content_state.py": "READY",
    }
    for filename, state in expected.items():
        text = (COMPONENTS / filename).read_text(encoding="utf-8")
        assert state in text
    feedback = (COMPONENTS / "feedback.py").read_text(encoding="utf-8")
    assert "class InlineFeedback" in feedback
    assert "class StatusMessage" in feedback
    assert "class Toast" in feedback
    assert "show_message" in feedback


def test_hr_pages_support_standard_states_and_inline_feedback() -> None:
    pages = ROOT / "frontend" / "desktop" / "modules" / "hr" / "pages"
    checked = [
        pages / "overview_page.py",
        pages / "employees_page.py",
        pages / "attendance_page.py",
        pages / "leave_page.py",
        pages / "schedules_page.py",
        pages / "payroll_page.py",
    ]
    required = ("LoadingState", "EmptyState", "ErrorState", "OfflineState", "StaleState", "PartialState", "PermissionState", "InlineFeedback", "Toast")
    missing = []
    for path in checked:
        text = path.read_text(encoding="utf-8")
        for token in required:
            if token not in text:
                missing.append(f"{path.name}:{token}")
        assert "except PermissionError" in text
        assert "except ConnectionError" in text
    assert missing == []


def test_hr_view_documents_responsive_accessibility_keyboard_and_tooltips() -> None:
    text = (ROOT / "frontend" / "desktop" / "modules" / "hr" / "hr_view.py").read_text(encoding="utf-8")
    assert "VALIDATED_RESOLUTIONS" in text
    assert "1366" in text and "1440" in text and "1920" in text
    assert "ACCESSIBILITY_SCALE_MIN" in text
    assert "setAccessibleName" in text
    assert "setAccessibleDescription" in text
    assert "Tooltip.attach" in text
    assert "flechas del teclado" in text


def test_hr_frontend_phase_ui11_has_no_legacy_dialog_table_or_chart_patterns() -> None:
    frontend = ROOT / "frontend" / "desktop" / "modules" / "hr"
    forbidden = ("QFormLayout", "QTableWidgetItem", "setStyleSheet(", "matplotlib", "pyqtgraph", "QChart")
    violations = []
    for path in frontend.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                violations.append(f"{path.relative_to(frontend)}:{token}")
    assert violations == []
