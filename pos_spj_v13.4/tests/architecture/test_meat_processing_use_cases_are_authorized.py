"""PROC-6 architecture guardrails: every use case re-validates its own
permission (no relying on the UI to hide a button) and none of them write raw
SQL — everything goes through MeatProcessingUnitOfWork's repositories."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
USE_CASES_DIR = ROOT / "backend/application/meat_processing/use_cases"
# _shared.py is helper code (error mapping, scope enforcement), not a use case
# class — it neither authorizes nor constructs a UnitOfWork itself.
_NOT_A_USE_CASE_MODULE = {"__init__.py", "_shared.py"}


def test_every_use_case_class_calls_authorization_require():
    for path in USE_CASES_DIR.glob("*.py"):
        if path.name in _NOT_A_USE_CASE_MODULE:
            continue
        source = path.read_text(encoding="utf-8")
        class_count = source.count("class ")
        require_count = source.count("self._auth.require(")
        assert require_count >= class_count, (
            f"{path} defines {class_count} use case(s) but only "
            f"{require_count} call self._auth.require(...)")


def test_use_cases_never_execute_raw_sql():
    for path in USE_CASES_DIR.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert ".execute(" not in source or "connection.execute(" not in source
        assert "CREATE TABLE" not in source
        assert "sqlite3" not in source


def test_use_cases_only_mutate_through_the_unit_of_work():
    for path in USE_CASES_DIR.glob("*.py"):
        if path.name in _NOT_A_USE_CASE_MODULE:
            continue
        source = path.read_text(encoding="utf-8")
        assert "MeatProcessingUnitOfWork(connection)" in source
