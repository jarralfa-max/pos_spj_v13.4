"""Roles por ámbito de un usuario (auditoría enterprise, Fase 2).

`RoleAssignmentsDialog` lista los roles ADICIONALES (vigentes y revocados) y
permite otorgar o revocar; `GrantRoleDialog` captura uno. Sólo presentación: las
reglas (ámbito válido, escalamiento, duplicados) las aplica la capa de aplicación.
"""

from __future__ import annotations

from datetime import date

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget

from frontend.desktop.components import (
    ColumnSpec,
    FormDialog,
    SearchableComboBox,
    StandardDialog,
    StandardLineEdit,
    StandardTable,
    apply_tooltip,
    create_primary_button,
    create_warning_button,
)
from frontend.desktop.components.dialogs import MessageDialog
from frontend.desktop.themes.tokens import Spacing

_ESTADOS = {"ACTIVE": "Vigente", "REVOKED": "Revocada"}


def _fecha(texto: str) -> date | None:
    texto = str(texto or "").strip()
    return date.fromisoformat(texto) if texto else None


class GrantRoleDialog(FormDialog):
    def __init__(self, parent=None, *, role_options=(), scope_options=()) -> None:
        super().__init__(parent, title="Otorgar rol con ámbito")
        self.role = SearchableComboBox(self, placeholder="Rol…")
        self.role.set_options(list(role_options))
        self.role.setAccessibleName("Rol")
        self.form.addRow("Rol:", self.role)
        self._scopes = {f"{t}:{i}": (t, i) for t, i, _ in scope_options}
        self.scope = SearchableComboBox(self, placeholder="Dónde vale…")
        self.scope.set_options([(f"{t}:{i}", etiqueta) for t, i, etiqueta in scope_options])
        self.scope.setAccessibleName("Ámbito")
        apply_tooltip(self.scope, "Una región o planta incluye todo lo que depende de ella.")
        self.form.addRow("Ámbito:", self.scope)
        self.valid_from = StandardLineEdit(self)
        self.valid_from.setPlaceholderText("AAAA-MM-DD (opcional)")
        self.valid_from.setAccessibleName("Vigente desde")
        self.form.addRow("Desde:", self.valid_from)
        self.valid_until = StandardLineEdit(self)
        self.valid_until.setPlaceholderText("AAAA-MM-DD (opcional)")
        self.valid_until.setAccessibleName("Vigente hasta")
        self.form.addRow("Hasta:", self.valid_until)
        self.reason = StandardLineEdit(self)
        self.reason.setAccessibleName("Motivo")
        self.form.addRow("Motivo:", self.reason)
        self.add_button_box(ok_text="Otorgar", on_accept=self._validar)

    def _validar(self) -> None:
        try:
            self.values()
        except ValueError:
            MessageDialog.warning(self, "Otorgar rol", "Las fechas van como AAAA-MM-DD.")
            return
        if not self.role.current_id() or not self.scope.current_id() or \
                not self.reason.text().strip():
            MessageDialog.warning(self, "Otorgar rol", "Rol, ámbito y motivo son obligatorios.")
            return
        self.accept()

    def values(self) -> dict:
        tipo, ambito = self._scopes.get(self.scope.current_id() or "", ("", ""))
        return {"role_id": self.role.current_id() or "", "scope_type": tipo,
                "scope_id": ambito, "reason": self.reason.text().strip(),
                "valid_from": _fecha(self.valid_from.text()),
                "valid_until": _fecha(self.valid_until.text())}


class RoleAssignmentsDialog(StandardDialog):
    def __init__(self, parent=None, *, presenter, user_id: str, user_name: str = "",
                 can_change: bool = False) -> None:
        super().__init__(parent, title=f"Roles por ámbito — {user_name}".rstrip(" —"))
        self._presenter = presenter
        self._user_id = user_id
        nota = QLabel("Además de su rol principal (en su sucursal), estos roles valen donde "
                      "indica el ámbito. Una región incluye sus sucursales.", self)
        nota.setWordWrap(True)
        self.content_layout().addWidget(nota)
        self.table = StandardTable([
            ColumnSpec("Rol", preferred_width=150), ColumnSpec("Ámbito", preferred_width=200),
            ColumnSpec("Vigencia", preferred_width=170), ColumnSpec("Estado", "status"),
            ColumnSpec("Motivo", preferred_width=200, stretch=True),
        ], self, settings_key="configuracion/role_assignments")
        self.table.setAccessibleName("Roles por ámbito del usuario")
        self.content_layout().addWidget(self.table)
        fila = QWidget(self)
        botones = QHBoxLayout(fila)
        botones.setContentsMargins(0, 0, 0, 0)
        botones.setSpacing(Spacing.SM)
        self.grant_button = create_primary_button(fila, "Otorgar rol…")
        self.revoke_button = create_warning_button(fila, "Revocar")
        for boton in (self.grant_button, self.revoke_button):
            boton.setVisible(can_change)
            botones.addWidget(boton)
        botones.addStretch(1)
        self.content_layout().addWidget(fila)
        self.grant_button.clicked.connect(self._on_grant)
        self.revoke_button.clicked.connect(self._on_revoke)
        self.add_button_box(ok_text="Cerrar")
        self.reload()

    def reload(self) -> None:
        filas = self._presenter.role_assignments(self._user_id)
        self._filas = {f["id"]: f for f in filas}
        self.table.load_rows([[
            f["role_name"], f["scope_name"],
            f"{f.get('valid_from') or '…'} → {f.get('valid_until') or '…'}",
            _ESTADOS.get(f["status"], f["status"]),
            f.get("revoke_reason") or f.get("reason") or "",
        ] for f in filas], row_ids=[f["id"] for f in filas])

    def _on_grant(self) -> None:
        dlg = GrantRoleDialog(self, role_options=self._presenter.assignment_role_options(),
                              scope_options=self._presenter.assignment_scope_options())
        if dlg.exec_() != FormDialog.Accepted:
            return
        ok, mensaje = self._presenter.assign_role(user_id=self._user_id, **dlg.values())
        (MessageDialog.information if ok else MessageDialog.warning)(self, "Roles por ámbito",
                                                                mensaje)
        if ok:
            self.reload()

    def _on_revoke(self) -> None:
        aid = self.table.selected_row_id()
        fila = self._filas.get(aid) if aid else None
        if fila is None or fila["status"] != "ACTIVE":
            MessageDialog.warning(self, "Roles por ámbito", "Selecciona una asignación vigente.")
            return
        motivo, aceptado = FormDialog.get_text(self, "Revocar rol", "Motivo:")
        if not aceptado:
            return
        ok, mensaje = self._presenter.revoke_role_assignment(aid, motivo)
        (MessageDialog.information if ok else MessageDialog.warning)(self, "Roles por ámbito",
                                                                mensaje)
        if ok:
            self.reload()


__all__ = ["GrantRoleDialog", "RoleAssignmentsDialog"]
