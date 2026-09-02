from datetime import datetime, timezone

from frontend.desktop.shell.application_shell.notification_drawer import (
    NotificationDrawer,
    NotificationItem,
)

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _item(notification_id="n1", **overrides) -> NotificationItem:
    fields = dict(notification_id=notification_id, title="Título", message="Mensaje", created_at=T0)
    fields.update(overrides)
    return NotificationItem(**fields)


def test_starts_closed_and_empty():
    drawer = NotificationDrawer()
    assert drawer.is_open is False
    assert drawer.unread_count() == 0
    assert drawer.all_notifications() == ()


def test_add_notification_increases_unread_count():
    drawer = NotificationDrawer()
    drawer.add_notification(_item())
    assert drawer.unread_count() == 1
    assert len(drawer.all_notifications()) == 1


def test_add_notification_already_read_does_not_count_as_unread():
    drawer = NotificationDrawer()
    drawer.add_notification(_item(read=True))
    assert drawer.unread_count() == 0


def test_mark_read_decreases_unread_count():
    drawer = NotificationDrawer()
    drawer.add_notification(_item())
    drawer.mark_read("n1")
    assert drawer.unread_count() == 0


def test_mark_read_unknown_id_is_a_no_op():
    drawer = NotificationDrawer()
    drawer.mark_read("does-not-exist")  # must not raise
    assert drawer.unread_count() == 0


def test_clear_removes_everything():
    drawer = NotificationDrawer()
    drawer.add_notification(_item())
    drawer.add_notification(_item(notification_id="n2"))
    drawer.clear()
    assert drawer.unread_count() == 0
    assert drawer.all_notifications() == ()


def test_open_close_toggle_track_is_open_without_show():
    drawer = NotificationDrawer()
    drawer.open()
    assert drawer.is_open is True
    drawer.close()
    assert drawer.is_open is False
    drawer.toggle()
    assert drawer.is_open is True
    drawer.toggle()
    assert drawer.is_open is False


def test_close_when_already_closed_does_not_emit_closed_signal():
    drawer = NotificationDrawer()
    calls = []
    drawer.closed.connect(lambda: calls.append(1))
    drawer.close()
    assert calls == []


def test_close_when_open_emits_closed_signal():
    drawer = NotificationDrawer()
    calls = []
    drawer.closed.connect(lambda: calls.append(1))
    drawer.open()
    drawer.close()
    assert calls == [1]


def test_unread_count_changed_emits_on_add_and_mark_read():
    drawer = NotificationDrawer()
    counts = []
    drawer.unread_count_changed.connect(counts.append)
    drawer.add_notification(_item())
    drawer.mark_read("n1")
    assert counts == [1, 0]


def test_activating_list_item_marks_read_and_emits_notification_activated():
    drawer = NotificationDrawer()
    drawer.add_notification(_item())
    activated = []
    drawer.notification_activated.connect(activated.append)
    list_item = drawer._list.item(0)
    drawer._on_item_activated(list_item)
    assert activated == ["n1"]
    assert drawer.unread_count() == 0
