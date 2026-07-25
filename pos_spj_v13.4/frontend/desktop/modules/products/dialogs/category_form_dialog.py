"""CategoryFormDialog — alta/edición de una categoría de producto (P1-01).

UI-only: captura código, nombre y orden; en alta permite elegir la categoría padre
(el nivel se deriva solo). El movimiento de ramas ya existentes se hace desde la
página con ``MoveCategoryDialog``. Delega el guardado en el presenter.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)


class CategoryFormDialog(QDialog):
    def __init__(self, presenter, *, category=None, default_parent_id=None,
                 parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._category = category or {}
        self._category_id = self._category.get("id")
        self.setObjectName("categoryFormDialog")
        self.setWindowTitle("Editar categoría" if self._category_id
                            else "Nueva categoría")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.code = QLineEdit(str(self._category.get("code") or ""))
        self.name = QLineEdit(str(self._category.get("name") or ""))
        self.sort_order = QSpinBox()
        self.sort_order.setRange(0, 9999)
        self.sort_order.setValue(int(self._category.get("sort_order") or 0))

        form.addRow("Código *", self.code)
        form.addRow("Nombre *", self.name)

        # El padre sólo se elige al crear; para mover una rama existente se usa
        # la acción "Mover" (reescribe rutas del subárbol de forma transaccional).
        self.parent = QComboBox()
        if self._category_id is None:
            self.parent.addItem("(Categoría raíz)", None)
            for opt in self._presenter.list_categories():
                self.parent.addItem(opt["label"], opt["id"])
            if default_parent_id:
                idx = self.parent.findData(default_parent_id)
                if idx >= 0:
                    self.parent.setCurrentIndex(idx)
            form.addRow("Categoría padre", self.parent)

        form.addRow("Orden", self.sort_order)
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
        parent_id = self.parent.currentData() if self._category_id is None else None
        ok, message, _cid = self._presenter.save_category(
            category_id=self._category_id, code=code, name=name,
            parent_id=parent_id, sort_order=self.sort_order.value())
        if ok:
            self.accept()
        else:
            self._error.setText(message)
            QMessageBox.warning(self, "No se pudo guardar", message)


class MoveCategoryDialog(QDialog):
    """Elige un nuevo padre para una categoría existente (o la lleva a raíz)."""

    def __init__(self, presenter, *, category_id: str, category_name: str,
                 parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._category_id = category_id
        self.setObjectName("moveCategoryDialog")
        self.setWindowTitle(f"Mover «{category_name}»")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.parent = QComboBox()
        self.parent.addItem("(Categoría raíz)", None)
        for opt in self._presenter.list_categories():
            # No se puede mover una categoría dentro de sí misma (el backend
            # también lo valida); ocultamos la propia opción por claridad.
            if opt["id"] != category_id:
                self.parent.addItem(opt["label"], opt["id"])
        form.addRow("Nuevo padre", self.parent)
        layout.addLayout(form)

        self._error = QLabel()
        self._error.setObjectName("textDanger")
        self._error.setWordWrap(True)
        layout.addWidget(self._error)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Mover")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._on_move)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_move(self) -> None:
        self._error.setText("")
        ok, message = self._presenter.move_category(
            self._category_id, self.parent.currentData())
        if ok:
            self.accept()
        else:
            self._error.setText(message)
            QMessageBox.warning(self, "No se pudo mover", message)
