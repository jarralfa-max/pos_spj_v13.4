"""Apariencia page — the base inherited table (title "Apariencia",
`_page_apariencia` query) is now the real Themes admin table
(create/edit/activate/deactivate + "Marcar como predeterminado"), same
"reuse the inherited table as the main interactive table" shape
`FeatureFlagsPage`/`NotificacionesPage` established. A "Tokens" card,
driven by the Themes table's current selection, shows that theme's
GLOBAL + theme-specific `DesignToken`s (mirrors `FeatureFlagsPage`'s
"Reglas activas" selection-driven card). "Perfiles de densidad" and
"Preferencias por alcance" are independent sibling cards, same
always-visible shape `NotificacionesPage`'s Accounts/Templates cards
use — neither is scoped to a Theme selection.
"""
from PyQt5.QtWidgets import QDialog, QHBoxLayout, QMessageBox, QWidget

from frontend.desktop.components import (
    ColumnSpec, SectionCard, StandardTable, ViewState, create_primary_button, create_secondary_button,
    create_state_widget, create_warning_button,
)
from frontend.desktop.modules.configuracion.dialogs import (
    AppearancePreferenceCreateDialog,
    DensityProfileCreateDialog,
    DensityProfileEditDialog,
    DesignTokenCreateDialog,
    DesignTokenEditDialog,
    SetDefaultThemeDialog,
    ThemeCreateDialog,
    ThemeEditDialog,
)
from frontend.desktop.themes.tokens import Spacing

from .base_page import ConfiguracionWorkspacePage

