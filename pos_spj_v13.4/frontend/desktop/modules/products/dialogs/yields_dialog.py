"""YieldProfilesDialog — gestión de rendimientos de un producto de entrada.

UI-only: lista los perfiles de rendimiento del producto y las versiones del
seleccionado, con enviar→aprobar→activar y edición de outputs de una versión DRAFT.
Toda mutación pasa por el presenter → use cases (autorización + segregación).
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


class YieldProfilesDialog(QDialog):
    def __init__(self, presenter, *, product_id: str, product_name: str,
                 parent=None) -> None:
        super().__init__(parent)
        self._presenter = presenter
        self._product_id = product_id
        self.setObjectName("yieldProfilesDialog")
        self.setWindowTitle(f"Rendimientos de «{product_name}»")
        self.setMinimumSize(640, 460)
        can_manage = bool(getattr(self._presenter, "can_manage_yields", False))

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Perfiles de rendimiento"))
        pbar = QHBoxLayout()
        self.btn_new = QPushButton("Nuevo perfil")
        self.btn_new.setEnabled(can_manage)
        self.btn_new.clicked.connect(self._new_profile)
        pbar.addWidget(self.btn_new)
        pbar.addStretch(1)
        layout.addLayout(pbar)

        self.profiles_table = StandardTable(columns=[
            ColumnSpec("Nombre", "name"),
            ColumnSpec("Activo", "active"),
        ])
        self.profiles_table.itemSelectionChanged.connect(self._refresh_versions)
        layout.addWidget(self.profiles_table, 1)

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
            ColumnSpec("Tolerancia %", "tolerance_pct"),
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
        self.refresh_profiles()

    def refresh_profiles(self) -> None:
        self._profiles = self._presenter.list_yield_profiles(self._product_id)
        rows = [[p["name"], "Sí" if p["active"] else "No"] for p in self._profiles]
        self.profiles_table.load_rows(rows, row_ids=[p["id"] for p in self._profiles])
        self._refresh_versions()

    def _refresh_versions(self) -> None:
        profile_id = self.profiles_table.selected_row_id()
        versions = (self._presenter.list_yield_versions(profile_id)
                    if profile_id else [])
        rows = [[f"v{v['version_number']}", _STATUS_ES.get(v["status"], v["status"]),
                 str(v.get("tolerance_pct", ""))] for v in versions]
        self.versions_table.load_rows(rows, row_ids=[v["id"] for v in versions])

    def _new_profile(self) -> None:
        from frontend.desktop.modules.products.dialogs.yield_form_dialog import (
            YieldProfileFormDialog,
        )
        dlg = YieldProfileFormDialog(self._presenter,
                                     input_product_id=self._product_id, parent=self)
        if dlg.exec_():
            self.refresh_profiles()

    def _edit_version(self) -> None:
        version_id = self.versions_table.selected_row_id()
        if not version_id:
            return
        detail = self._presenter.yield_version_detail(version_id)
        if detail is None:
            return
        if detail.get("status") not in ("DRAFT", "UNDER_REVIEW"):
            self._error.setText("Sólo las versiones en borrador/revisión son editables.")
            return
        from frontend.desktop.modules.products.dialogs.yield_form_dialog import (
            YieldProfileFormDialog,
        )
        dlg = YieldProfileFormDialog(self._presenter,
                                     input_product_id=self._product_id,
                                     version=detail, parent=self)
        if dlg.exec_():
            self._refresh_versions()

    def _transition(self, action: str) -> None:
        self._error.setText("")
        version_id = self.versions_table.selected_row_id()
        if not version_id:
            return
        fn = {"submit": self._presenter.submit_yield_version,
              "approve": self._presenter.approve_yield_version,
              "activate": self._presenter.activate_yield_version}[action]
        ok, message = fn(version_id)
        if ok:
            self._refresh_versions()
        else:
            self._error.setText(message)
