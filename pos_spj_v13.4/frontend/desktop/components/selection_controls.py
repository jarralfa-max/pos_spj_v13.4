"""Small catalog and boolean controls sharing the global density and QSS."""
from PyQt5.QtWidgets import QCheckBox, QComboBox, QRadioButton, QStyledItemDelegate

from frontend.desktop.themes.theme_manager import ThemeManager
from frontend.desktop.themes.tokens import density_metrics


class _DensityControl:
    def _configure(self, name):
        self.setObjectName(name)
        self._apply_density()
        ThemeManager.instance().density_changed.connect(self._apply_density)

    def _apply_density(self, _density=None):
        self.setMinimumHeight(density_metrics().input_height)


class _DensityOptionDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(max(size.height(), density_metrics().input_height))
        return size


class StandardComboBox(QComboBox, _DensityControl):
    """For small fixed option sets; entity selection uses SearchSelector."""
    def __init__(self, parent=None, *, accessible_name="Opciones"):
        super().__init__(parent)
        self._configure("standardComboBox")
        self.setAccessibleName(accessible_name)
        self.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.setItemDelegate(_DensityOptionDelegate(self))

    def _apply_density(self, _density=None):
        super()._apply_density(_density)
        self.view().doItemsLayout()


class StandardCheckBox(QCheckBox, _DensityControl):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._configure("standardCheckBox")
        self.setAccessibleName(text)

    def hitButton(self, position):
        # Qt's native hit area only covers the indicator and text baseline.
        return self.rect().contains(position)


class StandardRadioButton(QRadioButton, _DensityControl):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._configure("standardRadioButton")
        self.setAccessibleName(text)
