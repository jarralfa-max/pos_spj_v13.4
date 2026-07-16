from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
HR_FRONTEND = PACKAGE_ROOT / "frontend" / "desktop" / "modules" / "hr"
HR_DOMAIN = PACKAGE_ROOT / "backend" / "domain" / "hr"
HR_SCHEMA = PACKAGE_ROOT / "backend" / "infrastructure" / "db" / "schema" / "hr_schema.py"


def test_hr_phase1_target_domain_and_schema_exist() -> None:
    expected = {
        HR_DOMAIN / "entities.py",
        HR_DOMAIN / "value_objects.py",
        HR_DOMAIN / "enums.py",
        HR_DOMAIN / "exceptions.py",
        HR_DOMAIN / "repository_ports.py",
        HR_DOMAIN / "policies" / "attendance_policy.py",
        HR_DOMAIN / "policies" / "leave_policy.py",
        HR_DOMAIN / "policies" / "payroll_policy.py",
        HR_DOMAIN / "policies" / "authorization_policy.py",
        HR_DOMAIN / "services" / "attendance_calculator.py",
        HR_DOMAIN / "services" / "payroll_calculator.py",
        HR_DOMAIN / "services" / "workday_builder.py",
        HR_SCHEMA,
    }
    missing = [str(path.relative_to(PACKAGE_ROOT)) for path in expected if not path.is_file()]
    assert missing == []


def test_hr_domain_generates_identity_only_with_new_uuid() -> None:
    entities = (HR_DOMAIN / "entities.py").read_text(encoding="utf-8")
    assert "from backend.shared.ids import new_uuid" in entities
    assert "uuid.uuid4" not in entities
    assert "lastrowid" not in entities
    assert "AUTOINCREMENT" not in entities


def test_hr_schema_has_no_integer_primary_keys_or_autoincrement() -> None:
    schema = HR_SCHEMA.read_text(encoding="utf-8")
    assert "AUTOINCREMENT" not in schema
    assert "INTEGER PRIMARY KEY" not in schema
    assert "id TEXT NOT NULL PRIMARY KEY" in schema


