"""PROC-3: repositories never own the transaction boundary — only
MeatProcessingUnitOfWork may call connection.commit()/rollback() (CLAUDE.md
rules #9-11: 'PyQt no debe hacer commit()/rollback()'; 'Solo migrations/ puede
modificar schema')."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPO_DIR = ROOT / "backend/infrastructure/db/repositories/meat_processing"


def test_entity_repositories_never_call_commit_or_rollback():
    for path in REPO_DIR.glob("*.py"):
        if path.name == "unit_of_work.py":
            continue
        source = path.read_text(encoding="utf-8")
        assert ".commit()" not in source, f"{path} must not commit directly"
        assert ".rollback()" not in source, f"{path} must not rollback directly"


def test_only_the_schema_module_and_its_migration_define_ddl():
    schema_source = (ROOT / "backend/infrastructure/db/schema/meat_processing_schema.py"
                      ).read_text(encoding="utf-8")
    assert "CREATE TABLE" in schema_source
    for path in REPO_DIR.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "CREATE TABLE" not in source, f"{path} must not define schema"
        assert "ALTER TABLE" not in source, f"{path} must not define schema"
