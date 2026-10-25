"""Permisos de UN usuario: excepciones sobre lo que le da su rol.

Por acción, tres estados: «Como su rol» (sin excepción), «Conceder» y «Negar».
La matriz llega resuelta (lo del rol, las excepciones guardadas y el permiso
efectivo con su origen); el diálogo sólo junta lo que cambió. Quién puede
conceder qué lo revalida el caso de uso.

Auditoría de permisos 968e0bc (PER-08): el ÁMBITO elige si la excepción rige en
todas las sucursales o sólo en una, y la columna «Efectivo» dice qué resulta y
qué capa lo decidió — así se explica por qué alguien sigue pudiendo operar.
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
_ALL_BRANCHES = ""


class UserPermissionsDialog(FormDialog):
    def __init__(self, parent=None, *, matrix, load_matrix=None) -> None:
        super().__init__(parent, title=f"Permisos de {matrix.user_name}", width=DialogMetrics.WIDTH_LG)
        self._load_matrix = load_matrix
        self._combos: dict[str, StandardComboBox] = {}
        self._set_matrix(matrix)

        self.note = QLabel(self)
        self.note.setWordWrap(True)
        self.note.setProperty("role", "muted")
        self.form.addRow(self.note)

        self.scope = SearchableComboBox(self, placeholder="Selecciona el ámbito…")
        self.scope.setAccessibleName("Ámbito de las excepciones")
        self.scope.set_options([(_ALL_BRANCHES, "Todas las sucursales")]
                               + [(bid, f"Sólo en {nombre}") for bid, nombre in matrix.branches])
        self.scope.set_current_id(matrix.scope_branch_id or _ALL_BRANCHES)
        self.scope.setEnabled(load_matrix is not None and bool(matrix.branches))
        self.form.addRow("Ámbito:", self.scope)

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
        self.scope.currentIndexChanged.connect(lambda _i: self._change_scope())
        if matrix.modules:
            self.module.set_current_id(matrix.modules[0].key)
        self._update_note()
        self._render()

    def changes(self) -> dict[str, str]:
        """Sólo lo que cambió: `código → INHERIT | GRANT | DENY`."""
        return {c: s for c, s in self._state.items() if s != self._initial[c]}

    def scope_branch_id(self) -> str:
        """"" = todas las sucursales; un id = sólo esa sucursal."""
        return self._matrix.scope_branch_id or _ALL_BRANCHES

    def _set_matrix(self, matrix) -> None:
        self._matrix = matrix
        self._initial = {o.code: matrix.state(o.code) for m in matrix.modules for o in m.actions}
        self._state = dict(self._initial)

    def _change_scope(self) -> None:
        nuevo = self.scope.current_id() or _ALL_BRANCHES
        if self._load_matrix is None or nuevo == self.scope_branch_id():
            return
        matrix = self._load_matrix(nuevo)
        if matrix is None:
            return
        # Las excepciones son por ámbito: cambiarlo descarta lo no guardado.
        self._set_matrix(matrix)
        self._update_note()
        self._render()

    def _update_note(self) -> None:
        ambito = ("en todas las sucursales" if not self._matrix.scope_branch_id
                  else "sólo en la sucursal elegida; una excepción aquí gana a la general")
        self.note.setText(f"Rol: {self._matrix.role_name or 'sin rol'}. {self._matrix.note} "
                          f"Las excepciones que edites rigen {ambito}. Cambiar el ámbito "
                          "descarta los cambios sin guardar.")

    def _render(self) -> None:
        while self._grid.count():
            widget = self._grid.takeAt(0).widget()
            if widget is not None:
                widget.setParent(None)
        self._combos.clear()
        modulo = next((m for m in self._matrix.modules if m.key == self.module.current_id()), None)
        if modulo is None:
            return
        for col, titulo in enumerate(("Acción", "Excepción", "Efectivo")):
            cabecera = QLabel(titulo, self._grid_host)
            cabecera.setProperty("role", "muted")
            self._grid.addWidget(cabecera, 0, col)
        termino = self.search.text().strip().lower()
        fila = 1
        for opcion in modulo.actions:
            if termino and termino not in f"{opcion.label} {opcion.code}".lower():
                continue
            etiqueta = QLabel(opcion.label, self._grid_host)
            etiqueta.setToolTip(opcion.code)
            combo = StandardComboBox(self._grid_host, accessible_name=opcion.label)
            del_rol = "sí" if opcion.code in self._matrix.role_granted else "no"
            combo.addItem(f"Como su rol ({del_rol})", INHERIT)
            combo.addItem("Conceder", GRANT)
            combo.addItem("Negar", DENY)
            combo.setCurrentIndex(max(combo.findData(self._state[opcion.code]), 0))
            combo.currentIndexChanged.connect(
                lambda _i, code=opcion.code, c=combo: self._set(code, c.currentData()))
            efectivo = QLabel(self._matrix.effective_label(opcion.code), self._grid_host)
            efectivo.setProperty("role", "muted")
            efectivo.setToolTip("Lo que rige hoy, antes de guardar los cambios de esta ventana.")
            self._grid.addWidget(etiqueta, fila, 0)
            self._grid.addWidget(combo, fila, 1)
            self._grid.addWidget(efectivo, fila, 2)
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
