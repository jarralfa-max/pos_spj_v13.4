"""Small catalog and boolean controls sharing the global density and QSS."""
from PyQt5.QtWidgets import QCheckBox, QComboBox, QRadioButton

from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics


class _DensityControl:
    def _configure(self, name):
        self.setObjectName(name)
        self._apply_density()
        ThemeManager.instance().density_changed.connect(self._apply_density)

    def _apply_density(self, _density=None):
        self.setMinimumHeight(density_metrics().input_height)


class StandardComboBox(QComboBox, _DensityControl):
    """For small fixed option sets; entity selection uses SearchSelector."""
    def __init__(self, parent=None, *, accessible_name="Opciones"):
        super().__init__(parent)
        self._configure("standardComboBox")
        self.setAccessibleName(accessible_name)
        self.setSizeAdjustPolicy(QComboBox.AdjustToContents)


class StandardCheckBox(QCheckBox, _DensityControl):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._configure("standardCheckBox")
        self.setAccessibleName(text)


class StandardRadioButton(QRadioButton, _DensityControl):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._configure("standardRadioButton")
        self.setAccessibleName(text)
