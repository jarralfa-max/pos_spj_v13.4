"""Dialogs for the "Apariencia" section — UI/UX phase."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PyQt5.QtWidgets import QCheckBox

from frontend.desktop.components import ConfirmationDialog, FormDialog, SearchableComboBox, StandardLineEdit

_THEME_MODES = (("LIGHT", "Claro"), ("DARK", "Oscuro"))
_TOKEN_CATEGORIES = (
    ("COLOR", "Color"), ("SPACING", "Espaciado"), ("TYPOGRAPHY", "Tipografía"), ("RADIUS", "Radio"),
    ("BORDER", "Borde"), ("ELEVATION", "Elevación"), ("ICON_SIZE", "Tamaño de ícono"),
    ("CONTROL_HEIGHT", "Altura de control"),
)
_DENSITY_LEVELS = (("COMPACT", "Compacta"), ("NORMAL", "Normal"), ("COMFORTABLE", "Cómoda"))
_SCOPE_TYPES = (("GLOBAL", "Global"), ("BRANCH", "Sucursal"), ("USER", "Usuario"))


class SetDefaultThemeDialog(ConfirmationDialog):
    """Confirms marking one `Theme` as the system default before calling
    `SetDefaultThemeUseCase` — a non-destructive but system-wide change,
    so it gets an explicit confirmation like every other Configuración
    write action in this phase."""

    def __init__(self, parent=None, *, theme_name: str = "") -> None:
        super().__init__(
            parent, title="Marcar como predeterminado",
            message=f"¿Marcar «{theme_name}» como el tema predeterminado del sistema?",
            confirm_text="Marcar como predeterminado",
        )


class ThemeCreateDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nuevo tema")
        self.code = StandardLineEdit(self)
        self.code.setAccessibleName("Código del tema")
        self.form.addRow("Código:", self.code)

        self.name = StandardLineEdit(self)
        self.name.setAccessibleName("Nombre del tema")
        self.form.addRow("Nombre:", self.name)

        self.mode = SearchableComboBox(self, placeholder="Selecciona un modo…")
        self.mode.set_options(list(_THEME_MODES))
        self.mode.setAccessibleName("Modo")
        self.form.addRow("Modo:", self.mode)

        self.add_button_box(ok_text="Crear tema")

    def values(self) -> dict:
        return {
            "code": self.code.text().strip(), "name": self.name.text().strip(), "mode": self.mode.current_id(),
        }


class ThemeEditDialog(FormDialog):
    """Edits only `name` — `code`/`mode` are identity fields, same
    boundary every other create/edit pair in this package draws."""

    def __init__(self, parent=None, *, name: str = "") -> None:
        super().__init__(parent, title="Editar tema")
        self.name = StandardLineEdit(self)
        self.name.setText(name)
        self.name.setAccessibleName("Nombre del tema")
        self.form.addRow("Nombre:", self.name)
        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        return {"name": self.name.text().strip()}


class DesignTokenCreateDialog(FormDialog):
    def __init__(self, parent=None, *, theme_name: str = "") -> None:
        super().__init__(parent, title="Nuevo token de diseño")
        self.token_key = StandardLineEdit(self)
        self.token_key.setAccessibleName("Clave del token")
        self.form.addRow("Clave:", self.token_key)

        self.category = SearchableComboBox(self, placeholder="Selecciona una categoría…")
        self.category.set_options(list(_TOKEN_CATEGORIES))
        self.category.setAccessibleName("Categoría")
        self.form.addRow("Categoría:", self.category)

        self.token_value = StandardLineEdit(self)
        self.token_value.setAccessibleName("Valor del token")
        self.form.addRow("Valor:", self.token_value)

        self.is_global = QCheckBox("Global (todos los temas)", self)
        self.is_global.setChecked(theme_name == "")
        self.is_global.setEnabled(theme_name != "")
        self.form.addRow("", self.is_global)

        self.add_button_box(ok_text="Crear token")

    def values(self) -> dict:
        return {
            "token_key": self.token_key.text().strip(), "category": self.category.current_id(),
            "token_value": self.token_value.text().strip(), "is_global": self.is_global.isChecked(),
        }


class DesignTokenEditDialog(FormDialog):
    """Edits only `token_value` — `theme_id`/`token_key`/`category` are
    identity fields."""

    def __init__(self, parent=None, *, token_value: str = "") -> None:
        super().__init__(parent, title="Editar valor de token")
        self.token_value = StandardLineEdit(self)
        self.token_value.setText(token_value)
        self.token_value.setAccessibleName("Valor del token")
        self.form.addRow("Valor:", self.token_value)
        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        return {"token_value": self.token_value.text().strip()}


def _parse_int(text: str, default: int) -> int:
    try:
        return int(text.strip() or str(default))
    except ValueError:
        return default


def _parse_decimal(text: str, default: str) -> Decimal:
    try:
        return Decimal(text.strip() or default)
    except InvalidOperation:
        return Decimal(default)


class DensityProfileCreateDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nuevo perfil de densidad")
        self.level = SearchableComboBox(self, placeholder="Selecciona un nivel…")
        self.level.set_options(list(_DENSITY_LEVELS))
        self.level.setAccessibleName("Nivel de densidad")
        self.form.addRow("Nivel:", self.level)

        self.name = StandardLineEdit(self)
        self.name.setAccessibleName("Nombre del perfil")
        self.form.addRow("Nombre:", self.name)

        self.scale_factor = StandardLineEdit(self)
        self.scale_factor.setText("1.0")
        self.scale_factor.setAccessibleName("Factor de escala")
        self.form.addRow("Factor de escala:", self.scale_factor)

        self.control_height_px = StandardLineEdit(self)
        self.control_height_px.setText("40")
        self.control_height_px.setAccessibleName("Altura de control (px)")
        self.form.addRow("Altura de control (px):", self.control_height_px)

        self.touch_target_px = StandardLineEdit(self)
        self.touch_target_px.setText("44")
        self.touch_target_px.setAccessibleName("Objetivo táctil (px)")
        self.form.addRow("Objetivo táctil (px):", self.touch_target_px)

        self.spacing_unit_px = StandardLineEdit(self)
        self.spacing_unit_px.setText("8")
        self.spacing_unit_px.setAccessibleName("Unidad de espaciado (px)")
        self.form.addRow("Unidad de espaciado (px):", self.spacing_unit_px)

        self.add_button_box(ok_text="Crear perfil")

    def values(self) -> dict:
        return {
            "level": self.level.current_id(), "name": self.name.text().strip(),
            "scale_factor": _parse_decimal(self.scale_factor.text(), "1.0"),
            "control_height_px": _parse_int(self.control_height_px.text(), 40),
            "touch_target_px": _parse_int(self.touch_target_px.text(), 44),
            "spacing_unit_px": _parse_int(self.spacing_unit_px.text(), 8),
        }


class DensityProfileEditDialog(FormDialog):
    """Edits name/scale_factor/pixel metrics — `level` is the identity
    field, same boundary every other create/edit pair in this package
    draws."""

    def __init__(
        self, parent=None, *, name: str = "", scale_factor: str = "1.0", control_height_px: int = 40,
        touch_target_px: int = 44, spacing_unit_px: int = 8,
    ) -> None:
        super().__init__(parent, title="Editar perfil de densidad")
        self.name = StandardLineEdit(self)
        self.name.setText(name)
        self.name.setAccessibleName("Nombre del perfil")
        self.form.addRow("Nombre:", self.name)

        self.scale_factor = StandardLineEdit(self)
        self.scale_factor.setText(scale_factor)
        self.scale_factor.setAccessibleName("Factor de escala")
        self.form.addRow("Factor de escala:", self.scale_factor)

        self.control_height_px = StandardLineEdit(self)
        self.control_height_px.setText(str(control_height_px))
        self.control_height_px.setAccessibleName("Altura de control (px)")
        self.form.addRow("Altura de control (px):", self.control_height_px)

        self.touch_target_px = StandardLineEdit(self)
        self.touch_target_px.setText(str(touch_target_px))
        self.touch_target_px.setAccessibleName("Objetivo táctil (px)")
        self.form.addRow("Objetivo táctil (px):", self.touch_target_px)

        self.spacing_unit_px = StandardLineEdit(self)
        self.spacing_unit_px.setText(str(spacing_unit_px))
        self.spacing_unit_px.setAccessibleName("Unidad de espaciado (px)")
        self.form.addRow("Unidad de espaciado (px):", self.spacing_unit_px)

        self.add_button_box(ok_text="Guardar")

    def values(self) -> dict:
        return {
            "name": self.name.text().strip(), "scale_factor": _parse_decimal(self.scale_factor.text(), "1.0"),
            "control_height_px": _parse_int(self.control_height_px.text(), 40),
            "touch_target_px": _parse_int(self.touch_target_px.text(), 44),
            "spacing_unit_px": _parse_int(self.spacing_unit_px.text(), 8),
        }


class AppearancePreferenceCreateDialog(FormDialog):
    def __init__(self, parent=None, *, theme_options=()) -> None:
        super().__init__(parent, title="Nueva preferencia de apariencia")
        self.scope_type = SearchableComboBox(self, placeholder="Selecciona un alcance…")
        self.scope_type.set_options(list(_SCOPE_TYPES))
        self.scope_type.setAccessibleName("Alcance")
        self.form.addRow("Alcance:", self.scope_type)

        self.scope_id = StandardLineEdit(self)
        self.scope_id.setAccessibleName("Identificador del alcance")
        self.form.addRow("ID de alcance:", self.scope_id)

        self.theme = SearchableComboBox(self, placeholder="Selecciona un tema…")
        self.theme.set_options([(o.entity_id, o.name) for o in theme_options])
        self.theme.setAccessibleName("Tema")
        self.form.addRow("Tema:", self.theme)

        self.density_level = SearchableComboBox(self, placeholder="Selecciona una densidad…")
        self.density_level.set_options(list(_DENSITY_LEVELS))
        self.density_level.setAccessibleName("Densidad")
        self.form.addRow("Densidad:", self.density_level)

        self.scope_type.currentIndexChanged.connect(self._on_scope_type_changed)
        self._on_scope_type_changed()

        self.add_button_box(ok_text="Crear preferencia")

    def _on_scope_type_changed(self) -> None:
        is_global = self.scope_type.current_id() == "GLOBAL"
        self.scope_id.setEnabled(not is_global)
        if is_global:
            self.scope_id.clear()

    def values(self) -> dict:
        return {
            "scope_type": self.scope_type.current_id(), "scope_id": self.scope_id.text().strip() or None,
            "theme_id": self.theme.current_id(), "density_level": self.density_level.current_id(),
        }
