from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOMAIN = ROOT / "backend/domain/losses"


def test_losses_domain_has_no_float_annotations_or_uuid_generators():
    offenders = []
    for path in DOMAIN.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if ": float" in source or "uuid.uuid4" in source:
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders


def test_losses_domain_does_not_import_ui_database_or_repositories():
    forbidden = ("PyQt", "sqlite3", "frontend.", "repositories.", "infrastructure.db")
    offenders = []
    for path in DOMAIN.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if any(token in source for token in forbidden):
            offenders.append(str(path.relative_to(ROOT)))
    assert not offenders
