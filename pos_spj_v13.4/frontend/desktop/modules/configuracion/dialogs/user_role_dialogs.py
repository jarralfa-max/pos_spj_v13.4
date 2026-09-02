"""Dialogs for the "Usuarios y Roles" section. Built entirely on
`FormDialog`, same convention as every other dialog in this package.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QCheckBox, QLineEdit

from frontend.desktop.components import FormDialog, SearchableComboBox, StandardLineEdit, apply_tooltip


class UserCreateDialog(FormDialog):
    def __init__(self, parent=None, *, role_options=(), branch_options=(), employee_options=()) -> None:
        super().__init__(parent, title="Nuevo usuario")
        self.username = StandardLineEdit(self)
        self.username.setAccessibleName("Usuario")
        self.form.addRow("Usuario*:", self.username)

        self.full_name = StandardLineEdit(self)
        self.full_name.setAccessibleName("Nombre")
        self.form.addRow("Nombre:", self.full_name)

        self.email = StandardLineEdit(self)
        self.email.setAccessibleName("Email")
        self.form.addRow("Email:", self.email)

        self.password = StandardLineEdit(self)
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setAccessibleName("Contraseña")
        self.form.addRow("Contraseña*:", self.password)

        self.role = SearchableComboBox(self, placeholder="Selecciona un rol…")
        self.role.set_options([(name, name) for name in role_options])
        self.role.setAccessibleName("Rol")
        self.form.addRow("Rol:", self.role)

        self.branch = SearchableComboBox(self, placeholder="Selecciona una sucursal…")
        self.branch.set_options(list(branch_options))
        self.branch.setAccessibleName("Sucursal")
        self.form.addRow("Sucursal*:", self.branch)

        self.employee = SearchableComboBox(self, placeholder="(ninguno)")
        self.employee.set_options([("", "(ninguno)")] + list(employee_options))
        self.employee.setAccessibleName("Empleado RRHH")
        apply_tooltip(self.employee, "Vincula este usuario a un empleado de RRHH.")
        self.form.addRow("Empleado RRHH:", self.employee)

        self.active = QCheckBox("Activo", self)
        self.active.setChecked(True)
        self.form.addRow("", self.active)

        self.add_button_box(ok_text="Crear usuario")

    def values(self) -> dict:
        return {
            "username": self.username.text().strip(), "full_name": self.full_name.text().strip(),
            "email": self.email.text().strip(), "password": self.password.text(),
            "role": self.role.current_id() or "", "branch_id": self.branch.current_id() or "",
            "employee_id": self.employee.current_id() or "", "active": self.active.isChecked(),
        }


class UserEditDialog(FormDialog):
    """Edits every field except `username` — the login identifier is the
    identity field, same boundary every other create/edit pair in this
    package draws. Blank password leaves the current one unchanged."""

    def __init__(
        self, parent=None, *, username: str = "", full_name: str = "", email: str = "", role: str = "",
        branch_id: str = "", employee_id: str = "", active: bool = True, role_options=(),
        branch_options=(), employee_options=(),
    ) -> None:
        super().__init__(parent, title=f"Editar usuario «{username}»")
        self.full_name = StandardLineEdit(self)
        self.full_name.setText(full_name)
        self.full_name.setAccessibleName("Nombre")
        self.form.addRow("Nombre:", self.full_name)

        self.email = StandardLineEdit(self)
        self.email.setText(email)
        self.email.setAccessibleName("Email")
        self.form.addRow("Email:", self.email)

        self.password = StandardLineEdit(self)
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setAccessibleName("Contraseña")
        apply_tooltip(self.password, "Deja vacío para no cambiar la contraseña.")
        self.form.addRow("Contraseña:", self.password)

        self.role = SearchableComboBox(self, placeholder="Selecciona un rol…")
        self.role.set_options([(name, name) for name in role_options])
        self.role.setAccessibleName("Rol")
        self.role.set_current_id(role)
        self.form.addRow("Rol:", self.role)

        self.branch = SearchableComboBox(self, placeholder="Selecciona una sucursal…")
        self.branch.set_options(list(branch_options))
        self.branch.setAccessibleName("Sucursal")
        self.branch.set_current_id(branch_id)
        self.form.addRow("Sucursal*:", self.branch)

        self.employee = SearchableComboBox(self, placeholder="(ninguno)")
        self.employee.set_options([("", "(ninguno)")] + list(employee_options))
        self.employee.setAccessibleName("Empleado RRHH")
        self.employee.set_current_id(employee_id or "")
        self.form.addRow("Empleado RRHH:", self.employee)

        self.active = QCheckBox("Activo", self)
        self.active.setChecked(active)
        self.form.addRow("", self.active)

        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        return {
            "full_name": self.full_name.text().strip(), "email": self.email.text().strip(),
            "password": self.password.text(), "role": self.role.current_id() or "",
            "branch_id": self.branch.current_id() or "", "employee_id": self.employee.current_id() or "",
            "active": self.active.isChecked(),
        }


class RoleCreateDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nuevo rol")
        self.name = StandardLineEdit(self)
        self.name.setAccessibleName("Nombre del rol")
        self.form.addRow("Nombre*:", self.name)

        self.description = StandardLineEdit(self)
        self.description.setAccessibleName("Descripción del rol")
        self.form.addRow("Descripción:", self.description)

        self.add_button_box(ok_text="Crear rol")

    def values(self) -> dict:
        return {"name": self.name.text().strip(), "description": self.description.text().strip()}


class RoleEditDialog(FormDialog):
    """Edits only `description` — `name` stays identity-adjacent (the
    legacy schema keys role lookups by name, `roles.nombre UNIQUE`),
    same boundary every other create/edit pair in this package draws."""

    def __init__(self, parent=None, *, name: str = "", description: str = "") -> None:
        super().__init__(parent, title=f"Editar rol «{name}»")
        self.description = StandardLineEdit(self)
        self.description.setText(description)
        self.description.setAccessibleName("Descripción del rol")
        self.form.addRow("Descripción:", self.description)
        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        return {"description": self.description.text().strip()}
