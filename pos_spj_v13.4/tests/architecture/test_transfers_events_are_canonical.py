from pathlib import Path


def test_transfers_domain_does_not_publish_legacy_event_names():
    source = (Path(__file__).resolve().parents[2] / "backend/domain/transfers/events.py").read_text(encoding="utf-8")
    assert "TRASPASO_" not in source
    assert "TRANSFER_DISPATCHED" in source
    assert "ALL_TRANSFER_EVENTS" in source
