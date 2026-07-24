from pathlib import Path


def test_transfers_security_is_defined_outside_frontend_and_uses_granular_permissions():
    source = (Path(__file__).resolve().parents[2] / "backend/application/transfers/authorization.py").read_text(encoding="utf-8")
    assert "can_access_transfer_scope" in source
    assert "record_hot_authorization" in source
    assert "TransferPermissions" not in source  # authorization receives codes, not UI roles
