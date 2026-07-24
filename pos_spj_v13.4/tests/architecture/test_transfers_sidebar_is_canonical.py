from pathlib import Path


def test_transfers_sidebar_has_no_database_or_legacy_ui_dependencies():
    root = Path(__file__).resolve().parents[2]
    source = (root / "frontend/desktop/modules/transfers/navigation/transfers_sidebar.py").read_text(encoding="utf-8")
    for forbidden in ("sqlite3", "Repository", "modulos.transferencias", "QTabWidget", "setStyleSheet", "TRANSFERENCIAS"):
        assert forbidden not in source
    assert "TransferPermissions" in source
    assert "pending_requests" in source
