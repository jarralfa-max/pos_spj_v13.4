from frontend.desktop.shell.application_shell.top_bar import TopBar
from tests.ui.shell.conftest import make_context


def test_breadcrumb_starts_empty():
    bar = TopBar()
    assert bar.breadcrumb_text == ""


def test_set_breadcrumb_joins_with_separator():
    bar = TopBar()
    bar.set_breadcrumb(("Ventas", "Punto de Venta"))
    assert bar.breadcrumb_text == "Ventas › Punto de Venta"


def test_set_breadcrumb_empty_tuple_clears_text():
    bar = TopBar()
    bar.set_breadcrumb(("Ventas",))
    bar.set_breadcrumb(())
    assert bar.breadcrumb_text == ""


def test_set_context_shows_branch_and_user():
    bar = TopBar()
    bar.set_context(make_context(branch_name="Sucursal Norte", user_name="Ana Ruiz"))
    assert "Sucursal Norte" in bar.context_text
    assert "Ana Ruiz" in bar.context_text


def test_unread_notification_count_starts_at_zero():
    bar = TopBar()
    assert bar.unread_notification_count == 0


def test_set_unread_notification_count_updates_tooltip():
    bar = TopBar()
    bar.set_unread_notification_count(3)
    assert bar.unread_notification_count == 3
    assert "3" in bar._notifications_button.toolTip()


def test_notifications_button_click_emits_toggle_signal():
    bar = TopBar()
    calls = []
    bar.notifications_toggled.connect(lambda: calls.append(1))
    bar._notifications_button.click()
    assert calls == [1]
