"""Architecture guardrails for the finance bounded context (FASES 19/21).

Enforced invariants:
- finance UI: no SQL, no sqlite3, no repositories, no db connections,
  no commit/rollback, no AppContainer, no hardcoded hex colors;
- finance domain: pure (no PyQt/sqlite/infrastructure imports), no float money;
- finance backend: no integer id casts, no lastrowid, no AUTOINCREMENT;
- schema: only the migration entry point executes finance DDL.
"""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UI_DIR = PROJECT_ROOT / "frontend" / "desktop" / "modules" / "finance"
DOMAIN_DIR = PROJECT_ROOT / "backend" / "domain" / "finance"
APP_DIRS = [
    PROJECT_ROOT / "backend" / "application" / "event_handlers" / "finance",
    PROJECT_ROOT / "backend" / "application" / "use_cases" / "finance",
    PROJECT_ROOT / "backend" / "application" / "services" / "finance",
    PROJECT_ROOT / "backend" / "application" / "queries" / "finance",
    PROJECT_ROOT / "backend" / "infrastructure" / "db" / "repositories" / "finance",
]


def _py_files(directory: Path):
    return sorted(directory.rglob("*.py"))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestFinanceUiIsClean:
    def test_no_sql_in_ui(self):
        sql_pattern = re.compile(
            r"\b(SELECT|INSERT INTO|UPDATE\s+\w+\s+SET|DELETE FROM|CREATE TABLE|ALTER TABLE)\b",
            re.IGNORECASE)
        for path in _py_files(UI_DIR):
            assert not sql_pattern.search(_read(path)), f"SQL en UI: {path}"

    def test_no_sqlite_or_connections_in_ui(self):
        for path in _py_files(UI_DIR):
            source = _read(path)
            assert "import sqlite3" not in source, f"sqlite3 en UI: {path}"
            if path.name != "finance_routes.py":  # composition root wires the connection
                assert "db_conn" not in source, f"db_conn en UI: {path}"

    def test_no_repository_imports_in_ui(self):
        forbidden = re.compile(
            r"from backend\.infrastructure\.db\.repositories|from repositories\.")
        for path in _py_files(UI_DIR):
            if path.name == "finance_routes.py":
                continue  # composition root is the single allowed wiring point
            assert not forbidden.search(_read(path)), f"repositorio importado en UI: {path}"

    def test_no_commit_rollback_in_ui(self):
        pattern = re.compile(r"\.(commit|rollback)\(")
        for path in _py_files(UI_DIR):
            assert not pattern.search(_read(path)), f"commit/rollback en UI: {path}"

    def test_no_hardcoded_hex_colors_in_ui(self):
        pattern = re.compile(r"#[0-9a-fA-F]{6}\b")
        for path in _py_files(UI_DIR):
            assert not pattern.search(_read(path)), f"color hardcodeado en UI: {path}"

    def test_no_app_container_in_view_or_pages(self):
        for path in _py_files(UI_DIR):
            if path.name == "finance_routes.py":
                continue
            assert "AppContainer" not in _read(path), f"AppContainer en UI: {path}"

    def test_no_except_exception_pass(self):
        pattern = re.compile(r"except Exception:\s*\n\s*pass")
        for path in _py_files(UI_DIR):
            assert not pattern.search(_read(path)), f"except-pass silencioso: {path}"


class TestFinanceDomainIsPure:
    def test_no_framework_imports_in_domain(self):
        forbidden = re.compile(
            r"import sqlite3|from PyQt5|from backend\.infrastructure|from frontend\.")
        for path in _py_files(DOMAIN_DIR):
            assert not forbidden.search(_read(path)), f"dependencia impura en dominio: {path}"

    def test_no_float_money_in_domain(self):
        pattern = re.compile(r"\bfloat\(")
        for path in _py_files(DOMAIN_DIR):
            assert not pattern.search(_read(path)), f"float() en dominio: {path}"


class TestFinanceIdentityRules:
    def test_no_integer_id_casts(self):
        pattern = re.compile(
            r"int\((account|entry|journal|period|receivable|payable|payment|budget|"
            r"asset|customer|supplier|branch|operation|obligation|instrument|"
            r"reconciliation|statement)[a-z_]*_id\)")
        for directory in APP_DIRS + [DOMAIN_DIR, UI_DIR]:
            for path in _py_files(directory):
                assert not pattern.search(_read(path)), f"cast int de id: {path}"

    def test_no_lastrowid_or_autoincrement(self):
        for directory in APP_DIRS + [DOMAIN_DIR]:
            for path in _py_files(directory):
                source = _read(path)
                assert "lastrowid" not in source, f"lastrowid: {path}"
                assert "AUTOINCREMENT" not in source.upper(), f"AUTOINCREMENT: {path}"

    def test_schema_has_no_autoincrement_or_real_money(self):
        schema = _read(PROJECT_ROOT / "backend" / "infrastructure" / "db" / "schema"
                       / "finance_schema.py")
        ddl_body = schema[schema.index('_DDL = """'):]
        assert "AUTOINCREMENT" not in ddl_body.upper(), "AUTOINCREMENT en el DDL financiero"
        assert " REAL" not in ddl_body, "columna REAL (float) en el esquema financiero"

    def test_new_uuid_is_the_only_id_generator(self):
        pattern = re.compile(r"uuid\.uuid4\(\)|uuid4\(\)")
        for directory in APP_DIRS + [DOMAIN_DIR, UI_DIR]:
            for path in _py_files(directory):
                assert not pattern.search(_read(path)), f"generador uuid4 disperso: {path}"


class TestSingleCanonicalRoute:
    def test_only_posting_engine_inserts_journal_entries(self):
        """Ningún módulo operativo escribe directamente en el mayor."""
        pattern = re.compile(r"INSERT INTO journal_entries", re.IGNORECASE)
        allowed = {"journal_entry_repository.py"}
        for directory in [PROJECT_ROOT / "backend", PROJECT_ROOT / "frontend"]:
            for path in _py_files(directory):
                if path.name in allowed:
                    continue
                assert not pattern.search(_read(path)), \
                    f"escritura directa al mayor fuera del repositorio canónico: {path}"

    def test_handlers_do_not_hardcode_account_codes(self):
        """Los handlers resuelven cuentas por perfil, nunca por código quemado."""
        pattern = re.compile(r"account_for\(")
        get_by_code = re.compile(r"get_by_code\(")
        handlers_dir = PROJECT_ROOT / "backend" / "application" / "event_handlers" / "finance"
        for path in _py_files(handlers_dir):
            assert not get_by_code.search(_read(path)), \
                f"handler resolviendo cuenta por código: {path}"
