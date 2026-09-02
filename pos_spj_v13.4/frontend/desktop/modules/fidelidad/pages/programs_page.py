"""ProgramsPage (LOY-25, route ``loyalty.programs``) — list of active
programs plus a quick-create form. Approve/activate happen inline from the
row selection (a program starts DRAFT→PENDING_APPROVAL on creation, per
``CreateLoyaltyProgramUseCase``'s own docstring, so the natural next steps
are Aprobar then Activar)."""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import ColumnSpec, FormField, StandardForm, StandardTable
from frontend.desktop.components.buttons import create_primary_button, create_secondary_button
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.themes.tokens import Spacing

_STATUS_LABELS = {
    "DRAFT": "Borrador", "PENDING_APPROVAL": "Pendiente de aprobación",
    "ACTIVE": "Activo", "SUSPENDED": "Suspendido", "CLOSED": "Cerrado",
    "ARCHIVED": "Archivado",
}


class ProgramsPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("fidelidadProgramsPage")
        self._presenter = presenter
        self._loaded = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._status.hide()
        layout.addWidget(self._status)

        self._table = StandardTable(
            [ColumnSpec("Código"), ColumnSpec("Nombre"), ColumnSpec("Moneda"),
             ColumnSpec("Estado", "status")], self)
        layout.addWidget(self._table, stretch=1)

        actions = QHBoxLayout()
        self._approve_btn = create_secondary_button(self, "Aprobar seleccionado")
        self._approve_btn.clicked.connect(self._approve_selected)
        self._activate_btn = create_secondary_button(self, "Activar seleccionado")
        self._activate_btn.clicked.connect(self._activate_selected)
        actions.addWidget(self._approve_btn)
        actions.addWidget(self._activate_btn)
        actions.addStretch(1)
        layout.addLayout(actions)

        layout.addWidget(QLabel("Crear programa", self))
        self._form = StandardForm(self)
        self._code_input = StandardLineEdit(self)
        self._form.add_field("code", FormField("Código", self._code_input, required=True))
        self._name_input = StandardLineEdit(self)
        self._form.add_field("name", FormField("Nombre", self._name_input, required=True))
        self._currency_input = StandardLineEdit(self)
        self._form.add_field(
            "currency_name", FormField("Nombre de la moneda", self._currency_input,
                                       required=True, helper="Ej. Estrellas, Puntos SPJ"))
        layout.addWidget(self._form)

        create_btn = create_primary_button(self, "Crear programa")
        create_btn.clicked.connect(self._create_program)
        layout.addWidget(create_btn)

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def reload(self) -> None:
        try:
            programs = self._presenter.list_programs()
            self._table.load_rows(
                [[p.code, p.name, p.currency_name,
                  _STATUS_LABELS.get(p.status.value, p.status.value)] for p in programs],
                row_ids=[p.id for p in programs])
            self._loaded = True
            self._status.hide()
        except Exception as exc:
            self._status.setProperty("state", "ERROR")
            self._status.setText(f"No fue posible cargar los programas: {exc}")
            self._status.show()

    def _selected_program_id(self) -> str | None:
        return self._table.selected_row_id()

    def _approve_selected(self) -> None:
        program_id = self._selected_program_id()
        if not program_id:
            self._show_message("Selecciona un programa primero.", error=True)
            return
        result = self._presenter.approve_program(program_id)
        self._show_message(result.message, error=not result.success)
        if result.success:
            self.reload()

    def _activate_selected(self) -> None:
        program_id = self._selected_program_id()
        if not program_id:
            self._show_message("Selecciona un programa primero.", error=True)
            return
        result = self._presenter.activate_program(program_id)
        self._show_message(result.message, error=not result.success)
        if result.success:
            self.reload()

    def _create_program(self) -> None:
        errors = {}
        if not self._code_input.text().strip():
            errors["code"] = "El código es obligatorio"
        if not self._name_input.text().strip():
            errors["name"] = "El nombre es obligatorio"
        if not self._currency_input.text().strip():
            errors["currency_name"] = "El nombre de la moneda es obligatorio"
        self._form.set_errors(errors)
        if errors:
            return
        result = self._presenter.create_program(
            code=self._code_input.text().strip(), name=self._name_input.text().strip(),
            currency_name=self._currency_input.text().strip())
        self._show_message(result.message, error=not result.success)
        if result.success:
            self._code_input.clear()
            self._name_input.clear()
            self._currency_input.clear()
            self._form.clear_errors()
            self.reload()

    def _show_message(self, message: str, *, error: bool) -> None:
        self._status.setProperty("state", "ERROR" if error else "READY")
        self._status.setText(message)
        self._status.show()
