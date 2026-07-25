"""Categorías de producto — gestión del árbol jerárquico (P1-01).

UI only: un QTreeWidget del árbol (vía ``presenter.category_tree()``) y una barra de
acciones (nueva raíz, nueva subcategoría, editar, mover, activar/desactivar). Toda
mutación pasa por el presenter → use cases canónicos. Sin SQL ni lógica de negocio.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import PageHeader
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class ProductCategoriesPage(QWidget):
    def __init__(self, presenter, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("productCategoriesPage")
        self._presenter = presenter

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(
            title="Categorías",
            subtitle="Árbol jerárquico para clasificar el catálogo de productos.",
            icon=getattr(Icons, "CATALOG", None), compact=True)
        layout.addWidget(self.header)

        toolbar = QHBoxLayout()
        self.btn_new_root = QPushButton("Nueva categoría")
        self.btn_new_child = QPushButton("Nueva subcategoría")
        self.btn_edit = QPushButton("Editar")
        self.btn_move = QPushButton("Mover")
        self.btn_toggle = QPushButton("Activar/Desactivar")
        can_manage = bool(getattr(self._presenter, "can_manage_categories", False))
        for b in (self.btn_new_root, self.btn_new_child, self.btn_edit,
                  self.btn_move, self.btn_toggle):
            b.setEnabled(can_manage)
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.btn_new_root.clicked.connect(lambda: self._open_form(parent_id=None))
        self.btn_new_child.clicked.connect(self._new_child)
        self.btn_edit.clicked.connect(self._edit_selected)
        self.btn_move.clicked.connect(self._move_selected)
        self.btn_toggle.clicked.connect(self._toggle_selected)

        self.tree = QTreeWidget()
        self.tree.setObjectName("categoryTree")
        self.tree.setHeaderLabels(["Nombre", "Código", "Estado"])
        self.tree.setColumnWidth(0, 320)
        layout.addWidget(self.tree, 1)
        self.refresh()

    # ── datos ────────────────────────────────────────────────────────────────
    def refresh(self) -> None:
        expanded = self._expanded_ids()
        self.tree.clear()
        for node in self._presenter.category_tree():
            self.tree.addTopLevelItem(self._build_item(node, expanded))

    def _build_item(self, node: dict, expanded: set) -> QTreeWidgetItem:
        estado = "Activa" if node.get("active") else "Inactiva"
        item = QTreeWidgetItem([node["name"], node["code"], estado])
        item.setData(0, Qt.UserRole, node["id"])
        if not node.get("active"):
            item.setForeground(0, Qt.gray)
        for child in node.get("children", []):
            item.addChild(self._build_item(child, expanded))
        item.setExpanded(node["id"] in expanded or not expanded)
        return item

    def _expanded_ids(self) -> set:
        ids: set = set()

        def walk(item: QTreeWidgetItem) -> None:
            if item.isExpanded():
                ids.add(item.data(0, Qt.UserRole))
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        return ids

    def _selected(self):
        item = self.tree.currentItem()
        if item is None:
            return None, None
        return item.data(0, Qt.UserRole), item.text(0)

    # ── acciones ───────────────────────────────────────────────────────────────
    def _new_child(self) -> None:
        parent_id, _name = self._selected()
        if parent_id:
            self._open_form(parent_id=parent_id)

    def _edit_selected(self) -> None:
        category_id, _name = self._selected()
        if not category_id:
            return
        self._open_form(category=self._presenter.get_category(category_id))

    def _open_form(self, *, category=None, parent_id=None) -> None:
        from frontend.desktop.modules.products.dialogs.category_form_dialog import (
            CategoryFormDialog,
        )
        dialog = CategoryFormDialog(self._presenter, category=category,
                                    default_parent_id=parent_id, parent=self)
        if dialog.exec_():
            self.refresh()

    def _move_selected(self) -> None:
        category_id, name = self._selected()
        if not category_id:
            return
        from frontend.desktop.modules.products.dialogs.category_form_dialog import (
            MoveCategoryDialog,
        )
        dialog = MoveCategoryDialog(self._presenter, category_id=category_id,
                                    category_name=name, parent=self)
        if dialog.exec_():
            self.refresh()

    def _toggle_selected(self) -> None:
        category_id, _name = self._selected()
        if not category_id:
            return
        row = self._presenter.get_category(category_id)
        if row is None:
            return
        self._presenter.set_category_active(category_id, not bool(row.get("active")))
        self.refresh()
