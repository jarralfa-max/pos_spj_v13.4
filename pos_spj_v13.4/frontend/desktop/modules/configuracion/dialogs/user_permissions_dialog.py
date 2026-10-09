"""Permisos de UN usuario: excepciones sobre lo que le da su rol.

Por acción, tres estados: «Como su rol» (sin excepción), «Conceder» y «Negar».
La matriz llega resuelta (lo del rol y las excepciones guardadas); el diálogo
sólo junta lo que cambió. Quién puede conceder qué lo revalida el caso de uso.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QGridLayout, QLabel, QWidget

from frontend.desktop.components import (
    FormDialog,
    SearchableComboBox,
    StandardComboBox,
    StandardLineEdit,
)
from frontend.desktop.themes.tokens import DialogMetrics, Spacing

INHERIT, GRANT, DENY = "INHERIT", "GRANT", "DENY"


class UserPermissionsDialog(FormDialog):
    def __init__(self, parent=None, *, matrix) -> None:
        super().__init__(parent, title=f"Permisos de {matrix.user_name}", width=DialogMetrics.WIDTH_LG)
        self._matrix = matrix
        self._initial = {o.code: matrix.state(o.code) for m in matrix.modules for o in m.actions}
        self._state = dict(self._initial)
        self._combos: dict[str, StandardComboBox] = {}

        nota = QLabel(f"Rol: {matrix.role_name or 'sin rol'}. {matrix.note}", self)
        nota.setWordWrap(True)
        nota.setProperty("role", "muted")
        self.form.addRow(nota)

        self.module = SearchableComboBox(self, placeholder="Selecciona un módulo…")
        self.module.setAccessibleName("Módulo")
        self.form.addRow("Módulo:", self.module)
        self.search = StandardLineEdit(self)
        self.search.setPlaceholderText("Buscar acción…")
        self.search.setAccessibleName("Buscar acción")
        self.form.addRow("Buscar:", self.search)

        self._grid_host = QWidget(self)
        self._grid = QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(Spacing.MD)
        self._grid.setVerticalSpacing(Spacing.XS)
        self.form.addRow(self._grid_host)

        self.summary = QLabel(self)
        self.form.addRow(self.summary)
        self.add_button_box(ok_text="Guardar permisos")

        self.module.set_options([
            (m.key, m.label) for m in matrix.modules])
        self.module.currentIndexChanged.connect(lambda _i: self._render())
        self.search.textChanged.connect(lambda _t: self._render())
        if matrix.modules:
            self.module.set_current_id(matrix.modules[0].key)
        self._render()

    def changes(self) -> dict[str, str]:
        """Sólo lo que cambió: `código → INHERIT | GRANT | DENY`."""
        return {c: s for c, s in self._state.items() if s != self._initial[c]}

    def _render(self) -> None:
        while self._grid.count():
            widget = self._grid.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
        self._combos.clear()
        modulo = next((m for m in self._matrix.modules if m.key == self.module.current_id()), None)
        if modulo is None:
            return
        termino = self.search.text().strip().lower()
        fila = 0
        for opcion in modulo.actions:
            if termino and termino not in f"{opcion.label} {opcion.code}".lower():
                continue
            etiqueta = QLabel(opcion.label, self._grid_host)
            etiqueta.setToolTip(opcion.code)
            combo = StandardComboBox(self._grid_host, accessible_name=opcion.label)
            del_rol = "sí" if opcion.code in self._matrix.role_granted else "no"
            combo.addItem(f"Como su rol ({del_rol})", INHERIT)
            combo.addItem("Conceder", GRANT)
            if self._matrix.mode != "GRANT_ONLY" or self._initial[opcion.code] == DENY:
                combo.addItem("Negar", DENY)
            combo.setCurrentIndex(max(combo.findData(self._state[opcion.code]), 0))
            combo.currentIndexChanged.connect(
                lambda _i, code=opcion.code, c=combo: self._set(code, c.currentData()))
            self._grid.addWidget(etiqueta, fila, 0)
            self._grid.addWidget(combo, fila, 1)
            self._combos[opcion.code] = combo
            fila += 1
        self._update_summary()

    def _set(self, code: str, state: str) -> None:
        self._state[code] = state
        self._update_summary()

    def _update_summary(self) -> None:
        cambios = self.changes()
        self.summary.setText(f"Cambios sin guardar: {len(cambios)}." if cambios else "Sin cambios.")


__all__ = ["UserPermissionsDialog"]
