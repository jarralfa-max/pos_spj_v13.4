from pathlib import Path


def test_transfers_domain_has_no_float_quantities():
    source = Path("backend/domain/transfers").read_text if False else "\n".join(
        path.read_text(encoding="utf-8") for path in Path("backend/domain/transfers").rglob("*.py"))
    assert "float(" not in source
    assert "REAL" not in source
