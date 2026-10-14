"""Overflow and navigation behavior of the shared viewport, without a database."""

from PyQt5 import sip
from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QLineEdit, QVBoxLayout, QWidget

from frontend.desktop.components.page_viewport import PageViewport
from frontend.desktop.shell.application_shell.content_host import ContentHost
from frontend.desktop.shell.routing.cache_policy import CachePolicy
from tests.ui.shell.test_content_host import _result, _route


def settle(app):
    for _ in range(8):
        app.processEvents()


def position(viewport):
    return (viewport.horizontalScrollBar().value(), viewport.verticalScrollBar().value())


def scroll(viewport, x, y):
    viewport.horizontalScrollBar().setValue(x)
    viewport.verticalScrollBar().setValue(y)


def show_page(host, name, page, policy=CachePolicy.KEEP_ALIVE):
    host.display(_result(_route(name, cache_policy=policy), page))


def large_page():
    page = QWidget()
    page.setMinimumSize(1600, 1800)
    return page


def test_new_route_starts_at_origin_and_cached_routes_restore_both_axes(qt_font_resources):
    app = qt_font_resources
    host = ContentHost()
    host.resize(640, 480)
    first, second = large_page(), large_page()
    try:
        show_page(host, "first", first)
        host.show()
        settle(app)
        scroll(host.page_viewport, 180, 520)
        show_page(host, "second", second)
        settle(app)
        assert position(host.page_viewport) == (0, 0)
        scroll(host.page_viewport, 90, 260)
        show_page(host, "first", first)
        settle(app)
        assert position(host.page_viewport) == (180, 520)
        show_page(host, "second", second)
        settle(app)
        assert position(host.page_viewport) == (90, 260)
    finally:
        sip.delete(host)


def test_small_route_does_not_erase_cached_large_route_scroll(qt_font_resources):
    app = qt_font_resources
    host = ContentHost()
    host.resize(640, 480)
    first, small = large_page(), QWidget()
    try:
        show_page(host, "large", first)
        host.show()
        settle(app)
        scroll(host.page_viewport, 180, 520)
        show_page(host, "small", small)
        settle(app)
        assert position(host.page_viewport) == (0, 0)
        assert host.page_viewport.verticalScrollBar().maximum() == 0
        show_page(host, "large", first)
        settle(app)
        assert position(host.page_viewport) == (180, 520)
    finally:
        sip.delete(host)


def test_rapid_navigation_restores_only_the_final_page(qt_font_resources):
    app = qt_font_resources
    host = ContentHost()
    host.resize(640, 480)
    first, second = large_page(), large_page()
    try:
        show_page(host, "first", first)
        host.show()
        settle(app)
        scroll(host.page_viewport, 140, 390)
        show_page(host, "second", second)
        show_page(host, "first", first)
        settle(app)
        assert position(host.page_viewport) == (140, 390)
        show_page(host, "second", second)
        host.clear()
        settle(app)
        assert host.page_viewport.verticalScrollBar().maximum() == 0
    finally:
        sip.delete(host)


def test_recreated_route_does_not_inherit_discarded_widget_position(qt_font_resources):
    app = qt_font_resources
    host = ContentHost()
    host.resize(640, 480)
    try:
        show_page(host, "route", large_page(), CachePolicy.RECREATE_ON_NAVIGATION)
        host.show()
        settle(app)
        scroll(host.page_viewport, 180, 520)
        show_page(host, "route", large_page(), CachePolicy.RECREATE_ON_NAVIGATION)
        settle(app)
        assert position(host.page_viewport) == (0, 0)
    finally:
        sip.delete(host)


def test_hidden_page_shrinking_clamps_restored_position_to_new_range(qt_font_resources):
    app = qt_font_resources
    host = ContentHost()
    host.resize(640, 480)
    first, second = large_page(), large_page()
    try:
        show_page(host, "first", first)
        host.show()
        settle(app)
        scroll(host.page_viewport, 900, 1300)
        show_page(host, "second", second)
        settle(app)
        first.setMinimumSize(800, 600)
        show_page(host, "first", first)
        settle(app)
        assert position(host.page_viewport) == (
            host.page_viewport.horizontalScrollBar().maximum(),
            host.page_viewport.verticalScrollBar().maximum(),
        )
        assert 0 < position(host.page_viewport)[1] < 1300
    finally:
        sip.delete(host)


def test_dynamic_form_growth_and_removal_keep_window_size_and_input(qt_font_resources):
    app = qt_font_resources
    viewport = PageViewport()
    content = QWidget()
    layout = QVBoxLayout(content)
    field = QLineEdit("Captura conservada")
    layout.addWidget(field)
    viewport.set_page(content)
    viewport.resize(640, 480)
    try:
        viewport.show()
        settle(app)
        assert content.size() == viewport.viewport_size()
        extra = [QLineEdit(f"Dato {index}") for index in range(50)]
        for widget in extra:
            layout.addWidget(widget)
        settle(app)
        assert viewport.size().width() == 640 and viewport.size().height() == 480
        assert viewport.verticalScrollBar().maximum() > 0
        for widget in extra:
            layout.removeWidget(widget)
            sip.delete(widget)
        settle(app)
        assert viewport.verticalScrollBar().maximum() == 0
        assert field.text() == "Captura conservada"
    finally:
        sip.delete(viewport)


def test_keyboard_focus_reveals_fields_and_scrollbar_accepts_navigation(qt_font_resources):
    app = qt_font_resources
    viewport = PageViewport()
    content = QWidget()
    layout = QVBoxLayout(content)
    fields = [QLineEdit(f"Campo {index}") for index in range(40)]
    for field in fields:
        layout.addWidget(field)
    viewport.set_page(content)
    viewport.resize(640, 300)
    try:
        viewport.show()
        viewport.activateWindow()
        settle(app)
        fields[0].setFocus()
        for _ in fields[1:]:
            QTest.keyClick(app.focusWidget(), Qt.Key_Tab)
        settle(app)
        assert app.focusWidget() is fields[-1]
        rect = QRect(fields[-1].mapTo(viewport.viewport(), QPoint()), fields[-1].size())
        assert viewport.viewport().rect().contains(rect)
        assert viewport.verticalScrollBar().value() > 0
        bar = viewport.verticalScrollBar()
        bar.setFocus()
        QTest.keyClick(bar, Qt.Key_Home)
        assert bar.value() == 0
        QTest.keyClick(bar, Qt.Key_End)
        assert bar.value() == bar.maximum()
    finally:
        sip.delete(viewport)


def test_replacing_content_and_taking_it_keep_qt_ownership_contract(qt_font_resources):
    app = qt_font_resources
    viewport = PageViewport()
    first, second = large_page(), QWidget()
    try:
        viewport.set_page(first)
        viewport.resize(640, 480)
        viewport.show()
        settle(app)
        scroll(viewport, 180, 520)
        viewport.set_page(second)
        settle(app)
        assert sip.isdeleted(first)
        assert viewport.page() is second
        assert position(viewport) == (0, 0)
        assert viewport.takeWidget() is second
        assert viewport.page() is None
        assert not sip.isdeleted(second)
        sip.delete(second)
    finally:
        sip.delete(viewport)
