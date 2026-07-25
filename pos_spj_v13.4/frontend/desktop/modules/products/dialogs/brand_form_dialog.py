"""BrandFormDialog — alta/edición de una marca de producto (P1-02).

UI-only: captura código, nombre y descripción; delega el guardado en el presenter.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)


class BrandFormDialog(QDialog):
    def __init__(self, presenter, *, brand=None, parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._brand = brand or {}
        self._brand_id = self._brand.get("id")
        self.setObjectName("brandFormDialog")
        self.setWindowTitle("Editar marca" if self._brand_id else "Nueva marca")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.code = QLineEdit(str(self._brand.get("code") or ""))
        self.name = QLineEdit(str(self._brand.get("name") or ""))
        self.description = QPlainTextEdit(str(self._brand.get("description") or ""))
        self.description.setFixedHeight(72)
        form.addRow("Código *", self.code)
        form.addRow("Nombre *", self.name)
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
        layout.addWidget(buttons)

    def _on_save(self) -> None:
        self._error.setText("")
        code = self.code.text().strip().upper()
        name = self.name.text().strip()
        if not code or not name:
            self._error.setText("Código y Nombre son obligatorios.")
            return
        description = self.description.toPlainText().strip() or None
        ok, message, _bid = self._presenter.save_brand(
            brand_id=self._brand_id, code=code, name=name, description=description)
        if ok:
            self.accept()
        else:
            self._error.setText(message)
            QMessageBox.warning(self, "No se pudo guardar", message)
