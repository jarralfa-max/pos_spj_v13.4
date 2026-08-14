"""CASH-18 device and hardware operations UI; backend owns every mutation."""

from PyQt5.QtWidgets import QMessageBox, QTabWidget, QVBoxLayout, QWidget

from backend.domain.cash_register.exceptions import CashRegisterError
from backend.shared.ids import is_uuidv7
from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.page_header import PageHeader
from frontend.desktop.components.tables import ColumnSpec, StandardTable
from frontend.desktop.modules.cash_register.cash_register_dialogs import (
    CashDeviceActionDialog,
    CashDeviceDialog,
)
from frontend.desktop.modules.cash_register.presentation import status_label, user_facing_error


class CashDevicesPage(QWidget):
    SECTIONS = (("register", "Cajas"), ("drawer", "Cajones"), ("terminal", "Terminales"))

    def __init__(self, query_service, *, presenter, parent=None):
        super().__init__(parent)
        self._query, self._tables = query_service, {}
        self._rows_by_id = {}
        self._presenter = presenter
        root = QVBoxLayout(self)
        create = create_primary_button(self, "Nuevo dispositivo")
        activate = create_secondary_button(self, "Activar")
        block = create_secondary_button(self, "Bloquear")
        maintenance = create_secondary_button(self, "Mantenimiento")
        retire = create_secondary_button(self, "Retirar")
        diagnose = create_secondary_button(self, "Diagnosticar")
        drawer_button = create_secondary_button(self, "Abrir cajon")
        refresh = create_secondary_button(self, "Actualizar")
        caps = presenter.capabilities()
        create.setEnabled(bool(caps.hardware_manage))
        activate.setEnabled(bool(caps.hardware_manage))
        block.setEnabled(bool(caps.hardware_manage))
        maintenance.setEnabled(bool(caps.hardware_manage))
        retire.setEnabled(bool(caps.hardware_manage))
        diagnose.setEnabled(bool(caps.hardware_diagnose))
        drawer_button.setEnabled(bool(caps.drawer_open_without_sale))
        create.clicked.connect(self._create_device)
        activate.clicked.connect(lambda: self._set_status(True))
        block.clicked.connect(lambda: self._set_status(False))
        maintenance.clicked.connect(lambda: self._set_status(False, target_status="MAINTENANCE"))
        retire.clicked.connect(lambda: self._set_status(False, target_status="RETIRED"))
        diagnose.clicked.connect(self._diagnose)
        drawer_button.clicked.connect(self._request_drawer_opening)
        refresh.clicked.connect(self.refresh)
        root.addWidget(PageHeader(
            self,
            title="Cajas, cajones y terminales",
            subtitle="Administracion, diagnostico y operacion auditada del hardware de Caja.",
            actions=[refresh, drawer_button, diagnose, retire, maintenance, block, activate, create],
        ))
        self._tabs = QTabWidget(self)
        for kind, label in self.SECTIONS:
            table = StandardTable([
                ColumnSpec("Nombre"),
                ColumnSpec("Sucursal"),
                ColumnSpec("Asignacion"),
                ColumnSpec("Estado", "status"),
                ColumnSpec("Hardware", "status"),
            ], self)
            table.doubleClicked.connect(lambda _index: self._diagnose())
            self._tables[kind] = table
            self._tabs.addTab(table, label)
        root.addWidget(self._tabs)
        self.refresh()

    def _active_kind(self):
        return self.SECTIONS[self._tabs.currentIndex()][0]

    def _selected_id(self) -> str | None:
        device_id = self._tables[self._active_kind()].selected_row_id()
        if device_id and not is_uuidv7(str(device_id)):
            self._show_error(
                "El dispositivo seleccionado no tiene una identidad valida. "
                "Actualiza la pantalla o recrea el registro."
            )
            return None
            self._show_error(
                "El dispositivo seleccionado tiene una identidad inválida. "
                "Caja requiere UUIDv7 canónico; recrea el registro desde una base born-clean."
            )
            return None
        return device_id

    def refresh(self):
        self._rows_by_id = {}
        for kind, _label in self.SECTIONS:
            rows = self._query.list_devices(kind)
            for row in rows:
                self._rows_by_id[row.id] = row
            self._tables[kind].load_rows(
                [
                    [row.name, row.branch_name, row.assignment, status_label(row.status), row.hardware_status]
                    for row in rows
                ],
                row_ids=[row.id for row in rows],
            )

    def _create_device(self) -> None:
        kind = self._active_kind()
        registers = tuple(self._query.list_devices("register")) if kind in {"drawer", "terminal"} else ()
        dialog = CashDeviceDialog(
            self,
            kind=kind,
            registers=registers,
            title="Nuevo dispositivo de Caja",
        )
        if dialog.exec_() != dialog.Accepted:
            return
        data = dialog.result_value()
        self._run(
            lambda: self._presenter.create_cash_device(
                kind=kind, name=data.name, register_id=data.register_id),
            "Dispositivo creado",
        )

    def _set_status(self, activate: bool, *, target_status: str | None = None) -> None:
        device_id = self._selected_id()
        if not device_id:
            return
        title = "Bloquear dispositivo"
        placeholder = "Motivo de bloqueo"
        if target_status == "MAINTENANCE":
            title, placeholder = "Enviar a mantenimiento", "Motivo de mantenimiento"
        elif target_status == "RETIRED":
            title, placeholder = "Retirar dispositivo", "Motivo de retiro"
        reason = "" if activate else self._text_dialog(title, placeholder)
        if not activate and not reason:
            return
        self._run(
            lambda: self._presenter.set_cash_device_status(
                kind=self._active_kind(),
                device_id=device_id,
                activate=activate,
                reason=reason,
                target_status=target_status,
            ),
            "Estado actualizado",
        )

    def _diagnose(self) -> None:
        device_id = self._selected_id()
        if not device_id:
            return
        try:
            result = self._presenter.diagnose_cash_hardware(device_id=device_id)
        except (CashRegisterError, RuntimeError, ValueError) as exc:
            self._show_error(user_facing_error(exc))
            return
        self._show_result(
            f"Diagnostico: {getattr(result, 'message', '')} "
            f"({getattr(result, 'driver', 'driver')})"
        )
        self.refresh()

    def _request_drawer_opening(self) -> None:
        if self._active_kind() != "drawer":
            self._show_error("Selecciona un cajon para abrirlo.")
            return
        drawer_id = self._selected_id()
        if not drawer_id:
            return
        reason = self._text_dialog("Abrir cajon sin venta", "Motivo auditado")
        if not reason:
            return
        self._run(
            lambda: self._presenter.open_cash_drawer_hardware(
                drawer_id=drawer_id,
                reason=reason,
            ),
            "Cajon abierto y auditado",
        )

    def _run(self, command, success: str) -> None:
        try:
            result = command()
        except (CashRegisterError, RuntimeError, ValueError) as exc:
            self._show_error(user_facing_error(exc))
            return
        self._show_result(getattr(result, "message", success))
        self.refresh()

    def _text_dialog(self, title: str, placeholder: str) -> str:
        device = self._rows_by_id.get(self._selected_id() or "")
        if device is None:
            self._show_error("Selecciona un dispositivo vigente.")
            return ""
        dialog = CashDeviceActionDialog(
            self,
            title=title,
            device=device,
            placeholder=placeholder,
            ok_text="Continuar",
        )
        if dialog.exec_() != dialog.Accepted:
            return ""
        return dialog.result_value().reason

    def _show_result(self, message: str) -> None:
        QMessageBox.information(self, "Caja", message)

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Caja", user_facing_error(message))
