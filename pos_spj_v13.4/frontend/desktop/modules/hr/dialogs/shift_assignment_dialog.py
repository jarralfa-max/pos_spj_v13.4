<<<<<<< HEAD
"""Canonical HR dialog shell for shift_assignment."""

from __future__ import annotations

from PyQt5.QtWidgets import QDialog, QVBoxLayout

from frontend.desktop.themes import DesktopSpacing


class HRShiftAssignmentDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG)
=======
"""Canonical HR standard dialog shell for asignar turno."""

from __future__ import annotations

from PyQt5.QtWidgets import QDialogButtonBox

from frontend.desktop.components import StandardDialog, StandardForm


class HRShiftAssignmentDialog(StandardDialog):
    """StandardDialog shell reserved for upcoming HR use-case wiring."""

    def __init__(self, parent=None) -> None:
        self._form = StandardForm(parent)
        super().__init__(
            parent,
            title='Asignar turno',
            description='Asigna turnos a empleados con formulario y controles estándar.',
            content=self._form,
            buttons=QDialogButtonBox.Save | QDialogButtonBox.Cancel,
        )
>>>>>>> 5f7df5247ec66f7297adb53c0d2e32ee56e33c23
