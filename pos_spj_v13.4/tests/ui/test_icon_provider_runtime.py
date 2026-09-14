"""Protect native icon states, scaling and binding lifetime with real Qt."""
from collections import Counter

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QEvent, QSize
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QAction, QLabel, QPushButton

from frontend.desktop.components.buttons import IconButton
from frontend.desktop.components.icons import IconProvider, Icons, icon_accessible_name
from frontend.desktop.themes.theme_manager import ThemeManager


@pytest.fixture
def manager(qt_font_resources, monkeypatch):
    instance = ThemeManager()
    monkeypatch.setattr(ThemeManager, "_instance", instance)
    instance.apply(qt_font_resources, "light")
    return instance


def stroke(pixmap):
    image = pixmap.toImage()
    pixels = Counter(image.pixelColor(x, y).name().upper()
                     for x in range(image.width()) for y in range(image.height())
                     if image.pixelColor(x, y).alpha() == 255)
    assert pixels, "The vector must contain visible strokes"
    return pixels.most_common(1)[0][0]


@pytest.mark.parametrize("size", [16, 20, 32, 64, 128])
def test_vector_icon_renders_at_requested_size_without_raster_cap(manager, size):
    icon = IconProvider.icon(Icons.ADD)
    assert icon.actualSize(QSize(size, size)) == QSize(size, size)
    rendered = icon.pixmap(size, size)
    assert rendered.size() == QSize(size, size)
    assert stroke(rendered) == manager.colors().TEXT_SECONDARY


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_checked_icon_uses_selected_color_and_disabled_wins(manager, theme):
    manager.set_theme(theme)
    icon = IconProvider.icon(Icons.ADD)
    colors = manager.colors()
    assert stroke(icon.pixmap(32, 32, QIcon.Normal, QIcon.Off)) == colors.TEXT_SECONDARY
    assert stroke(icon.pixmap(32, 32, QIcon.Normal, QIcon.On)) == colors.PRIMARY_DEFAULT
    assert stroke(icon.pixmap(32, 32, QIcon.Disabled, QIcon.On)) == colors.TEXT_DISABLED


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("state,token", [("danger", "DANGER_DEFAULT"), ("success", "SUCCESS_DEFAULT"),
                                       ("warning", "WARNING_DEFAULT"), ("info", "INFO_DEFAULT"),
                                       ("inverse", "TEXT_INVERSE")])
def test_semantic_states_keep_meaning_when_active_or_selected(manager, theme, state, token):
    manager.set_theme(theme)
    icon = IconProvider.icon(Icons.INFO, state=state)
    for mode in (QIcon.Normal, QIcon.Active, QIcon.Selected):
        for checked in (QIcon.Off, QIcon.On):
            assert stroke(icon.pixmap(32, 32, mode, checked)) == getattr(manager.colors(), token)


@pytest.mark.parametrize("variant", ["primary", "danger"])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_icon_only_filled_button_uses_inverse_icon(manager, qt_font_resources, theme, variant):
    manager.set_theme(theme, app=qt_font_resources)
    button = IconButton(Icons.ADD, "Agregar", variant=variant)
    try:
        assert stroke(button.icon().pixmap(32, 32)) == manager.colors().TEXT_INVERSE
    finally:
        button.deleteLater()


def test_label_binding_tracks_enabled_state_and_accessible_name(manager, qt_font_resources):
    label = QLabel()
    IconProvider.bind(label, Icons.WARNING, state="warning")
    try:
        assert label.accessibleName() == icon_accessible_name(Icons.WARNING)
        assert stroke(label.pixmap()) == manager.colors().WARNING_DEFAULT
        label.setEnabled(False)
        qt_font_resources.processEvents()
        assert stroke(label.pixmap()) == manager.colors().TEXT_DISABLED
        label.setEnabled(True)
        qt_font_resources.processEvents()
        assert stroke(label.pixmap()) == manager.colors().WARNING_DEFAULT
    finally:
        label.deleteLater()


def test_rebinding_disconnects_the_original_manager(manager, monkeypatch, qt_font_resources):
    action = QAction("Acción existente")
    IconProvider.bind(action, Icons.ADD)
    replacement = ThemeManager()
    monkeypatch.setattr(ThemeManager, "_instance", replacement)
    IconProvider.bind(action, Icons.CLOSE)
    before = action.icon().cacheKey()
    manager.set_theme("dark")
    assert action.icon().cacheKey() == before
    replacement.set_theme("dark")
    assert action.icon().cacheKey() != before
    assert action.text() == "Acción existente"
    action.deleteLater()
    qt_font_resources.sendPostedEvents(None, QEvent.DeferredDelete)


