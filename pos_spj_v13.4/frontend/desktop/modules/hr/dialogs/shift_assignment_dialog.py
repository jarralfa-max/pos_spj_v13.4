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
