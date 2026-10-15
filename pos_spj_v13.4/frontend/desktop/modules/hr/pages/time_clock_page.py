"""Checador — aparatos (lector USB de kiosco, huella, rostro, tarjeta, QR) y sus
marcaciones. Las credenciales de cada empleado se dan de alta en Empleados."""

from __future__ import annotations

from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.hr.dialogs.hr_operation_dialogs import (
    KioskDialog,
    TimeClockDeviceDialog,
)
from frontend.desktop.modules.hr.pages._page_base import HRPage


class TimeClockPage(HRPage):
    title = "Checador"
    subtitle = "Lectores de asistencia de la sucursal; cada lectura se vuelve una marcación"
    columns = [ColumnSpec("Código"), ColumnSpec("Nombre"), ColumnSpec("Tipo"),
               ColumnSpec("Conexión"), ColumnSpec("Última descarga"),
               ColumnSpec("Sin empleado", "numeric"), ColumnSpec("Estado", "status")]
    empty_message = "No hay checadores dados de alta"

    def _build_actions(self) -> None:
        self._add_action(create_primary_button(self, "Modo checador"), "time_clock_punch",
                         self._kiosk)
        self._add_action(create_secondary_button(self, "Descargar marcaciones"),
                         "time_clock_punch", self._sync)
        self._add_action(create_secondary_button(self, "Importar archivo"), "time_clock_punch",
                         self._import_file)
        self._add_action(create_secondary_button(self, "Nuevo checador"), "time_clock_manage",
                         self._register)

    def _load(self) -> None:
        self.set_table(self._presenter.devices())

    def _selected_device(self):
        device_id = self.selected_id()
        if not device_id:
            self.notify(False, "Seleccione un checador.")
        return device_id

    def _register(self) -> None:
        dialog = TimeClockDeviceDialog(self, on_submit=lambda v: self._presenter.register_device(**v))
        if dialog.exec_():
            self.notify(True, getattr(dialog, "submitted_message", "Checador registrado"))
            self.reload()

    def _kiosk(self) -> None:
        device_id = self._selected_device()
        if not device_id:
            return
        row = self._table.currentRow()
        label = self._table.item(row, 1).text() if row >= 0 and self._table.item(row, 1) else ""
        KioskDialog(self._presenter, device_id, label, self).exec_()
        self.reload()

    def _sync(self) -> None:
        device_id = self._selected_device()
        if device_id:
            self.notify(*self._presenter.sync_device(device_id))
            self.reload()

    def _import_file(self) -> None:
        from PyQt5.QtWidgets import QFileDialog
        device_id = self._selected_device()
        if not device_id:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Archivo de marcaciones del checador", "",
                                              "Marcaciones (*.dat *.txt *.csv);;Todos (*.*)")
        if path:
            self.notify(*self._presenter.import_device_file(device_id, path))
            self.reload()
