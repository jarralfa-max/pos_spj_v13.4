from pathlib import Path


def test_transfer_notifications_are_gateway_driven_and_have_no_direct_channels():
    root = Path("pos_spj_v13.4/backend/application/transfers/notification_handlers")
    source = "\n".join(path.read_text() for path in root.glob("*.py"))
    assert "sqlite3" not in source
    assert "requests." not in source
    assert "twilio" not in source.lower()
    assert "WhatsAppTransferNotifier" in source
    assert "InAppTransferNotifier" in source
    assert "TransferRecipientQueryService" in source
    assert "TransferNotificationAuditSink" in source
    assert "was_delivered" in source
