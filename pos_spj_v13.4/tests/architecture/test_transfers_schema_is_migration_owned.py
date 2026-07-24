from pathlib import Path


def test_transfers_schema_is_registered_by_the_single_canonical_migration():
    root = Path(__file__).resolve().parents[2]
    engine = (root / "migrations/engine.py").read_text(encoding="utf-8")
    migration = root / "migrations/standalone/154_transfers_bounded_context_schema.py"
    assert '"154",  "migrations.standalone.154_transfers_bounded_context_schema"' in engine
    assert migration.exists()
    assert not (root / "migrations/standalone/135_transfers_bounded_context_schema.py").exists()
