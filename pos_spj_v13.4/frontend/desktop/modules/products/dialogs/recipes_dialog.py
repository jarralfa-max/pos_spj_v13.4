"""RecipesDialog — gestión de recetas de un producto (recetas UI).

UI-only: lista las recetas del producto y las versiones de la seleccionada, con las
transiciones enviar→aprobar→activar y la edición de componentes de una versión
DRAFT. Toda mutación pasa por el presenter → use cases canónicos (autorización +
segregación de funciones). Sin SQL ni lógica de negocio.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from frontend.desktop.components import ColumnSpec, StandardTable

_STATUS_ES = {
    "DRAFT": "Borrador", "UNDER_REVIEW": "En revisión", "APPROVED": "Aprobada",
    "ACTIVE": "Activa", "SUPERSEDED": "Reemplazada", "INACTIVE": "Inactiva",
}


class RecipesDialog(QDialog):
    def __init__(self, presenter, *, product_id: str, product_name: str,
                 parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._product_id = product_id
        self.setObjectName("recipesDialog")
        self.setWindowTitle(f"Recetas de «{product_name}»")
        self.setMinimumSize(640, 460)
        self._recipes: list[dict] = []
        self._versions: list[dict] = []
        can_manage = bool(getattr(self._presenter, "can_manage_recipes", False))

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Recetas"))
        rec_bar = QHBoxLayout()
        self.btn_new = QPushButton("Nueva receta")
        self.btn_new.setEnabled(can_manage)
        self.btn_new.clicked.connect(self._new_recipe)
        rec_bar.addWidget(self.btn_new)
        rec_bar.addStretch(1)
        layout.addLayout(rec_bar)

        self.recipes_table = StandardTable(columns=[
            ColumnSpec("Nombre", "name"),
            ColumnSpec("Tipo", "recipe_type"),
            ColumnSpec("Activa", "active"),
        ])
        self.recipes_table.itemSelectionChanged.connect(self._on_recipe_selected)
        layout.addWidget(self.recipes_table, 1)

        layout.addWidget(QLabel("Versiones"))
        ver_bar = QHBoxLayout()
        self.btn_edit = QPushButton("Editar componentes")
        self.btn_submit = QPushButton("Enviar")
        self.btn_approve = QPushButton("Aprobar")
        self.btn_activate = QPushButton("Activar")
        for b in (self.btn_edit, self.btn_submit, self.btn_approve, self.btn_activate):
            b.setEnabled(can_manage)
            ver_bar.addWidget(b)
        ver_bar.addStretch(1)
        layout.addLayout(ver_bar)
        self.btn_edit.clicked.connect(self._edit_version)
        self.btn_submit.clicked.connect(lambda: self._transition("submit"))
        self.btn_approve.clicked.connect(lambda: self._transition("approve"))
        self.btn_activate.clicked.connect(lambda: self._transition("activate"))

        self.versions_table = StandardTable(columns=[
            ColumnSpec("Versión", "version_number"),
            ColumnSpec("Estado", "status"),
        ])
        layout.addWidget(self.versions_table, 1)

        self._error = QLabel()
        self._error.setObjectName("textDanger")
        self._error.setWordWrap(True)
        layout.addWidget(self._error)

        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.button(QDialogButtonBox.Close).setText("Cerrar")
        close.rejected.connect(self.reject)
        close.accepted.connect(self.accept)
        layout.addWidget(close)
        self.refresh_recipes()

    # ── datos ────────────────────────────────────────────────────────────────
    def refresh_recipes(self) -> None:
        self._recipes = self._presenter.list_recipes(self._product_id)
        rows = [[r["name"], r["recipe_type"], "Sí" if r["active"] else "No"]
                for r in self._recipes]
        self.recipes_table.load_rows(rows, row_ids=[r["id"] for r in self._recipes])
        self._refresh_versions()

    def _selected_recipe_id(self):
        return self.recipes_table.selected_row_id()

    def _on_recipe_selected(self) -> None:
        self._refresh_versions()

    def _refresh_versions(self) -> None:
        recipe_id = self._selected_recipe_id()
        self._versions = (self._presenter.list_recipe_versions(recipe_id)
                          if recipe_id else [])
        rows = [[f"v{v['version_number']}", _STATUS_ES.get(v["status"], v["status"])]
                for v in self._versions]
        self.versions_table.load_rows(rows, row_ids=[v["id"] for v in self._versions])

    # ── acciones ───────────────────────────────────────────────────────────────
    def _new_recipe(self) -> None:
        from frontend.desktop.modules.products.dialogs.recipe_form_dialog import (
            RecipeFormDialog,
        )
        dlg = RecipeFormDialog(self._presenter, product_id=self._product_id,
                               parent=self)
        if dlg.exec_():
            self.refresh_recipes()

    def _edit_version(self) -> None:
        version_id = self.versions_table.selected_row_id()
        if not version_id:
            return
        detail = self._presenter.recipe_version_detail(version_id)
        if detail is None:
            return
        if detail.get("status") not in ("DRAFT", "UNDER_REVIEW"):
            self._error.setText("Sólo las versiones en borrador/revisión son editables.")
            return
        from frontend.desktop.modules.products.dialogs.recipe_form_dialog import (
            RecipeFormDialog,
        )
        dlg = RecipeFormDialog(self._presenter, product_id=self._product_id,
                               version=detail, parent=self)
        if dlg.exec_():
            self._refresh_versions()

    def _transition(self, action: str) -> None:
        self._error.setText("")
        version_id = self.versions_table.selected_row_id()
        if not version_id:
            return
        fn = {"submit": self._presenter.submit_recipe_version,
              "approve": self._presenter.approve_recipe_version,
              "activate": self._presenter.activate_recipe_version}[action]
        ok, message = fn(version_id)
        if ok:
            self._refresh_versions()
        else:
            self._error.setText(message)
