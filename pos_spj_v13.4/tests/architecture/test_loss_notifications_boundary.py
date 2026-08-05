from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_loss19_has_policies_recipients_channels_audit_and_idempotency():
    domain=(ROOT/"backend/domain/losses/notifications.py").read_text(encoding="utf-8");repository=(ROOT/"backend/infrastructure/persistence/loss_notification_repository.py").read_text(encoding="utf-8");migration=(ROOT/"migrations/standalone/174_losses_bounded_context_schema.py").read_text(encoding="utf-8")
    assert "NotificationChannel.IN_APP" in domain and "NotificationChannel.WHATSAPP" in domain
    for table in ("loss_notification_subscriptions","loss_notification_deliveries","loss_notification_audit"):assert table in migration
    assert "loss_processed_operations" in repository and "source_event_id,recipient_user_id,channel" in migration
def test_loss19_whatsapp_is_behind_an_injected_adapter():
    router=(ROOT/"backend/application/losses/notifications.py").read_text(encoding="utf-8");adapter=(ROOT/"backend/infrastructure/integrations/loss_notification_senders.py").read_text(encoding="utf-8")
    assert "self._whatsapp" in router and "send_message" in adapter and "idempotency_key" in adapter
