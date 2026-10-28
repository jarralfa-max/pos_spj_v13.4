"""BrandFormDialog — alta/edición de una marca de producto (P1-02).

UI-only: captura nombre, código (automático desde el nombre, reescribible) y
descripción; delega el guardado en el presenter.
"""

from __future__ import annotations

from frontend.desktop.components.dialogs import MessageDialog, StandardDialog
from frontend.desktop.modules.products.dialogs.auto_code import (
    AutoCodeBinder,
    catalog_suggester,
)

from PyQt5.QtWidgets import (
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
)


class BrandFormDialog(StandardDialog):
    def __init__(self, presenter, *, brand=None, parent=None) -> None:
        super().__init__(parent, width=420)
        self._presenter = presenter
        self._brand = brand or {}
        self._brand_id = self._brand.get("id")
        self.setObjectName("brandFormDialog")
        self.setWindowTitle("Editar marca" if self._brand_id else "Nueva marca")
        self.setMinimumWidth(420)

        layout = self.content_layout()
        form = QFormLayout()
        self.code = QLineEdit(str(self._brand.get("code") or ""))
        self.name = QLineEdit(str(self._brand.get("name") or ""))
        self.description = QPlainTextEdit(str(self._brand.get("description") or ""))
        self.description.setFixedHeight(72)
        form.addRow("Nombre *", self.name)
        form.addRow("Código" if self._brand_id is None else "Código *", self.code)
        # PROD-23: en el alta el código se genera del nombre (reescribible).
        self._auto = (AutoCodeBinder(self.name, self.code, catalog_suggester(
            self._presenter, "BRAND"))
            if self._brand_id is None else None)
        form.addRow("Descripción", self.description)
        layout.addLayout(form)

        self._error = QLabel()
        self._error.setObjectName("textDanger")
        self._error.setWordWrap(True)
        layout.addWidget(self._error)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        self.add_footer_widget(buttons)

    def _on_save(self) -> None:
        self._error.setText("")
        code = (self._auto.code_for_save() if self._auto is not None
                else self.code.text().strip().upper())
        name = self.name.text().strip()
        if not name or (self._auto is None and not code):
            self._error.setText("Nombre es obligatorio." if self._auto is not None
                                else "Código y Nombre son obligatorios.")
            return
        description = self.description.toPlainText().strip() or None
        ok, message, _bid = self._presenter.save_brand(
            brand_id=self._brand_id, code=code, name=name, description=description)
        if ok:
            self.accept()
        else:
            self._error.setText(message)
            MessageDialog.warning(self, "No se pudo guardar", message)
