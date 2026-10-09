"""Top-level window bounds include decorations and follow available desktop space."""
import pytest
from PyQt5 import sip
from PyQt5.QtCore import QObject, QRect, QSize, QSettings, Qt, pyqtSignal
from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QTest

from frontend.desktop.components.standard_window import StandardWindow
from frontend.desktop.themes.theme_manager import ThemeManager


class DesktopScreen(QObject):
    availableGeometryChanged = pyqtSignal(QRect)

    def __init__(self, geometry):
        super().__init__()
        self.geometry = QRect(geometry)

    def availableGeometry(self):
        return QRect(self.geometry)

    def change_available_area(self, geometry):
        self.geometry = QRect(geometry)
        self.availableGeometryChanged.emit(self.availableGeometry())


@pytest.fixture
def desktop(qt_font_resources, ui_tmp_path, monkeypatch):
    app = qt_font_resources
    manager = ThemeManager(QSettings(str(ui_tmp_path / "window.ini"), QSettings.IniFormat))
    monkeypatch.setattr(ThemeManager, "_instance", manager)
    manager.apply(app, "light", density="comfortable")
    screen = DesktopScreen(QRect(1920, 40, 1280, 680))
    monkeypatch.setattr(QApplication, "primaryScreen", lambda: screen)
    monkeypatch.setattr(StandardWindow, "screen", lambda self: screen)
    window = StandardWindow(title="JUANIS · Ventana de prueba")
    yield app, manager, screen, window
    sip.delete(window)


def settle(app):
    for _ in range(5):
        app.processEvents()
    QTest.qWait(30)


@pytest.mark.parametrize("available", [QRect(0, 0, 1280, 720), QRect(1920, 40, 1366, 728),
                                      QRect(-1440, -100, 1440, 900), QRect(0, 0, 600, 400)])
def test_first_show_fits_frame_and_titlebar_on_target_screen(desktop, available):
    app, _, screen, window = desktop
    screen.geometry = available
    window.move(-4000, -4000)
    window.show()
    settle(app)
    assert available.contains(window.frameGeometry())
    assert not window.windowIcon().isNull()
    assert window.windowTitle() == "JUANIS · Ventana de prueba"


def test_available_area_change_keeps_visible_window_accessible(desktop):
    app, _, screen, window = desktop
    window.show()
    settle(app)
    screen.change_available_area(QRect(1920, 40, 850, 580))
    settle(app)
    assert screen.availableGeometry().contains(window.frameGeometry())


def test_minimum_recovers_after_small_desktop(desktop):
    app, _, screen, window = desktop
    screen.geometry = QRect(0, 0, 600, 400)
    window.show()
    settle(app)
    window.hide()
    screen.geometry = QRect(0, 0, 1600, 900)
    window.show()
    settle(app)
    assert window.minimumSize() == QSize(640, 480)


@pytest.mark.parametrize("change", ["move", "resize"])
def test_late_platform_geometry_is_brought_back_inside_desktop(desktop, change):
    app, _, screen, window = desktop
    window.show()
    settle(app)
    if change == "move":
        window.move(-4000, 4000)
    else:
        window.resize(4000, 3000)
    settle(app)
    assert screen.availableGeometry().contains(window.frameGeometry())


def test_live_appearance_preserves_window_status_and_user_geometry(desktop):
    app, manager, _, window = desktop
    window.show()
    settle(app)
    window.resize(900, 550)
    window.statusBar().showMessage("Lista para operar")
    settle(app)
    geometry = window.geometry()
    icon = window.windowIcon().cacheKey()
    for theme, density in (("dark", "touch"), ("light", "compact"), ("dark", "comfortable")):
        manager.apply(app, theme, density=density)
        settle(app)
        assert window.geometry() == geometry
        assert window.statusBar().currentMessage() == "Lista para operar"
        assert window.windowIcon().cacheKey() == icon
        assert window.styleSheet() == ""


def test_screen_change_rebinds_available_area_and_disconnects_previous(desktop, monkeypatch):
    app, _, old_screen, window = desktop
    window.show()
    settle(app)
    new_screen = DesktopScreen(QRect(-1440, 0, 1440, 900))
    monkeypatch.setattr(window, "screen", lambda: new_screen)
    # screenChanged follows the window moving onto the new monitor.
    window.move(-1400, 40)
    settle(app)
    handle = window.windowHandle()
    handle.screenChanged.emit(handle.screen())
    settle(app)
    assert new_screen.availableGeometry().contains(window.frameGeometry())
    geometry = window.geometry()
    old_screen.change_available_area(QRect(1920, 0, 600, 400))
    settle(app)
    assert window.geometry() == geometry
    new_screen.change_available_area(QRect(-1440, 0, 800, 600))
    settle(app)
    assert new_screen.availableGeometry().contains(window.frameGeometry())


@pytest.mark.parametrize(("neighbor", "position"), [
    (QRect(1280, 0, 1280, 720), (600, 40)),
    (QRect(-1280, 0, 1280, 720), (-100, 40)),
    (QRect(0, 720, 1280, 720), (100, 300)),
    (QRect(0, -720, 1280, 720), (100, -100)),
])
def test_window_can_cross_connected_monitor_edge(desktop, monkeypatch, neighbor, position):
    app, _, screen, window = desktop
    screen.geometry = QRect(0, 0, 1280, 720)
    adjacent = DesktopScreen(neighbor)
    monkeypatch.setattr(QApplication, "screens", lambda: [screen, adjacent])
    window.resize(800, 500)
    window.move(100, 100)
    window.show()
    settle(app)
    # The centre still belongs to the old monitor. The next movement must
    # remain possible instead of snapping the frame back inside that monitor.
    window.move(*position)
    settle(app)
    # Native borders can shift a negative requested position by a few pixels.
    # The contract is an intermediate frame spanning both monitors, with its
    # centre still on the old one, rather than an exact platform coordinate.
    frame = window.frameGeometry()
    assert screen.availableGeometry().contains(frame.center())
    assert not screen.availableGeometry().contains(frame)
    assert neighbor.intersects(frame)
    monkeypatch.setattr(window, "screen", lambda: adjacent)
    window.move(neighbor.topLeft())
    handle = window.windowHandle()
    handle.screenChanged.emit(handle.screen())
    settle(app)
    assert neighbor.contains(window.frameGeometry())


def test_two_monitors_do_not_disable_recovery_of_oversized_or_lost_windows(desktop, monkeypatch):
    app, _, screen, window = desktop
    screen.geometry = QRect(0, 0, 1280, 720)
    adjacent = DesktopScreen(QRect(1280, 0, 1280, 720))
    monkeypatch.setattr(QApplication, "screens", lambda: [screen, adjacent])
    window.show()
    settle(app)
    window.resize(3000, 2000)
    settle(app)
    assert screen.availableGeometry().contains(window.frameGeometry())
    window.move(6000, 6000)
    settle(app)
    assert screen.availableGeometry().contains(window.frameGeometry())


@pytest.mark.parametrize("state", [Qt.WindowMaximized, Qt.WindowFullScreen, Qt.WindowMinimized])
def test_available_area_does_not_override_managed_window_state(desktop, state):
    app, _, screen, window = desktop
    window.show()
    settle(app)
    window.setWindowState(state)
    settle(app)
    geometry = window.geometry()
    screen.change_available_area(QRect(1920, 0, 800, 600))
    settle(app)
    assert window.windowState() == state
    assert window.geometry() == geometry
    window.showNormal()
    settle(app)
    assert screen.availableGeometry().contains(window.frameGeometry())
