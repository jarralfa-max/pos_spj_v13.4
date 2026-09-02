"""Usuarios y Roles page — first real caller of the dormant "FASE 6"
canonical use-case layer (`SaveUserUseCase`/`SetUserActiveUseCase`,
`backend/application/use_cases/`). The legacy UI (`modulos/
configuracion.py`'s "Usuarios y Roles" tab) already delegated to the
same application-service layer (`UserManagementService`/
`RoleManagementService`/`UserSecurityService`/`PermissionQueryService`)
this page uses — this is a Design-System port, not a new domain build.

The base inherited table (Usuarios) is the main interactive table, same
"reuse the inherited table" shape `FeatureFlagsPage`/`AparienciaPage`/
`OfflinePage` established. Two independent sibling cards: "Roles"
(create/edit name+description only — NOT the permission matrix, a
separate, bigger, deferred project) and "Auditoría" (read-only, últimas
200, no buttons at all — same deliberately-read-only shape `OfflinePage`
's Cache card established).
"""
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QWidget

from frontend.desktop.components import (
    ColumnSpec, SectionCard, StandardTable, ViewState, create_danger_button, create_primary_button,
    create_secondary_button, create_state_widget, create_warning_button,
)
from frontend.desktop.modules.configuracion.dialogs import (
    RoleCreateDialog,
    RoleEditDialog,
    UserCreateDialog,
    UserEditDialog,
)
from frontend.desktop.themes.tokens import Spacing

from .base_page import ConfiguracionWorkspacePage

_ROLE_COLUMNS = [ColumnSpec("Nombre"), ColumnSpec("Descripción"), ColumnSpec("# Usuarios", "numeric")]
_AUDIT_COLUMNS = [
    ColumnSpec("Fecha"), ColumnSpec("Usuario"), ColumnSpec("Módulo"), ColumnSpec("Acción"),
    ColumnSpec("Detalle"),
]


def _button_row(parent, *buttons):
    row = QWidget(parent)
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(Spacing.SM)
    for button in buttons:
        layout.addWidget(button)
    layout.addStretch(1)
    return row