def test_deleted_binding_disconnects_and_rebinding_leaves_one_observer(manager, qt_font_resources):
    button = QPushButton("Operación")
    count = manager.receivers(manager.theme_changed)
    IconProvider.bind(button, Icons.ADD)
    old = button._spj_icon_binding
    IconProvider.bind(button, Icons.CLOSE)
    qt_font_resources.sendPostedEvents(None, QEvent.DeferredDelete)
    assert sip.isdeleted(old)
    assert manager.receivers(manager.theme_changed) == count + 1
    button.deleteLater()
    qt_font_resources.sendPostedEvents(None, QEvent.DeferredDelete)
    assert manager.receivers(manager.theme_changed) == count


def test_binding_preserves_custom_accessibility_text(manager):
    button = QPushButton()
    button.setAccessibleName("Eliminar renglón seleccionado")
    button.setToolTip("Eliminar únicamente este renglón")
    IconProvider.bind(button, Icons.DELETE, state="danger")
    assert button.accessibleName() == "Eliminar renglón seleccionado"
    assert button.toolTip() == "Eliminar únicamente este renglón"
    button.deleteLater()


@pytest.mark.parametrize("control", [QLabel, QPushButton])
def test_rebinding_updates_generated_accessibility_name(manager, control):
    widget = control()
    try:
        IconProvider.bind(widget, Icons.CHEVRON_LEFT)
        assert widget.accessibleName() == "Contraer"
        IconProvider.bind(widget, Icons.CHEVRON_RIGHT)
        assert widget.accessibleName() == "Expandir"
        IconProvider.bind(widget, Icons.CLOSE)
        assert widget.accessibleName() == "Cerrar"
    finally:
        widget.deleteLater()


@pytest.mark.parametrize("customize_before_binding", [True, False])
def test_rebinding_preserves_application_accessibility_name(manager, customize_before_binding):
    button = QPushButton()
    try:
        if customize_before_binding:
            button.setAccessibleName("Alternar navegación")
        IconProvider.bind(button, Icons.CHEVRON_LEFT)
        if not customize_before_binding:
            button.setAccessibleName("Alternar navegación")
        IconProvider.bind(button, Icons.CHEVRON_RIGHT)
        assert button.accessibleName() == "Alternar navegación"
    finally:
        button.deleteLater()


@pytest.mark.parametrize("ratio", [1.0, 1.25, 1.5, 2.0, 3.0])
def test_pixmap_preserves_logical_size_at_device_pixel_ratio(manager, ratio):
    pixmap = IconProvider.pixmap(Icons.SEARCH, size=20, device_pixel_ratio=ratio)
    assert pixmap.devicePixelRatioF() == ratio
    assert pixmap.width() == pixmap.height() == round(20 * ratio)


def test_label_refreshes_when_its_window_changes_screen(manager, qt_font_resources, monkeypatch):
    label = QLabel()
    IconProvider.bind(label, Icons.ADD)
    try:
        label.show()
        qt_font_resources.processEvents()
        window = label.windowHandle()
        assert window is not None
        monkeypatch.setattr(label, "devicePixelRatioF", lambda: 2.0)
        window.screenChanged.emit(window.screen())
        assert label.pixmap().size() == QSize(40, 40)
        assert label.pixmap().devicePixelRatioF() == 2.0
    finally:
        label.close()
        label.deleteLater()
        qt_font_resources.sendPostedEvents(None, QEvent.DeferredDelete)


@pytest.mark.parametrize("bind_before_show", [True, False])
def test_binding_visible_label_follows_screen_changes(manager, qt_font_resources, monkeypatch, bind_before_show):
    label = QLabel()
    try:
        if bind_before_show:
            IconProvider.bind(label, Icons.ADD)
        label.show()
        qt_font_resources.processEvents()
        IconProvider.bind(label, Icons.WARNING, state="warning")
        window = label.windowHandle()
        assert window is not None
        monkeypatch.setattr(label, "devicePixelRatioF", lambda: 2.0)
        window.screenChanged.emit(window.screen())
        assert label.pixmap().size() == QSize(40, 40)
        assert label.pixmap().devicePixelRatioF() == 2.0
        assert stroke(label.pixmap()) == manager.colors().WARNING_DEFAULT
    finally:
        label.close()
        label.deleteLater()
        qt_font_resources.sendPostedEvents(None, QEvent.DeferredDelete)
