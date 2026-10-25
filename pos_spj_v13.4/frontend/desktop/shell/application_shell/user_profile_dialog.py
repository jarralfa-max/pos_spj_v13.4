"""Read-only presentation of the authenticated context; no credential access."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialogButtonBox, QFormLayout, QLabel

from backend.bootstrap.application_context import ApplicationContext
from frontend.desktop.components.dialogs import StandardDialog
from frontend.desktop.themes.tokens import Spacing


class UserProfileDialog(StandardDialog):
    def __init__(self, context: ApplicationContext, *, session_text: str, parent=None):
        super().__init__(parent, title="Mi perfil")
        form = QFormLayout()
        form.setSpacing(Spacing.SM)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        role_labels = {"admin": "Administrador", "administrator": "Administrador",
                       "owner": "Propietario", "operator": "Operador",
                       "cashier": "Cajero", "manager": "Gerente"}
        roles = ", ".join(role_labels.get(role.lower(), role) for role in context.roles)
        for title, value in (("Usuario", context.user_name), ("Roles", roles or "Sin roles asignados"),
                             ("Sucursal", context.branch_name), ("Estado de sesión", session_text)):
            label = QLabel(value, self)
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            label.setAccessibleName(f"{title}: {value}")
            form.addRow(f"{title}:", label)
        self.content_layout().addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.button(QDialogButtonBox.Close).setText("Cerrar")
        buttons.rejected.connect(self.reject)
        self.add_footer_widget(buttons)
