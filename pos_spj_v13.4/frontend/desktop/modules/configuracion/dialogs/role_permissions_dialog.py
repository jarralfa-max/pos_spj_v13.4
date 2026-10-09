"""Permisos de un rol: dar o quitar acceso, módulo por módulo.

La matriz llega resuelta (módulos, acciones con etiqueta, lo concedido y el
modo del rol). El diálogo sólo junta lo que el usuario marcó y desmarcó; quién
puede otorgar qué lo revalida el caso de uso.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import (
    FormDialog,
    SearchableComboBox,
    StandardCheckBox,
    StandardLineEdit,
    create_secondary_button,
)
from frontend.desktop.themes.tokens import DialogMetrics, Spacing


class RolePermissionsDialog(FormDialog):
    def __init__(self, parent=None, *, matrix) -> None:
        super().__init__(parent, title=f"Permisos del rol «{matrix.role_name}»",
                         width=DialogMetrics.WIDTH_LG)
        self._matrix = matrix
        self._initial = {o.code: o.code in matrix.granted
                         for m in matrix.modules for o in m.actions}
        self._state = dict(self._initial)
        self._grant_only = matrix.mode == "GRANT_ONLY"
        self._boxes: dict[str, StandardCheckBox] = {}

        nota = QLabel(matrix.note, self)
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

        acciones = QWidget(self)
        fila = QHBoxLayout(acciones)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(Spacing.SM)
        self.check_all_button = create_secondary_button(acciones, "Marcar todo el módulo")
        self.uncheck_all_button = create_secondary_button(acciones, "Quitar todo el módulo")
        fila.addWidget(self.check_all_button)
        fila.addWidget(self.uncheck_all_button)
        fila.addStretch(1)
        self.form.addRow(acciones)

        self._list = QWidget(self)
        self._list_layout = QVBoxLayout(self._list)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(Spacing.XS)
        self.form.addRow(self._list)

        self.summary = QLabel(self)
        self.form.addRow(self.summary)
        self.add_button_box(ok_text="Guardar permisos")

        self.module.currentIndexChanged.connect(lambda _i: self._render())
        self.search.textChanged.connect(lambda _t: self._render())
        self.check_all_button.clicked.connect(lambda: self._set_module(True))
        self.uncheck_all_button.clicked.connect(lambda: self._set_module(False))
        self._refresh_modules()
        if matrix.modules:
            self.module.set_current_id(matrix.modules[0].key)
        self._render()

    # ── estado ──────────────────────────────────────────────────────────
    def changes(self) -> dict[str, bool]:
        """Sólo lo que cambió respecto de lo concedido: `código → otorgado`."""
        return {code: value for code, value in self._state.items()
                if value != self._initial[code]}

    def _current_module(self):
        key = self.module.current_id()
        return next((m for m in self._matrix.modules if m.key == key), None)

    def _refresh_modules(self) -> None:
        """Actualiza el conteo «concedidos/total» de cada módulo SIN redibujar
        la lista: se llama desde la señal de una casilla, y redibujar la
        destruiría mientras su propia señal sigue en curso."""
        actual = self.module.current_id()
        self.module.set_options([
            (m.key, f"{m.label} ({sum(self._state[o.code] for o in m.actions)}/{len(m.actions)})")
            for m in self._matrix.modules])
        self.module.blockSignals(True)
        try:
            if actual:
                self.module.set_current_id(actual)
        finally:
            self.module.blockSignals(False)

    def _locked(self, code: str) -> bool:
        return self._grant_only and self._initial[code]

    def _render(self) -> None:
        while self._list_layout.count():
            widget = self._list_layout.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
        self._boxes.clear()
        modulo = self._current_module()
        if modulo is None:
            return
        termino = self.search.text().strip().lower()
        for opcion in modulo.actions:
            if termino and termino not in f"{opcion.label} {opcion.code}".lower():
                continue
            box = StandardCheckBox(opcion.label, self._list)
            box.setToolTip(opcion.code)
            box.setChecked(self._state[opcion.code])
            box.setEnabled(not self._locked(opcion.code))
            box.toggled.connect(lambda checked, code=opcion.code: self._toggle(code, checked))
            self._list_layout.addWidget(box)
            self._boxes[opcion.code] = box
        self._update_summary()

    def _toggle(self, code: str, checked: bool) -> None:
        self._state[code] = checked
        self._refresh_modules()
        self._update_summary()

    def _set_module(self, value: bool) -> None:
        modulo = self._current_module()
        if modulo is None:
            return
        for opcion in modulo.actions:
            if not self._locked(opcion.code):
                self._state[opcion.code] = value
        self._refresh_modules()
        self._render()

    def _update_summary(self) -> None:
        cambios = self.changes()
        dar = sum(1 for v in cambios.values() if v)
        quitar = len(cambios) - dar
        self.summary.setText(
            f"Cambios sin guardar: {dar} por otorgar, {quitar} por retirar." if cambios
            else "Sin cambios.")


__all__ = ["RolePermissionsDialog"]
