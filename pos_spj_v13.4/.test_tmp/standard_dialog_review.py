"""Independent, DB-free StandardDialog contract probes."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt5 import sip
from PyQt5.QtCore import QObject, QRect, QSettings, Qt, pyqtSignal
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QDialogButtonBox, QLabel, QWidget

from frontend.desktop.components.dialogs import StandardDialog, DestructiveConfirmationDialog
from frontend.desktop.themes.theme_manager import ThemeManager


class Screen(QObject):
    availableGeometryChanged = pyqtSignal(QRect)

    def __init__(self, rect):
        super().__init__()
        self.rect = rect

    def availableGeometry(self):
        return QRect(self.rect)


app = QApplication([])
settings = QSettings(str(Path(__file__).with_suffix('.ini')), QSettings.IniFormat)
ThemeManager._instance = ThemeManager(settings)
left = Screen(QRect(0, 0, 1280, 720))
right = Screen(QRect(1280, 0, 1280, 720))
QApplication.primaryScreen = staticmethod(lambda: left)
QApplication.screens = staticmethod(lambda: [left, right])


def settle():
    for _ in range(5):
        app.processEvents()
    QTest.qWait(80)


results = {}
parent = QWidget()
parent.screen = lambda: left
dialog = StandardDialog(parent, title='Captura de prueba', width=600)
current = [left]
dialog.screen = lambda: current[0]
dialog.content_layout().addWidget(QLabel('Dato editable'))
dialog.add_button_box()
dialog.show()
settle()

dialog.move(5000, 5000)
settle()
results['move_outside'] = {
    'frame': dialog.frameGeometry().getRect(),
    'inside_screen': left.availableGeometry().contains(dialog.frameGeometry()),
}

dialog.move(1400, 100)
current[0] = right
# Invoke the screen-change slot with its new screen payload, without real monitors.
dialog._screen_changed(right)
settle()
results['parent_monitor'] = {
    'frame': dialog.frameGeometry().getRect(),
    'followed_own_screen': right.availableGeometry().contains(dialog.frameGeometry()),
    'returned_to_parent_screen': left.availableGeometry().contains(dialog.frameGeometry()),
}

dialog.resize(850, 500)
settle()
before = dialog.size().width(), dialog.size().height()
dialog.hide()
dialog.show()
settle()
results['reopen'] = {'before_size': before, 'after_size': (dialog.width(), dialog.height())}
sip.delete(dialog)
sip.delete(parent)

for key, key_code in [('escape', Qt.Key_Escape), ('return', Qt.Key_Return)]:
    confirmation = DestructiveConfirmationDialog(title='Eliminar', message='Confirmar eliminación')
    confirmation.screen = lambda: left
    confirmation.show()
    settle()
    box = confirmation.findChild(QDialogButtonBox)
    QTest.keyClick(confirmation, key_code)
    settle()
    results[key] = {'visible': confirmation.isVisible(), 'result': confirmation.result()}
    sip.delete(confirmation)

print(json.dumps(results, indent=2), flush=True)
