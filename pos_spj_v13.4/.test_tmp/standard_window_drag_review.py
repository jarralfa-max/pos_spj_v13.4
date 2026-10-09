"""Reproduce incremental cross-monitor moves without business services."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt5 import sip
from PyQt5.QtCore import QObject, QRect, pyqtSignal
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from frontend.desktop.components.standard_window import StandardWindow


class Screen(QObject):
    availableGeometryChanged = pyqtSignal(QRect)

    def __init__(self, rect):
        super().__init__()
        self.rect = rect

    def availableGeometry(self):
        return QRect(self.rect)


app = QApplication([])
left = Screen(QRect(0, 0, 1280, 900))
right = Screen(QRect(1280, 0, 1280, 900))
QApplication.primaryScreen = staticmethod(lambda: left)
QApplication.screens = staticmethod(lambda: [left, right])
StandardWindow.screen = lambda self: (right if self.frameGeometry().center().x() >= 1280 else left)
window = StandardWindow()
window.resize(800, 550)
window.move(100, 100)
window.show()
QTest.qWait(50)
positions = []
for step in range(120):
    # Like a drag, each event advances from the actual settled position.
    before = window.frameGeometry().x()
    window.move(before + 10, 100)
    current = window.screen()
    if current is not window._desktop_screen:
        handle = window.windowHandle()
        handle.screenChanged.emit(handle.screen())
    QTest.qWait(40)
    positions.append(window.frameGeometry().x())

result = {
    "attempts": len(positions),
    "max_frame_x": max(positions),
    "final_frame": window.frameGeometry().getRect(),
    "final_screen": "right" if window.screen() is right else "left",
    "tail_positions": positions[-10:],
    "crossed_monitor": window.screen() is right,
}
print(json.dumps(result, indent=2), flush=True)
sip.delete(window)
