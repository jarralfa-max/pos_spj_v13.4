"""Diálogos de «Estructura organizacional» (auditoría enterprise, Fase 1).
Sobre `FormDialog`, nunca un `QDialog` crudo. Sólo capturan datos: las reglas
(jerarquía, capacidades, códigos) las valida la capa de aplicación.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QGridLayout, QWidget

from frontend.desktop.components import (
    FormDialog,
    SearchableComboBox,
    StandardCheckBox,
    StandardLineEdit,
    apply_tooltip,
)

#: Etiqueta visible de cada capacidad (el código viaja tal cual a la aplicación).
CAPABILITY_LABELS = (
    ("SALES", "Ventas"), ("POS", "Punto de venta"), ("CASH", "Caja"),
    ("INVENTORY", "Inventario"), ("PURCHASING", "Compras"), ("RECEIVING", "Recepción"),
    ("PRODUCTION", "Producción"), ("LOGISTICS", "Logística"), ("FINANCE", "Finanzas"),
    ("CRM", "Clientes (CRM)"), ("BI", "Reportes (BI)"),
)


class _CapabilityGrid(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        self.boxes: dict[str, StandardCheckBox] = {}
        for i, (code, label) in enumerate(CAPABILITY_LABELS):
            box = StandardCheckBox(label, self)
            box.setAccessibleName(f"Capacidad {label}")
            grid.addWidget(box, i // 3, i % 3)
            self.boxes[code] = box

    def set_checked(self, codes) -> None:
        marcados = set(codes)
        for code, box in self.boxes.items():
            box.setChecked(code in marcados)

    def checked(self) -> list[str]:
        return [code for code, box in self.boxes.items() if box.isChecked()]


class OrgUnitDialog(FormDialog):
    """Alta (con tipo, superior y capacidades) o edición (nombre y código)."""

    def __init__(self, parent=None, *, type_options=(), parent_options=(),
                 suggested=None, unit=None) -> None:
        super().__init__(parent, title="Editar unidad" if unit else "Nueva unidad")
        self._suggested = dict(suggested or {})
        self._editing = unit is not None

        self.unit_type = SearchableComboBox(self, placeholder="Tipo de unidad…")
        self.unit_type.set_options(list(type_options))
        self.unit_type.setAccessibleName("Tipo de unidad")
        apply_tooltip(self.unit_type, "Sucursal, planta, centro de distribución, almacén, "
                      "oficina corporativa, operación logística o región (sólo agrupa).")
        self.form.addRow("Tipo:", self.unit_type)

        self.code = StandardLineEdit(self)
        self.code.setAccessibleName("Código")
        apply_tooltip(self.code, "Único en la empresa; 2 a 24 caracteres, se guarda en "
                      "mayúsculas.")
        self.form.addRow("Código:", self.code)

        self.name = StandardLineEdit(self)
        self.name.setAccessibleName("Nombre")
        self.form.addRow("Nombre:", self.name)

        self.parent_unit = SearchableComboBox(self, placeholder="(Sin unidad superior)")
        self.parent_unit.set_options([("", "(Sin unidad superior)"), *parent_options])
        self.parent_unit.setAccessibleName("Unidad superior")
        self.form.addRow("Depende de:", self.parent_unit)

        self.capabilities = _CapabilityGrid(self)
        apply_tooltip(self.capabilities, "Se proponen las del tipo; lo que rige es lo que "
                      "quede marcado aquí.")
        self.form.addRow("Capacidades:", self.capabilities)

        if self._editing:
            self.unit_type.set_current_id(unit.unit_type.value)
            self.unit_type.setEnabled(False)
            self.code.setText(unit.code)
            self.name.setText(unit.name)
            self.form.labelForField(self.parent_unit).setVisible(False)
            self.parent_unit.setVisible(False)
            self.form.labelForField(self.capabilities).setVisible(False)
            self.capabilities.setVisible(False)
        else:
            self.unit_type.selection_changed.connect(self._apply_suggestion)
        self.add_button_box(ok_text="Guardar" if self._editing else "Crear")

    def _apply_suggestion(self, unit_type) -> None:
        self.capabilities.set_checked(self._suggested.get(unit_type, ()))

    def values(self) -> dict:
        datos = {"name": self.name.text().strip(), "code": self.code.text().strip()}
        if not self._editing:
            datos.update(unit_type=self.unit_type.current_id(),
                         parent_id=self.parent_unit.current_id() or None,
                         capabilities=self.capabilities.checked())
        return datos


class NewBranchDialog(FormDialog):
    """«Nueva sucursal»: crea la sucursal operable (unidad, fila de `sucursales`
    y perfil, con el mismo código y nombre). Horario y tickets se completan
    después con «Editar sucursal»."""

    def __init__(self, parent=None, *, parent_options=()) -> None:
        super().__init__(parent, title="Nueva sucursal")
        self.code = StandardLineEdit(self)
        self.code.setAccessibleName("Código")
        apply_tooltip(self.code, "Prefijo de los folios de la sucursal; 2 a 24 caracteres, "
                      "se guarda en mayúsculas.")
        self.form.addRow("Código:", self.code)
        self.name = StandardLineEdit(self)
        self.name.setAccessibleName("Nombre")
        self.form.addRow("Nombre:", self.name)
        self.parent_unit = SearchableComboBox(self, placeholder="(Sin unidad superior)")
        self.parent_unit.set_options([("", "(Sin unidad superior)"), *parent_options])
        self.parent_unit.setAccessibleName("Unidad superior")
        self.form.addRow("Depende de:", self.parent_unit)
        self.add_button_box(ok_text="Crear sucursal")

    def values(self) -> dict:
        return {"code": self.code.text().strip(), "name": self.name.text().strip(),
                "parent_id": self.parent_unit.current_id() or None}


class MoveOrgUnitDialog(FormDialog):
    def __init__(self, parent=None, *, unit_name: str = "", parent_options=()) -> None:
        super().__init__(parent, title=f"Mover «{unit_name}»")
        self.parent_unit = SearchableComboBox(self, placeholder="(Sin unidad superior)")
        self.parent_unit.set_options([("", "(Sin unidad superior)"), *parent_options])
        self.parent_unit.setAccessibleName("Nueva unidad superior")
        self.form.addRow("Depende de:", self.parent_unit)
        self.add_button_box(ok_text="Mover")

    def values(self) -> dict:
        return {"parent_id": self.parent_unit.current_id() or None}


class OrgUnitCapabilitiesDialog(FormDialog):
    """Cambia capacidades; todo cambio lleva motivo (queda en la auditoría)."""

    def __init__(self, parent=None, *, unit_name: str = "", current=()) -> None:
        super().__init__(parent, title=f"Capacidades de «{unit_name}»")
        self._current = set(current)
        self.capabilities = _CapabilityGrid(self)
        self.capabilities.set_checked(self._current)
        self.form.addRow("Capacidades:", self.capabilities)
        self.reason = StandardLineEdit(self)
        self.reason.setAccessibleName("Motivo del cambio")
        self.form.addRow("Motivo:", self.reason)
        self.add_button_box(ok_text="Aplicar")

    def changes(self) -> list[tuple[str, bool]]:
        nuevas = set(self.capabilities.checked())
        # Altas primero y, en las bajas, POS antes que SALES/CASH (POS las exige):
        # el orden contrario fallaría aunque el conjunto final sea válido.
        altas = [(c, True) for c, _ in CAPABILITY_LABELS if c in nuevas - self._current]
        bajas = sorted((c for c, _ in CAPABILITY_LABELS if c in self._current - nuevas),
                       key=lambda c: c != "POS")
        return altas + [(c, False) for c in bajas]

    def values(self) -> dict:
        return {"changes": self.changes(), "reason": self.reason.text().strip()}


__all__ = ["CAPABILITY_LABELS", "MoveOrgUnitDialog", "NewBranchDialog",
           "OrgUnitCapabilitiesDialog", "OrgUnitDialog"]
