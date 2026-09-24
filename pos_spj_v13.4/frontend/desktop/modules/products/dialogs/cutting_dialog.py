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
        # §16/Fase 7: vender el producto de entrada armándolo con sus partes
        # cuando no hay existencia directa. Por esquema; por omisión, no.
        self.btn_reverse = QPushButton("Permitir armar con partes")
        self.btn_reverse.setEnabled(False)
        self.btn_reverse.setToolTip(
            "Si no hay existencia del producto entero, el mostrador lo arma con sus "
            "partes en existencia (según este despiece) al cobrar.")
        self._can_manage = can_manage
        self.btn_reverse.clicked.connect(self._toggle_reverse)
        sbar.addWidget(self.btn_reverse)
        sbar.addStretch(1)
        layout.addLayout(sbar)

        self.schemes_table = StandardTable(columns=[
            ColumnSpec("Nombre", "name"),
            ColumnSpec("Nivel", "cut_level"),
            ColumnSpec("Activo", "active"),
            ColumnSpec("Armar con partes", "reverse"),
        ])
        self.schemes_table.itemSelectionChanged.connect(self._refresh_versions)
        self.schemes_table.itemSelectionChanged.connect(self._sync_reverse_button)
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
        rows = [[s["name"], s.get("cut_level", ""), "Sí" if s["active"] else "No",
                 "Sí" if s.get("reverse_reconstruction_allowed") else "No"]
                for s in self._schemes]
        self.schemes_table.load_rows(rows, row_ids=[s["id"] for s in self._schemes])
        self._refresh_versions()

    def _selected_scheme(self) -> dict | None:
        scheme_id = self.schemes_table.selected_row_id()
        return next((s for s in self._schemes if s["id"] == scheme_id), None)

    def _sync_reverse_button(self) -> None:
        esquema = self._selected_scheme()
        self.btn_reverse.setEnabled(bool(esquema) and self._can_manage)
        self.btn_reverse.setText(
            "Dejar de armar con partes"
            if esquema and esquema.get("reverse_reconstruction_allowed")
            else "Permitir armar con partes")

    def _toggle_reverse(self) -> None:
        self._error.setText("")
        esquema = self._selected_scheme()
        if esquema is None:
            return
        ok, message = self._presenter.set_cutting_reverse_reconstruction(
            esquema["id"], not bool(esquema.get("reverse_reconstruction_allowed")))
        if not ok:
            self._error.setText(message)
            return
        seleccion = esquema["id"]
        self.refresh_schemes()
        fila = next((i for i, s in enumerate(self._schemes) if s["id"] == seleccion), None)
        if fila is not None:
            self.schemes_table.selectRow(fila)
        self._sync_reverse_button()

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