_TOKEN_COLUMNS = [
    ColumnSpec("Alcance"), ColumnSpec("Clave"), ColumnSpec("Categoría"), ColumnSpec("Valor"),
]
_DENSITY_COLUMNS = [
    ColumnSpec("Nivel"), ColumnSpec("Nombre"), ColumnSpec("Escala"), ColumnSpec("Activo", "status"),
]
_PREFERENCE_COLUMNS = [
    ColumnSpec("Alcance"), ColumnSpec("ID de alcance"), ColumnSpec("Tema"), ColumnSpec("Densidad"),
    ColumnSpec("Activo", "status"),
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


class AparienciaPage(ConfiguracionWorkspacePage):
    page_id = "config_apariencia"
    title = "Apariencia"
    subtitle = "Temas, tokens de diseño, perfiles de densidad y preferencias por alcance."
    action_text = "Marcar como predeterminado"

    def __init__(self, presenter, parent=None) -> None:
        super().__init__(presenter, parent)
        self._theme_names: dict[str, str] = {}

        self.new_theme_button = create_primary_button(self, "Nuevo tema")
        self.edit_theme_button = create_secondary_button(self, "Editar")
        self.activate_theme_button = create_secondary_button(self, "Activar")
        self.deactivate_theme_button = create_warning_button(self, "Desactivar")
        self.action_button = create_secondary_button(self, self.action_text)
        theme_actions = _button_row(
            self, self.new_theme_button, self.edit_theme_button, self.activate_theme_button,
            self.deactivate_theme_button, self.action_button,
        )
        self.layout().insertWidget(1, theme_actions)

        self.new_theme_button.clicked.connect(self._on_new_theme)
        self.edit_theme_button.clicked.connect(self._on_edit_theme)
        self.activate_theme_button.clicked.connect(lambda: self._on_change_theme_status("ACTIVATE"))
        self.deactivate_theme_button.clicked.connect(lambda: self._on_change_theme_status("DEACTIVATE"))
        self.action_button.clicked.connect(self._on_set_default)

        self._build_tokens_card()
        self._build_density_card()
        self._build_preferences_card()

    # ── Temas (base inherited table) ────────────────────────────────────────

    def reload(self, search: str = "") -> None:
        super().reload(search)
        if self.table is not None:
            self.table.itemSelectionChanged.connect(self._on_theme_selection_changed)
        self._theme_names = {t.entity_id: t.name for t in self._presenter.list_themes()}
        self._reload_tokens()
        self._reload_density_profiles()
        self._reload_preferences()

    def _selected_theme_id(self) -> str | None:
        row_id = self.table.selected_row_id() if self.table is not None else None
        if not row_id:
            QMessageBox.warning(self, "Apariencia", "Selecciona un tema primero.")
        return row_id

    def _on_new_theme(self) -> None:
        dlg = ThemeCreateDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["code"] or not values["name"] or not values["mode"]:
            QMessageBox.warning(self, "Apariencia", "Código, nombre y modo son obligatorios.")
            return
        ok, message = self._presenter.create_theme(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Apariencia", message)
        if ok:
            self.reload(self.search.text())

    def _on_edit_theme(self) -> None:
        theme_id = self._selected_theme_id()
        if not theme_id:
            return
        dlg = ThemeEditDialog(self, name=self._theme_names.get(theme_id, ""))
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["name"]:
            QMessageBox.warning(self, "Apariencia", "El nombre es obligatorio.")
            return
        ok, message = self._presenter.update_theme(theme_id=theme_id, **values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Apariencia", message)
        if ok:
            self.reload(self.search.text())

    def _on_change_theme_status(self, action: str) -> None:
        theme_id = self._selected_theme_id()
        if not theme_id:
            return
        ok, message = self._presenter.change_theme_status(theme_id=theme_id, action=action)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Apariencia", message)
        if ok:
            self.reload(self.search.text())

    def _on_set_default(self) -> None:
        theme_id = self.table.selected_row_id() if self.table is not None else None
        if not theme_id:
            QMessageBox.warning(self, "Apariencia", "Selecciona un tema primero.")
            return
        dlg = SetDefaultThemeDialog(self, theme_name=self._theme_names.get(theme_id, theme_id))
        if dlg.exec_() != QDialog.Accepted:
            return
        ok, message = self._presenter.set_default_theme(theme_id)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Apariencia", message)
        if ok:
            self.reload(self.search.text())

    # ── Tokens (driven by Temas selection) ──────────────────────────────────

    def _build_tokens_card(self) -> None:
        self.tokens_card = SectionCard(self, title="Tokens de diseño")
        self.tokens_table = StandardTable(_TOKEN_COLUMNS, self.tokens_card)
        self.tokens_table.setAccessibleName("Tokens de diseño del tema seleccionado")
        self.tokens_card.add(self.tokens_table)
        self.tokens_empty = None

        self.new_token_button = create_primary_button(self.tokens_card, "Nuevo token")
        self.edit_token_button = create_secondary_button(self.tokens_card, "Editar valor")
        self.tokens_card.add(_button_row(self.tokens_card, self.new_token_button, self.edit_token_button))
        self.layout().addWidget(self.tokens_card)

        self.new_token_button.clicked.connect(self._on_new_token)
        self.edit_token_button.clicked.connect(self._on_edit_token)
        self._reload_tokens()

    def _on_theme_selection_changed(self) -> None:
        self._reload_tokens()

    def _reload_tokens(self) -> None:
        theme_id = self.table.selected_row_id() if self.table is not None else None
        tokens = self._presenter.list_design_tokens_for_theme(theme_id) if theme_id else ()
        rows = [
            [self._theme_names.get(t.theme_id, "Global") if t.theme_id else "Global", t.token_key, t.category,
             t.token_value]
            for t in tokens
        ]
        self.tokens_table.load_rows(rows, row_ids=[t.entity_id for t in tokens])
        if self.tokens_empty is not None:
            self.tokens_empty.setParent(None)
            self.tokens_empty = None
        if not rows:
            message = "Selecciona un tema para ver sus tokens." if not theme_id else "Este tema no tiene tokens."
            self.tokens_empty = create_state_widget(ViewState.EMPTY, self.tokens_card, message=message)
            self.tokens_card.add(self.tokens_empty)
        self.tokens_table.setVisible(bool(rows))

    def _selected_token_id(self) -> str | None:
        row_id = self.tokens_table.selected_row_id()
        if not row_id:
            QMessageBox.warning(self, "Apariencia", "Selecciona un token primero.")
        return row_id

    def _on_new_token(self) -> None:
        theme_id = self.table.selected_row_id() if self.table is not None else None
        if not theme_id:
            QMessageBox.warning(self, "Apariencia", "Selecciona un tema primero.")
            return
        dlg = DesignTokenCreateDialog(self, theme_name=self._theme_names.get(theme_id, ""))
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["token_key"] or not values["category"] or not values["token_value"]:
            QMessageBox.warning(self, "Apariencia", "Clave, categoría y valor son obligatorios.")
            return
        is_global = values.pop("is_global")
        ok, message = self._presenter.create_design_token(
            theme_id=None if is_global else theme_id, **values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Apariencia", message)
        if ok:
            self._reload_tokens()

    def _on_edit_token(self) -> None:
        token_id = self._selected_token_id()
        if not token_id:
            return
        dlg = DesignTokenEditDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["token_value"]:
            QMessageBox.warning(self, "Apariencia", "El valor es obligatorio.")
            return
        ok, message = self._presenter.update_design_token(token_id=token_id, **values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Apariencia", message)
        if ok:
            self._reload_tokens()

    # ── Perfiles de densidad (independiente) ────────────────────────────────

    def _build_density_card(self) -> None:
        self.density_card = SectionCard(self, title="Perfiles de densidad")
        self.density_table = StandardTable(_DENSITY_COLUMNS, self.density_card)
        self.density_table.setAccessibleName("Perfiles de densidad")
        self.density_card.add(self.density_table)
        self.density_empty = None

        self.new_density_button = create_primary_button(self.density_card, "Nuevo perfil")
        self.edit_density_button = create_secondary_button(self.density_card, "Editar")
        self.activate_density_button = create_secondary_button(self.density_card, "Activar")
        self.deactivate_density_button = create_warning_button(self.density_card, "Desactivar")
        self.density_card.add(_button_row(
            self.density_card, self.new_density_button, self.edit_density_button,
            self.activate_density_button, self.deactivate_density_button,
        ))
        self.layout().addWidget(self.density_card)

        self.new_density_button.clicked.connect(self._on_new_density_profile)
        self.edit_density_button.clicked.connect(self._on_edit_density_profile)
        self.activate_density_button.clicked.connect(lambda: self._on_change_density_status("ACTIVATE"))
        self.deactivate_density_button.clicked.connect(lambda: self._on_change_density_status("DEACTIVATE"))
        self._reload_density_profiles()

    def _reload_density_profiles(self) -> None:
        profiles = self._presenter.list_density_profiles()
        self._density_by_id = {p.entity_id: p for p in profiles}
        rows = [[p.level, p.name, p.scale_factor, "Sí" if p.active else "No"] for p in profiles]
        self.density_table.load_rows(rows, row_ids=[p.entity_id for p in profiles])
        if self.density_empty is not None:
            self.density_empty.setParent(None)
            self.density_empty = None
        if not rows:
            self.density_empty = create_state_widget(
                ViewState.EMPTY, self.density_card, message="No hay perfiles de densidad todavía.")
            self.density_card.add(self.density_empty)
        self.density_table.setVisible(bool(rows))

    def _selected_density_profile_id(self) -> str | None:
        row_id = self.density_table.selected_row_id()
        if not row_id:
            QMessageBox.warning(self, "Apariencia", "Selecciona un perfil de densidad primero.")
        return row_id

    def _on_new_density_profile(self) -> None:
        dlg = DensityProfileCreateDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["level"] or not values["name"]:
            QMessageBox.warning(self, "Apariencia", "Nivel y nombre son obligatorios.")
            return
        ok, message = self._presenter.create_density_profile(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Apariencia", message)
        if ok:
            self._reload_density_profiles()

    def _on_edit_density_profile(self) -> None:
        profile_id = self._selected_density_profile_id()
        if not profile_id:
            return
        profile = self._density_by_id.get(profile_id)
        if profile is None:
            QMessageBox.warning(self, "Apariencia", "El perfil ya no existe.")
            return
        dlg = DensityProfileEditDialog(
            self, name=profile.name, scale_factor=profile.scale_factor,
            control_height_px=profile.control_height_px, touch_target_px=profile.touch_target_px,
            spacing_unit_px=profile.spacing_unit_px,
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["name"]:
            QMessageBox.warning(self, "Apariencia", "El nombre es obligatorio.")
            return
        ok, message = self._presenter.update_density_profile(profile_id=profile_id, **values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Apariencia", message)
        if ok:
            self._reload_density_profiles()

    def _on_change_density_status(self, action: str) -> None:
        profile_id = self._selected_density_profile_id()
        if not profile_id:
            return
        ok, message = self._presenter.change_density_profile_status(profile_id=profile_id, action=action)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Apariencia", message)
        if ok:
            self._reload_density_profiles()

    # ── Preferencias por alcance (independiente) ────────────────────────────

    def _build_preferences_card(self) -> None:
        self.preferences_card = SectionCard(self, title="Preferencias por alcance")
        self.preferences_table = StandardTable(_PREFERENCE_COLUMNS, self.preferences_card)
        self.preferences_table.setAccessibleName("Preferencias de apariencia por alcance")
        self.preferences_card.add(self.preferences_table)
        self.preferences_empty = None

        self.new_preference_button = create_primary_button(self.preferences_card, "Nueva preferencia")
        self.activate_preference_button = create_secondary_button(self.preferences_card, "Activar")
        self.deactivate_preference_button = create_warning_button(self.preferences_card, "Desactivar")
        self.preferences_card.add(_button_row(
            self.preferences_card, self.new_preference_button, self.activate_preference_button,
            self.deactivate_preference_button,
        ))
        self.layout().addWidget(self.preferences_card)

        self.new_preference_button.clicked.connect(self._on_new_preference)
        self.activate_preference_button.clicked.connect(lambda: self._on_change_preference_status("ACTIVATE"))
        self.deactivate_preference_button.clicked.connect(
            lambda: self._on_change_preference_status("DEACTIVATE"))
        self._reload_preferences()

    def _reload_preferences(self) -> None:
        preferences = self._presenter.list_appearance_preferences()
        rows = [
            [p.scope_type, p.scope_id or "—", p.theme_name, p.density_level, "Sí" if p.active else "No"]
            for p in preferences
        ]
        self.preferences_table.load_rows(rows, row_ids=[p.entity_id for p in preferences])
        if self.preferences_empty is not None:
            self.preferences_empty.setParent(None)
            self.preferences_empty = None
        if not rows:
            self.preferences_empty = create_state_widget(
                ViewState.EMPTY, self.preferences_card, message="No hay preferencias de apariencia todavía.")
            self.preferences_card.add(self.preferences_empty)
        self.preferences_table.setVisible(bool(rows))

    def _selected_preference_id(self) -> str | None:
        row_id = self.preferences_table.selected_row_id()
        if not row_id:
            QMessageBox.warning(self, "Apariencia", "Selecciona una preferencia primero.")
        return row_id

    def _on_new_preference(self) -> None:
        dlg = AppearancePreferenceCreateDialog(self, theme_options=self._presenter.list_themes())
        if dlg.exec_() != QDialog.Accepted:
            return
        values = dlg.values()
        if not values["scope_type"] or not values["theme_id"] or not values["density_level"]:
            QMessageBox.warning(self, "Apariencia", "Alcance, tema y densidad son obligatorios.")
            return
        ok, message = self._presenter.create_appearance_preference(**values)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Apariencia", message)
        if ok:
            self._reload_preferences()

    def _on_change_preference_status(self, action: str) -> None:
        preference_id = self._selected_preference_id()
        if not preference_id:
            return
        ok, message = self._presenter.change_appearance_preference_status(
            preference_id=preference_id, action=action)
        (QMessageBox.information if ok else QMessageBox.warning)(self, "Apariencia", message)
        if ok:
            self._reload_preferences()


__all__ = ["AparienciaPage"]