def test_hr_frontend_does_not_import_database_or_repositories_when_present() -> None:
    if not HR_FRONTEND.exists():
        return
    forbidden_imports = {"sqlite3"}
    offenders: list[str] = []
    for path in HR_FRONTEND.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden_imports or "repositories" in alias.name:
                        offenders.append(f"{path.relative_to(PACKAGE_ROOT)}:{alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module in forbidden_imports or "repositories" in module or "db.connection" in module:
                    offenders.append(f"{path.relative_to(PACKAGE_ROOT)}:{module}")
    assert offenders == []


def test_hr_repositories_and_queries_do_not_use_legacy_identity_or_schema_mutation() -> None:
    roots = (
        PACKAGE_ROOT / "backend" / "infrastructure" / "db" / "repositories",
        PACKAGE_ROOT / "backend" / "application" / "queries",
    )
    targets = [
        path for root in roots for path in root.glob("*hr*.py")
    ] + [
        PACKAGE_ROOT / "backend" / "infrastructure" / "db" / "repositories" / name
        for name in (
            "employee_repository.py",
            "department_repository.py",
            "position_repository.py",
            "attendance_repository.py",
            "attendance_adjustment_repository.py",
            "work_shift_repository.py",
            "leave_repository.py",
            "payroll_repository.py",
            "payroll_payment_repository.py",
        )
    ]
    forbidden = ("lastrowid", "AUTOINCREMENT", "INTEGER PRIMARY KEY", "CREATE TABLE", "ALTER TABLE")
    offenders: list[str] = []
    for path in targets:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{path.relative_to(PACKAGE_ROOT)}:{token}")
        if "int(" in text and "_id" in text:
            offenders.append(f"{path.relative_to(PACKAGE_ROOT)}:int(..._id)")
    assert offenders == []


def test_hr_phase3_frontend_target_structure_exists() -> None:
    expected = {
        HR_FRONTEND / "__init__.py",
        HR_FRONTEND / "hr_view.py",
        HR_FRONTEND / "hr_presenter.py",
        HR_FRONTEND / "hr_routes.py",
        HR_FRONTEND / "hr_view_models.py",
        HR_FRONTEND / "pages" / "overview_page.py",
        HR_FRONTEND / "pages" / "employees_page.py",
        HR_FRONTEND / "pages" / "attendance_page.py",
        HR_FRONTEND / "pages" / "schedules_page.py",
        HR_FRONTEND / "pages" / "leave_page.py",
        HR_FRONTEND / "pages" / "payroll_page.py",
        HR_FRONTEND / "pages" / "evaluations_page.py",
        HR_FRONTEND / "pages" / "settings_page.py",
        HR_FRONTEND / "dialogs" / "employee_dialog.py",
        HR_FRONTEND / "dialogs" / "attendance_dialog.py",
        HR_FRONTEND / "dialogs" / "attendance_adjustment_dialog.py",
        HR_FRONTEND / "dialogs" / "leave_request_dialog.py",
        HR_FRONTEND / "dialogs" / "shift_assignment_dialog.py",
        HR_FRONTEND / "dialogs" / "payroll_run_dialog.py",
        HR_FRONTEND / "dialogs" / "payroll_authorization_dialog.py",
    }
    missing = [str(path.relative_to(PACKAGE_ROOT)) for path in expected if not path.is_file()]
    assert missing == []


def test_hr_frontend_does_not_execute_sql_or_use_app_container() -> None:
    forbidden_tokens = (
        "SELECT ",
        "INSERT ",
        "UPDATE ",
        "DELETE ",
        "CREATE TABLE",
        "ALTER TABLE",
        "commit(",
        "rollback(",
        "AppContainer",
    )
    offenders: list[str] = []
    for path in HR_FRONTEND.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            if token in text:
                offenders.append(f"{path.relative_to(PACKAGE_ROOT)}:{token}")
    assert offenders == []


def test_hr_main_navigation_uses_canonical_module_factory() -> None:
    main_window = (PACKAGE_ROOT / "interfaz" / "main_window.py").read_text(encoding="utf-8")
    module_loader = (PACKAGE_ROOT / "core" / "ui" / "module_loader.py").read_text(encoding="utf-8")
    assert "from modulos.rrhh import ModuloRRHH" not in main_window
    assert "modulos.rrhh" not in module_loader
    assert "CanonicalHRModule" in main_window
    assert " as ModuloRRHH" not in main_window
    assert "core.ui.hr_module_factory" in module_loader


def test_hr_employee_dialog_uses_presenter_catalog_options() -> None:
    dialog = (HR_FRONTEND / "dialogs" / "employee_dialog.py").read_text(encoding="utf-8")
    employees_page = (HR_FRONTEND / "pages" / "employees_page.py").read_text(encoding="utf-8")
    assert "HREmployeeFormOptionsViewModel" in dialog
    assert "options.departments" in dialog
    assert "options.positions" in dialog
    assert "options.contract_types" in dialog
    assert "options.payment_frequencies" in dialog
    assert "load_employee_form_options" in employees_page
    assert "submit_create_employee" in employees_page
    assert "submit_update_employee" in employees_page
    assert "ContractType." not in dialog
    assert "PaymentFrequency." not in dialog


def test_hr_module_factory_does_not_import_pyqt_at_module_import_time() -> None:
    factory = (PACKAGE_ROOT / "core" / "ui" / "hr_module_factory.py").read_text(encoding="utf-8")
    package_init = (HR_FRONTEND / "__init__.py").read_text(encoding="utf-8")
    assert "from PyQt5" not in factory
    assert "import PyQt5" not in factory
    assert "from .hr_view import HRView" not in package_init.split("def __getattr__", 1)[0]


def test_hr_personal_page_uses_context_menu_for_row_actions() -> None:
    employees_page = (HR_FRONTEND / "pages" / "employees_page.py").read_text(encoding="utf-8")
    assert "QMenu" in employees_page
    assert "_open_row_actions" in employees_page
    assert "submit_deactivate_employee" in employees_page
    assert "load_employee_form(employee_id)" in employees_page


def test_hr_phase9_enterprise_ui_uses_standard_states_navigation_and_pagination() -> None:
    hr_view = (HR_FRONTEND / "hr_view.py").read_text(encoding="utf-8")
    employees_page = (HR_FRONTEND / "pages" / "employees_page.py").read_text(encoding="utf-8")
    assert "QListWidget" in hr_view
    assert "MINIMUM_WIDTH_FOR_1366" in hr_view
    assert "setMinimumSize" in hr_view
    assert "DebouncedSearchInput" in employees_page
    assert "PaginationBar" in employees_page
    assert "EmptyState" in employees_page
    assert "LoadingState" in employees_page
<<<<<<< HEAD
    assert "setToolTip" in employees_page
=======
    assert "set_action_button" in employees_page or "set_status_badge" in employees_page
>>>>>>> 5f7df5247ec66f7297adb53c0d2e32ee56e33c23
    assert "👔" not in hr_view
    assert "📅" not in hr_view
    assert "💸" not in hr_view


def test_hr_phase9_pages_have_empty_loading_and_pagination_states() -> None:
    pages = ("attendance_page.py", "employees_page.py", "leave_page.py", "payroll_page.py", "schedules_page.py")
    missing: list[str] = []
    for page in pages:
        text = (HR_FRONTEND / "pages" / page).read_text(encoding="utf-8")
<<<<<<< HEAD
        for token in ("EmptyState", "LoadingState", "PaginationBar", "setToolTip"):
=======
        for token in ("EmptyState", "LoadingState", "PaginationBar", "set_status_badge"):
>>>>>>> 5f7df5247ec66f7297adb53c0d2e32ee56e33c23
            if token not in text:
                missing.append(f"{page}:{token}")
    assert missing == []


def test_hr_phase9_frontend_has_no_local_hardcoded_styles_or_colors() -> None:
    forbidden_tokens = ("setStyleSheet", "#0", "#1", "#2", "#3", "#4", "#5", "#6", "#7", "#8", "#9", "#A", "#B", "#C", "#D", "#E", "#F", "background-color", "color:")
    offenders: list[str] = []
    targets = list(HR_FRONTEND.rglob("*.py")) + [PACKAGE_ROOT / "frontend" / "desktop" / "components" / "status_badge.py"]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            if token in text:
                offenders.append(f"{path.relative_to(PACKAGE_ROOT)}:{token}")
    assert offenders == []


def test_hr_phase10_legacy_runtime_paths_are_removed() -> None:
    removed = (
        PACKAGE_ROOT / "modulos" / "rrhh.py",
        PACKAGE_ROOT / "modulos" / "rrhh_turnos.py",
        PACKAGE_ROOT / "core" / "rrhh",
        PACKAGE_ROOT / "core" / "services" / "rrhh_service.py",
        PACKAGE_ROOT / "core" / "services" / "rrhh_catalog_service.py",
        PACKAGE_ROOT / "core" / "services" / "rrhh_turnos_service.py",
        PACKAGE_ROOT / "core" / "services" / "hr_rule_engine.py",
        PACKAGE_ROOT / "core" / "use_cases" / "nomina.py",
    )
    assert [path for path in removed if path.exists()] == []


def test_hr_phase10_runtime_code_has_no_legacy_hr_imports_or_fallbacks() -> None:
    roots = (
        PACKAGE_ROOT / "backend",
        PACKAGE_ROOT / "core",
        PACKAGE_ROOT / "frontend",
        PACKAGE_ROOT / "interfaz",
        PACKAGE_ROOT / "application",
        PACKAGE_ROOT / "modulos",
    )
    forbidden = (
        "modulos.rrhh",
        "rrhh_turnos",
        "core.rrhh",
        "core.services.rrhh",
        "rrhh_service",
        "rrhh_catalog_service",
        "rrhh_turnos_service",
        "core.use_cases.nomina",
        "GestionarNominaUC",
        "uc_nomina",
        "hr_rule_engine",
    )
    offenders: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                if token in text:
                    offenders.append(f"{path.relative_to(PACKAGE_ROOT)}:{token}")
    assert offenders == []


def test_hr_ui_enterprise_components_exist() -> None:
    components = PACKAGE_ROOT / "frontend" / "desktop" / "components"
    expected = {
        "buttons.py",
        "cards.py",
        "filter_bar.py",
        "icons.py",
        "kpi_bar.py",
        "kpi_card.py",
        "page_header.py",
        "tables.py",
        "tooltip.py",
    }
    missing = [name for name in expected if not (components / name).is_file()]
    assert missing == []


def test_hr_pages_use_enterprise_page_structure() -> None:
    page_files = (
        "overview_page.py",
        "employees_page.py",
        "attendance_page.py",
        "leave_page.py",
        "payroll_page.py",
        "schedules_page.py",
        "evaluations_page.py",
        "settings_page.py",
    )
    missing: list[str] = []
    for page in page_files:
        text = (HR_FRONTEND / "pages" / page).read_text(encoding="utf-8")
        if "PageHeader" not in text:
            missing.append(f"{page}:PageHeader")
        if "Icons." not in text:
            missing.append(f"{page}:Icons")
    assert missing == []


def test_hr_operational_pages_use_standard_tables_and_actions() -> None:
    page_files = ("employees_page.py", "attendance_page.py", "leave_page.py", "payroll_page.py", "schedules_page.py")
    offenders: list[str] = []
    for page in page_files:
        text = (HR_FRONTEND / "pages" / page).read_text(encoding="utf-8")
        if "StandardTable" not in text:
            offenders.append(f"{page}:StandardTable")
        if "QTableWidget(" in text:
            offenders.append(f"{page}:QTableWidget")
        if "QPushButton(" in text:
            offenders.append(f"{page}:QPushButton")
    assert offenders == []


def test_hr_overview_uses_canonical_kpi_bar() -> None:
    overview = (HR_FRONTEND / "pages" / "overview_page.py").read_text(encoding="utf-8")
    assert "KPIBar" in overview
    assert "KPIDTO" in overview
    assert "QGridLayout" not in overview
    assert "KPICard" not in overview or "KPIBar" in overview
