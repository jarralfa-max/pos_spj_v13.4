"""Architecture tests for the configuracion module (FASE 7)."""

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
CONFIGURACION_UI = PACKAGE_ROOT / "modulos" / "configuracion.py"
SETTINGS_COMMANDS = PACKAGE_ROOT / "backend" / "application" / "commands" / "settings_commands.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def test_configuracion_ui_has_no_direct_sql():
    """The configuracion UI module must not execute SQL directly."""
    src = _read(CONFIGURACION_UI)
    forbidden = ["cursor.execute(", "conn.execute(", ".execute(\"SELECT", ".execute(\"INSERT", ".execute(\"UPDATE", ".execute(\"DELETE"]
    violations = [f for f in forbidden if f in src]
    assert not violations, f"Direct SQL found in configuracion.py: {violations}"


def test_configuracion_ui_has_no_commit_or_rollback():
    """The configuracion UI module must not call commit() or rollback()."""
    src = _read(CONFIGURACION_UI)
    assert ".commit()" not in src, "configuracion.py calls .commit() directly"
    assert ".rollback()" not in src, "configuracion.py calls .rollback() directly"


def test_settings_commands_use_str_ids():
    """All ID fields in settings commands must be str, not int."""
    src = _read(SETTINGS_COMMANDS)
    forbidden_patterns = ["branch_id: int", "user_id: int", "role_id: int", "rule_id: int"]
    violations = [p for p in forbidden_patterns if p in src]
    assert not violations, f"Integer ID fields found in settings_commands.py: {violations}"


def test_settings_commands_have_no_int_defaults():
    """Settings command ID fields must default to empty string, not zero."""
    src = _read(SETTINGS_COMMANDS)
    # ID fields with int defaults like `branch_id: str = 0` would be a bug
    assert 'branch_id: str = 0' not in src
    assert 'user_id: str = 0' not in src
    assert 'role_id: str = 0' not in src


def test_settings_use_cases_exist():
    """All canonical settings use case files must exist."""
    use_cases_dir = PACKAGE_ROOT / "backend" / "application" / "use_cases"
    required = [
        "save_company_profile_use_case.py",
        "save_system_setting_use_case.py",
        "save_smtp_settings_use_case.py",
        "save_happy_hour_rule_use_case.py",
        "save_user_use_case.py",
        "save_role_permissions_use_case.py",
        "execute_monthly_closing_use_case.py",
    ]
    missing = [f for f in required if not (use_cases_dir / f).exists()]
    assert not missing, f"Missing settings use case files: {missing}"


def test_settings_commands_file_exists():
    """settings_commands.py must exist in the commands directory."""
    assert SETTINGS_COMMANDS.exists(), "backend/application/commands/settings_commands.py is missing"


def test_execute_monthly_closing_requires_period_and_branch():
    """ExecuteMonthlyClosingCommand must validate period and branch_id."""
    src = _read(SETTINGS_COMMANDS)
    assert '"period is required"' in src
    assert '"branch_id is required"' in src


def test_save_happy_hour_rule_validates_discount():
    """SaveHappyHourRuleCommand must validate discount_percent > 0."""
    src = _read(SETTINGS_COMMANDS)
    assert "discount_percent" in src
    assert "discount_percent must be greater than zero" in src
