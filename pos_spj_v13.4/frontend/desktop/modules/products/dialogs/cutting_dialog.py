"""CuttingSchemesDialog — gestión de esquemas de despiece de un producto.

UI-only: lista los esquemas del producto y las versiones del seleccionado, con
enviar→aprobar→activar y edición de outputs de una versión DRAFT. Toda mutación pasa
por el presenter → use cases (autorización PRODUCTS_CUTTING_SCHEME_MANAGE).
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


class CuttingSchemesDialog(QDialog):
    def __init__(self, presenter, *, product_id: str, product_name: str,
                 species_id: str = "", parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._product_id = product_id
        self._species_id = species_id
        self.setObjectName("cuttingSchemesDialog")
        self.setWindowTitle(f"Despiece de «{product_name}»")
        self.setMinimumSize(660, 460)
        can_manage = bool(getattr(self._presenter, "can_manage_cutting", False))

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Esquemas de despiece"))
        sbar = QHBoxLayout()
        self.btn_new = QPushButton("Nuevo esquema")
        self.btn_new.setEnabled(can_manage)
        self.btn_new.clicked.connect(self._new_scheme)
        sbar.addWidget(self.btn_new)
        sbar.addStretch(1)
        layout.addLayout(sbar)

        self.schemes_table = StandardTable(columns=[
            ColumnSpec("Nombre", "name"),
            ColumnSpec("Nivel", "cut_level"),
            ColumnSpec("Activo", "active"),
        ])
        self.schemes_table.itemSelectionChanged.connect(self._refresh_versions)
        layout.addWidget(self.schemes_table, 1)

        layout.addWidget(QLabel("Versiones"))
        vbar = QHBoxLayout()
        self.btn_edit = QPushButton("Editar outputs")
        self.btn_submit = QPushButton("Enviar")
        self.btn_approve = QPushButton("Aprobar")
        self.btn_activate = QPushButton("Activar")
        for b in (self.btn_edit, self.btn_submit, self.btn_approve, self.btn_activate):
            b.setEnabled(can_manage)
            vbar.addWidget(b)
        vbar.addStretch(1)
        layout.addLayout(vbar)
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
        self.refresh_schemes()

    def refresh_schemes(self) -> None:
        self._schemes = self._presenter.list_cutting_schemes(self._product_id)
        rows = [[s["name"], s.get("cut_level", ""), "Sí" if s["active"] else "No"]
                for s in self._schemes]
        self.schemes_table.load_rows(rows, row_ids=[s["id"] for s in self._schemes])
        self._refresh_versions()

    def _refresh_versions(self) -> None:
        scheme_id = self.schemes_table.selected_row_id()
        versions = (self._presenter.list_cutting_versions(scheme_id)
                    if scheme_id else [])
        rows = [[f"v{v['version_number']}", _STATUS_ES.get(v["status"], v["status"])]
                for v in versions]
        self.versions_table.load_rows(rows, row_ids=[v["id"] for v in versions])

    def _new_scheme(self) -> None:
        from frontend.desktop.modules.products.dialogs.cutting_form_dialog import (
            CuttingSchemeFormDialog,
        )
        dlg = CuttingSchemeFormDialog(self._presenter,
                                      input_product_id=self._product_id,
                                      species_id=self._species_id, parent=self)
        if dlg.exec_():
            self.refresh_schemes()

    def _edit_version(self) -> None:
        version_id = self.versions_table.selected_row_id()
        if not version_id:
            return
        detail = self._presenter.cutting_version_detail(version_id)
        if detail is None:
            return
        if detail.get("status") not in ("DRAFT", "UNDER_REVIEW"):
            self._error.setText("Sólo las versiones en borrador/revisión son editables.")
            return
        from frontend.desktop.modules.products.dialogs.cutting_form_dialog import (
            CuttingSchemeFormDialog,
        )
        dlg = CuttingSchemeFormDialog(self._presenter,
                                      input_product_id=self._product_id,
                                      version=detail, parent=self)
        if dlg.exec_():
            self._refresh_versions()

    def _transition(self, action: str) -> None:
        self._error.setText("")
        version_id = self.versions_table.selected_row_id()
        if not version_id:
            return
        fn = {"submit": self._presenter.submit_cutting_version,
              "approve": self._presenter.approve_cutting_version,
              "activate": self._presenter.activate_cutting_version}[action]
        ok, message = fn(version_id)
        if ok:
            self._refresh_versions()
        else:
            self._error.setText(message)
