"""VariantGeneratorDialog — genera variantes de un producto padre (P1-03).

UI-only: presenta los atributos LISTA con sus opciones como árbol con casillas; el
usuario marca las opciones que definen los ejes y pulsa "Generar". El producto
cartesiano y la creación de hijos lo hace el use case (vía el presenter). Muestra las
variantes ya existentes.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)


class VariantGeneratorDialog(QDialog):
    def __init__(self, presenter, *, product_id: str, product_name: str,
                 parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._product_id = product_id
        self.setObjectName("variantGeneratorDialog")
        self.setWindowTitle(f"Variantes de «{product_name}»")
        self.setMinimumSize(520, 460)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Marca las opciones de cada atributo. Se creará una variante por cada "
            "combinación (producto cartesiano)."))

        self.tree = QTreeWidget()
        self.tree.setObjectName("variantAxesTree")
        self.tree.setHeaderLabels(["Atributo / Opción", "Código"])
        self.tree.setColumnWidth(0, 320)
        layout.addWidget(self.tree, 1)

        self._existing = QLabel()
        self._existing.setObjectName("textMuted")
        layout.addWidget(self._existing)

        self._status = QLabel()
        self._status.setObjectName("textSuccess")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._error = QLabel()
        self._error.setObjectName("textDanger")
        self._error.setWordWrap(True)
        layout.addWidget(self._error)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self._btn_generate = QPushButton("Generar")
        self._btn_generate.setEnabled(
            bool(getattr(self._presenter, "can_generate_variants", False)))
        self._btn_generate.clicked.connect(self._on_generate)
        buttons.addButton(self._btn_generate, QDialogButtonBox.AcceptRole)
        buttons.button(QDialogButtonBox.Cancel).setText("Cerrar")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_axes()
        self._refresh_existing()

    def _load_axes(self) -> None:
        self.tree.clear()
        for attr in self._presenter.variant_axes_catalog():
            node = QTreeWidgetItem([attr["name"], attr["code"]])
            node.setFlags(node.flags() & ~Qt.ItemIsUserCheckable)
            for opt in attr.get("options", []):
                child = QTreeWidgetItem([opt["label"], opt["code"]])
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Unchecked)
                child.setData(0, Qt.UserRole, (attr["id"], opt["id"]))
                node.addChild(child)
            self.tree.addTopLevelItem(node)
            node.setExpanded(True)

    def _refresh_existing(self) -> None:
        count = len(self._presenter.list_variants(self._product_id))
        self._existing.setText(f"Variantes existentes: {count}")

    def _selected_axes(self) -> dict:
        axes: dict[str, list[str]] = {}
        for i in range(self.tree.topLevelItemCount()):
            node = self.tree.topLevelItem(i)
            for j in range(node.childCount()):
                child = node.child(j)
                if child.checkState(0) == Qt.Checked:
                    attribute_id, option_id = child.data(0, Qt.UserRole)
                    axes.setdefault(attribute_id, []).append(option_id)
        return axes

    def _on_generate(self) -> None:
        self._error.setText("")
        self._status.setText("")
        axes = self._selected_axes()
        if not axes:
            self._error.setText("Marca al menos una opción para generar variantes.")
            return
        ok, message = self._presenter.generate_variants(
            parent_product_id=self._product_id, axes=axes)
        if ok:
            self._refresh_existing()
            self._status.setText(message)  # no bloqueante: reporta en la propia vista
        else:
            self._error.setText(message)
