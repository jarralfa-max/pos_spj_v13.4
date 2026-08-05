from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_losses_schema_ddl_lives_only_in_migrations():
    offenders = []
    for base in (ROOT / "backend", ROOT / "frontend", ROOT / "modulos"):
        for path in base.rglob("*.py"):
            source = path.read_text(encoding="utf-8", errors="ignore")
            if "CREATE TABLE" in source and "loss_" in source.lower():
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders


def test_losses_migration_is_registered_in_engine():
    source = (ROOT / "migrations/engine.py").read_text(encoding="utf-8")
    assert '"174"' in source
    assert "174_losses_bounded_context_schema" in source