class UsuariosRolesPage(ConfiguracionWorkspacePage):
    page_id = "config_usuarios_roles"
    title = "Usuarios y Roles"
    subtitle = "Usuarios, roles y auditoría del sistema."

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(presenter, parent)
        self._users_by_id: dict = {}
        self._roles_by_id: dict = {}

        self.new_user_button = create_primary_button(self, "Nuevo usuario")
        self.edit_user_button = create_secondary_button(self, "Editar")
        self.activate_user_button = create_secondary_button(self, "Activar")
        self.deactivate_user_button = create_warning_button(self, "Desactivar")
        self.unlock_user_button = create_danger_button(self, "Desbloquear")
        user_actions = _button_row(
            self, self.new_user_button, self.edit_user_button, self.activate_user_button,
            self.deactivate_user_button, self.unlock_user_button,
        )
        self.layout().insertWidget(1, user_actions)

        self.new_user_button.clicked.connect(self._on_new_user)
        self.edit_user_button.clicked.connect(self._on_edit_user)
        self.activate_user_button.clicked.connect(lambda: self._on_change_user_status(True))
        self.deactivate_user_button.clicked.connect(lambda: self._on_change_user_status(False))
        self.unlock_user_button.clicked.connect(self._on_unlock_user)

        self._build_roles_card()
        self._build_audit_card()

    def reload(self, search: str = "") -> None:
        super().reload(search)
        self._users_by_id = {u.id: u for u in self._presenter.list_users()}
        self._reload_roles()
        self._reload_audit()

    def _selected_user_id(self) -> str | None:
        row_id = self.table.selected_row_id() if self.table is not None else None
        if not row_id:
            QMessageBox.warning(self, "Usuarios y Roles", "Selecciona un usuario primero.")
        return row_id

    def _selector_options(self):
        roles = self._presenter.list_role_names()
        branches = self._presenter.list_branches_for_user_selector()
        employees = self._presenter.list_employees_for_user_selector()
        return roles, branches, employees

    def _on_new_user(self) -> None:
        roles, branches, employees = self._selector_options()
        dlg = UserCreateDialog(self, role_options=roles, branch_options=branches, employee_options=employees)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["username"] or not values["password"]:
            QMessageBox.warning(self, "Usuarios y Roles", "Usuario y contraseña son obligatorios.")
            return
        if not values["branch_id"]:
            QMessageBox.warning(self, "Usuarios y Roles", "Selecciona la sucursal del usuario.")
            return
        ok, message = self._presenter.create_user(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Usuarios y Roles", message)
        if ok:
            self.reload(self.search.text())

    def _on_edit_user(self) -> None:
        user_id = self._selected_user_id()
        if not user_id:
            return
        form_data = self._presenter.get_user_form_data(user_id)
        if form_data is None:
            QMessageBox.warning(self, "Usuarios y Roles", "El usuario ya no existe.")
            return
        roles, branches, employees = self._selector_options()
        dlg = UserEditDialog(
            self, username=form_data.username, full_name=form_data.name, email=form_data.email,
            role=form_data.role, branch_id=form_data.branch_id, employee_id=str(form_data.employee_id or ""),
            active=form_data.active, role_options=roles, branch_options=branches, employee_options=employees,
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["branch_id"]:
            QMessageBox.warning(self, "Usuarios y Roles", "Selecciona la sucursal del usuario.")
            return
        ok, message = self._presenter.update_user(user_id=user_id, username=form_data.username, **values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Usuarios y Roles", message)
        if ok:
            self.reload(self.search.text())

    def _on_change_user_status(self, active: bool) -> None:
        user_id = self._selected_user_id()
        if not user_id:
            return
        ok, message = self._presenter.set_user_active(user_id=user_id, active=active)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Usuarios y Roles", message)
        if ok:
            self.reload(self.search.text())

    def _on_unlock_user(self) -> None:
        user_id = self._selected_user_id()
        if not user_id:
            return
        user = self._users_by_id.get(user_id)
        if user is not None and not user.locked:
            QMessageBox.information(self, "Usuarios y Roles", "Este usuario no está bloqueado.")
            return
        confirm = QMessageBox.question(
            self, "Desbloquear usuario",
            f"¿Desbloquear a «{user.username if user else user_id}»? Se reiniciarán los intentos fallidos "
            "y el bloqueo temporal. La acción quedará auditada.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        ok, message = self._presenter.unlock_user(user_id)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Usuarios y Roles", message)
        if ok:
            self.reload(self.search.text())

    # ── Roles ────────────────────────────────────────────────────────────

    def _build_roles_card(self) -> None:
        self.roles_card = SectionCard(self, title="Roles")
        self.roles_table = StandardTable(_ROLE_COLUMNS, self.roles_card)
        self.roles_table.setAccessibleName("Roles del sistema")
        self.roles_card.add(self.roles_table)
        self.roles_empty = None

        self.new_role_button = create_primary_button(self.roles_card, "Nuevo rol")
        self.edit_role_button = create_secondary_button(self.roles_card, "Editar")
        self.roles_card.add(_button_row(self.roles_card, self.new_role_button, self.edit_role_button))
        self.layout().addWidget(self.roles_card)

        self.new_role_button.clicked.connect(self._on_new_role)
        self.edit_role_button.clicked.connect(self._on_edit_role)
        self._reload_roles()

    def _reload_roles(self) -> None:
        roles = self._presenter.list_roles()
        self._roles_by_id = {r.id: r for r in roles}
        rows = [[r.name, r.description, str(r.user_count)] for r in roles]
        self.roles_table.load_rows(rows, row_ids=[r.id for r in roles])
        if self.roles_empty is not None:
            self.roles_empty.setParent(None)
            self.roles_empty = None
        if not rows:
            self.roles_empty = create_state_widget(
                ViewState.EMPTY, self.roles_card, message="No hay roles todavía.")
            self.roles_card.add(self.roles_empty)
        self.roles_table.setVisible(bool(rows))

    def _selected_role_id(self) -> str | None:
        row_id = self.roles_table.selected_row_id()
        if not row_id:
            QMessageBox.warning(self, "Usuarios y Roles", "Selecciona un rol primero.")
        return row_id

    def _on_new_role(self) -> None:
        dlg = RoleCreateDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["name"]:
            QMessageBox.warning(self, "Usuarios y Roles", "El nombre del rol es obligatorio.")
            return
        ok, message = self._presenter.save_role(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Usuarios y Roles", message)
        if ok:
            self._reload_roles()

    def _on_edit_role(self) -> None:
        role_id = self._selected_role_id()
        if not role_id:
            return
        role = self._roles_by_id.get(role_id)
        if role is None:
            QMessageBox.warning(self, "Usuarios y Roles", "El rol ya no existe.")
            return
        dlg = RoleEditDialog(self, name=role.name, description=role.description)
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message = self._presenter.save_role(role_id=role_id, name=role.name, **dlg.values())
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Usuarios y Roles", message)
        if ok:
            self._reload_roles()

    # ── Auditoría (solo lectura, sin botones de acción) ─────────────────────

    def _build_audit_card(self) -> None:
        self.audit_card = SectionCard(self, title="Auditoría")
        self.audit_table = StandardTable(_AUDIT_COLUMNS, self.audit_card)
        self.audit_table.setAccessibleName("Últimas acciones registradas en el sistema")
        self.audit_card.add(self.audit_table)
        self.audit_empty = None
        self.layout().addWidget(self.audit_card)
        self._reload_audit()

    def _reload_audit(self) -> None:
        rows_data = self._presenter.audit_log_rows()
        rows = [[r.fecha, r.usuario, r.modulo, r.accion, r.detalle] for r in rows_data]
        self.audit_table.load_rows(rows, row_ids=[str(i) for i in range(len(rows))])
        if self.audit_empty is not None:
            self.audit_empty.setParent(None)
            self.audit_empty = None
        if not rows:
            self.audit_empty = create_state_widget(
                ViewState.EMPTY, self.audit_card, message="No hay acciones registradas todavía.")
            self.audit_card.add(self.audit_empty)
        self.audit_table.setVisible(bool(rows))


__all__ = ["UsuariosRolesPage"]
