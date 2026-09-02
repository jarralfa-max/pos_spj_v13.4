"""Dialogs for the "Feature Flags" section — UI/UX phase. Built entirely
on `StandardDialog`/`FormDialog` (FASE DS-3), never a raw `QDialog`.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QCheckBox, QDialogButtonBox

from frontend.desktop.components import (
    FormDialog, SearchableComboBox, StandardLineEdit, StandardTextArea, apply_tooltip,
)

_SCOPE_TYPES = (("GLOBAL", "Global"), ("BRANCH", "Sucursal"), ("USER", "Usuario"))


class RejectChangeRequestDialog(FormDialog):
    """Rejecting a `FeatureFlagChangeRequest` always requires a reason —
    the domain (`FeatureFlagChangeRequest.reject`) rejects a blank one, so
    this dialog can't be submitted without one either."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Rechazar solicitud")
        self.reason = StandardTextArea(self)
        self.reason.setAccessibleName("Motivo de rechazo")
        apply_tooltip(self.reason, "Explica por qué se rechaza esta solicitud de cambio.")
        self.form.addRow("Motivo:", self.reason)
        box = self.add_button_box(ok_text="Rechazar")
        self._ok_button = box.button(QDialogButtonBox.Ok)
        self._ok_button.setEnabled(False)
        self.reason.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self) -> None:
        self._ok_button.setEnabled(bool(self.reason_text()))

    def reason_text(self) -> str:
        return self.reason.toPlainText().strip()


class FeatureFlagCreateDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nuevo feature flag")
        self.code = StandardLineEdit(self)
        self.code.setAccessibleName("Código del flag")
        apply_tooltip(self.code, "Identificador único, ej. «delivery_auto_asign».")
        self.form.addRow("Código:", self.code)

        self.name = StandardLineEdit(self)
        self.name.setAccessibleName("Nombre del flag")
        self.form.addRow("Nombre:", self.name)

        self.description = StandardLineEdit(self)
        self.description.setAccessibleName("Descripción del flag")
        self.form.addRow("Descripción:", self.description)

        self.default_enabled = QCheckBox("Habilitado por defecto", self)
        self.form.addRow("", self.default_enabled)

        self.add_button_box(ok_text="Crear flag")

    def values(self) -> dict:
        return {
            "code": self.code.text().strip(), "name": self.name.text().strip(),
            "description": self.description.text().strip(), "default_enabled": self.default_enabled.isChecked(),
        }


class FeatureFlagEditDialog(FormDialog):
    """Edits name/description/default_enabled — never `code` (identity),
    same boundary every other create/edit pair in this package draws."""

    def __init__(
        self, parent=None, *, name: str = "", description: str = "", default_enabled: bool = False,
    ) -> None:
        super().__init__(parent, title="Editar feature flag")
        self.name = StandardLineEdit(self)
        self.name.setText(name)
        self.name.setAccessibleName("Nombre del flag")
        self.form.addRow("Nombre:", self.name)

        self.description = StandardLineEdit(self)
        self.description.setText(description)
        self.description.setAccessibleName("Descripción del flag")
        self.form.addRow("Descripción:", self.description)

        self.default_enabled = QCheckBox("Habilitado por defecto", self)
        self.default_enabled.setChecked(default_enabled)
        self.form.addRow("", self.default_enabled)

        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        return {
            "name": self.name.text().strip(), "description": self.description.text().strip(),
            "default_enabled": self.default_enabled.isChecked(),
        }


class RequestFeatureFlagChangeDialog(FormDialog):
    """Originates a `FeatureFlagChangeRequest` — the piece that feeds the
    existing Approve/Reject/Apply flow. `scope_id` is disabled for
    scope_type=GLOBAL, mirroring `FeatureFlagRule.create()`'s own domain
    validation (GLOBAL must not carry a scope_id)."""

    def __init__(self, parent=None, *, flag_options=()) -> None:
        super().__init__(parent, title="Solicitar cambio de feature flag")
        self.flag = SearchableComboBox(self, placeholder="Selecciona un flag…")
        self.flag.set_options([(o.entity_id, f"{o.code} ({o.name})") for o in flag_options])
        self.flag.setAccessibleName("Flag")
        self.form.addRow("Flag:", self.flag)

        self.scope_type = SearchableComboBox(self, placeholder="Selecciona un alcance…")
        self.scope_type.set_options(list(_SCOPE_TYPES))
        self.scope_type.setAccessibleName("Alcance")
        self.form.addRow("Alcance:", self.scope_type)

        self.scope_id = StandardLineEdit(self)
        self.scope_id.setAccessibleName("Identificador del alcance")
        apply_tooltip(self.scope_id, "ID de sucursal o usuario. Vacío y deshabilitado para alcance Global.")
        self.form.addRow("ID de alcance:", self.scope_id)

        self.proposed_enabled = QCheckBox("Proponer habilitado", self)
        self.proposed_enabled.setChecked(True)
        self.form.addRow("", self.proposed_enabled)

        self.proposed_rollout_percentage = StandardLineEdit(self)
        self.proposed_rollout_percentage.setText("100")
        self.proposed_rollout_percentage.setAccessibleName("Porcentaje de despliegue")
        apply_tooltip(self.proposed_rollout_percentage, "Entero entre 0 y 100.")
        self.form.addRow("Rollout (%):", self.proposed_rollout_percentage)

        self.scope_type.currentIndexChanged.connect(self._on_scope_type_changed)
        self._on_scope_type_changed()

        self.add_button_box(ok_text="Solicitar cambio")

    def _on_scope_type_changed(self) -> None:
        is_global = self.scope_type.current_id() == "GLOBAL"
        self.scope_id.setEnabled(not is_global)
        if is_global:
            self.scope_id.clear()

    def values(self) -> dict:
        try:
            rollout = int(self.proposed_rollout_percentage.text().strip() or "100")
        except ValueError:
            rollout = 100
        return {
            "flag_id": self.flag.current_id(), "scope_type": self.scope_type.current_id(),
            "scope_id": self.scope_id.text().strip() or None,
            "proposed_enabled": self.proposed_enabled.isChecked(),
            "proposed_rollout_percentage": rollout,
        }
