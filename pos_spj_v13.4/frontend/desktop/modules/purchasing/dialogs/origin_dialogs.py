"""Diálogos de «Compra en origen» (FASE 8-10). Sólo presentación: cada diálogo
arma un dict y quien lo abre lo manda al presentador; los campos que el producto
exige (peso, lote, caducidad, temperatura) se piden aquí y el backend los vuelve
a validar."""

from __future__ import annotations

from decimal import Decimal

from PyQt5.QtWidgets import QLabel

from frontend.desktop.components import (
    DateInput,
    DecimalInput,
    FormDialog,
    SearchableComboBox,
    StandardCheckBox,
    StandardLineEdit,
    StandardTextArea,
)
from frontend.desktop.themes.tokens import DialogMetrics

CONTAINER_CATEGORIES = [
    ("PLASTIC_BOX", "Caja de plástico"), ("CARDBOARD_BOX", "Caja de cartón"),
    ("CRATE", "Huacal"), ("PALLET", "Tarima"), ("CAGE", "Jaula"), ("COOLER", "Hielera"),
    ("TOTE", "Contenedor apilable"), ("TRAY", "Charola"), ("BAG", "Bolsa"),
    ("BIN", "Contenedor a granel"), ("TRAILER_CONTAINER", "Caja de tráiler"),
    ("MASTER_CONTAINER", "Contenedor maestro"),
]


def _banner(parent) -> QLabel:
    label = QLabel("", parent)
    label.setProperty("role", "banner")
    label.setProperty("state", "error")
    label.setWordWrap(True)
    label.hide()
    return label


class _OriginDialog(FormDialog):
    def __init__(self, parent=None, *, title: str) -> None:
        super().__init__(parent, title=title, width=DialogMetrics.WIDTH_LG)
        self._error = _banner(self)
        self._root.insertWidget(0, self._error)

    def error_text(self) -> str:
        return self._error.text()

    def show_error(self, text: str) -> None:
        self._error.setText(text)
        self._error.setVisible(bool(text))

    def problem(self) -> str | None:
        return None

    def accept(self) -> None:
        problem = self.problem()
        if problem:
            self.show_error(problem)
            return
        super().accept()


class OriginPickDialog(_OriginDialog):
    """De cuál bodega/punto de recolección del proveedor sale el embarque."""

    def __init__(self, parent=None, *, options) -> None:
        super().__init__(parent, title="Origen del embarque")
        self._origin = SearchableComboBox(placeholder="Bodega o punto de recolección")
        self._origin.set_options(list(options))
        self.form.addRow("Recoger en", self._origin)
        self.add_button_box(ok_text="Crear embarque")

    def problem(self) -> str | None:
        return None if self._origin.current_id() else "Elige la bodega o punto de recolección."

    def origin_id(self) -> str:
        return str(self._origin.current_id() or "")


class ContainerRegisterDialog(_OriginDialog):
    """Registrar un contenedor físico de la empresa; si ningún tipo sirve, se crea
    el tipo en el mismo paso."""

    def __init__(self, parent=None, *, type_options) -> None:
        super().__init__(parent, title="Registrar contenedor")
        self._code = StandardLineEdit(self)
        self._code.setPlaceholderText("Código impreso (ej. CJ-0001)")
        self._type = SearchableComboBox(placeholder="Tipo de contenedor")
        self._type.set_options(list(type_options))
        self._new_type = StandardCheckBox("Crear un tipo nuevo", self)
        self._type_name = StandardLineEdit(self)
        self._type_name.setPlaceholderText("Nombre del tipo (ej. Caja azul 20 kg)")
        self._category = SearchableComboBox(placeholder="Categoría")
        self._category.set_options(CONTAINER_CATEGORIES)
        self._allows_children = StandardCheckBox("Puede contener otros contenedores", self)
        self._max_weight = DecimalInput(self, precision=3, minimum="0", nullable=True)
        self._tare = DecimalInput(self, precision=3, minimum="0", nullable=True)
        self.form.addRow("Código", self._code)
        self.form.addRow("Tipo", self._type)
        self.form.addRow("", self._new_type)
        self.form.addRow("Nombre del tipo", self._type_name)
        self.form.addRow("Categoría", self._category)
        self.form.addRow("", self._allows_children)
        self.form.addRow("Peso neto máximo (kg)", self._max_weight)
        self.form.addRow("Tara (kg)", self._tare)
        self._new_type.toggled.connect(self._sync)
        if not type_options:
            self._new_type.setChecked(True)
        self._sync()
        self.add_button_box(ok_text="Registrar")

    def _sync(self) -> None:
        new = self._new_type.isChecked()
        self._type.setEnabled(not new)
        for widget in (self._type_name, self._category, self._allows_children,
                       self._max_weight):
            widget.setEnabled(new)

    def creates_type(self) -> bool:
        return self._new_type.isChecked()

    def problem(self) -> str | None:
        if not self._code.text().strip():
            return "Captura el código del contenedor."
        if self.creates_type():
            if not self._type_name.text().strip() or not self._category.current_id():
                return "Captura el nombre y la categoría del tipo nuevo."
        elif not self._type.current_id():
            return "Elige el tipo de contenedor."
        return None

    def type_values(self) -> dict:
        name = self._type_name.text().strip()
        return {"code": name.upper().replace(" ", "-")[:24], "name": name,
                "category": self._category.current_id(),
                "allows_children": self._allows_children.isChecked(),
                "maximum_net_weight": self._max_weight.decimal_value(),
                "tare_weight": self._tare.decimal_value() or "0"}

    def container_values(self, type_id: str | None = None) -> dict:
        return {"code": self._code.text().strip(),
                "container_type_id": type_id or self._type.current_id(),
                "tare_weight": self._tare.decimal_value()}


class _TraceFields:
    """Peso, lote, caducidad y temperatura — sólo se exigen si el producto lo pide."""

    def _build_trace(self, dialog, *, weight_label="Peso neto (kg)") -> None:
        self._weight = DecimalInput(dialog, precision=3, minimum="0", nullable=True)
        self._lot = StandardLineEdit(dialog)
        self._lot.setPlaceholderText("Lote del proveedor")
        self._has_expiration = StandardCheckBox("Capturar caducidad", dialog)
        self._expiration = DateInput(dialog)
        self._temperature = DecimalInput(dialog, precision=1, nullable=True)
        self._has_expiration.toggled.connect(self._expiration.setEnabled)
        dialog.form.addRow(weight_label, self._weight)
        dialog.form.addRow("Lote", self._lot)
        dialog.form.addRow("", self._has_expiration)
        dialog.form.addRow("Caducidad", self._expiration)
        dialog.form.addRow("Temperatura (°C)", self._temperature)

    def _apply_requirements(self, line: dict) -> None:
        self._has_expiration.setChecked(bool(line.get("expiration_required")))
        self._expiration.setEnabled(self._has_expiration.isChecked())
        self._weight.setPlaceholderText("Obligatorio" if line.get("weight_required") else "")
        self._lot.setPlaceholderText("Lote (obligatorio)" if line.get("lot_required")
                                     else "Lote del proveedor")
        self._temperature.setPlaceholderText("Obligatoria" if line.get("temperature_required")
                                             else "")

    def _trace_problem(self, line: dict, name: str, *, applies: bool = True) -> str | None:
        if not applies:
            return None
        if line.get("weight_required") and not (self._weight.decimal_value() or 0) > 0:
            return f"{name} requiere el peso neto."
        if line.get("lot_required") and not self._lot.text().strip():
            return f"{name} requiere lote."
        if line.get("expiration_required") and not self._has_expiration.isChecked():
            return f"{name} requiere caducidad."
        if line.get("temperature_required") and self._temperature.decimal_value() is None:
            return f"{name} requiere temperatura."
        return None

    def _trace_values(self) -> dict:
        return {"lot_number": self._lot.text().strip() or None,
                "expiration_date": (self._expiration.date_value().isoformat()
                                    if self._has_expiration.isChecked() else None),
                "temperature": (str(self._temperature.decimal_value())
                                if self._temperature.decimal_value() is not None else None)}


class LoadLineDialog(_OriginDialog, _TraceFields):
    """Cargar una línea de la compra en el contenedor seleccionado."""

    def __init__(self, parent=None, *, lines: list[dict], container_label: str) -> None:
        super().__init__(parent, title=f"Cargar en {container_label}")
        self._lines = {ln["source_line_id"]: ln for ln in lines}
        self._line = SearchableComboBox(placeholder="Producto de la compra")
        self._line.set_options([
            (ln["source_line_id"],
             f"{ln['product_name']} — pendiente {_plain(ln['pending'])} "
             f"{ln['purchase_unit']}".rstrip())
            for ln in lines])
        self._quantity = DecimalInput(self, precision=3, minimum="0")
        self.form.addRow("Producto", self._line)
        self.form.addRow("Cantidad cargada", self._quantity)
        self._build_trace(self)
        self._line.selection_changed.connect(lambda *_: self._line_changed())
        pending = [ln for ln in lines if ln["pending"] > 0]
        if len(pending) == 1:
            self._line.set_current_id(pending[0]["source_line_id"])
        self._line_changed()
        self.add_button_box(ok_text="Cargar")

    def _selected(self) -> dict:
        return self._lines.get(self._line.current_id() or "", {})

    def _line_changed(self) -> None:
        line = self._selected()
        if line:
            self._quantity.set_decimal(line["pending"] if line["pending"] > 0 else None)
        self._apply_requirements(line)

    def problem(self) -> str | None:
        line = self._selected()
        if not line:
            return "Elige el producto que se carga."
        if not (self._quantity.decimal_value() or 0) > 0:
            return "La cantidad cargada debe ser mayor a cero."
        return self._trace_problem(line, line["product_name"])

    def values(self) -> dict:
        return {"source_line_id": self._line.current_id(),
                "quantity": str(self._quantity.decimal_value()),
                "net_weight": str(self._weight.decimal_value() or "0"),
                **self._trace_values()}


class ArrivalCountDialog(_OriginDialog, _TraceFields):
    """Conteo/pesaje de un contenido al llegar: recibido, aceptado (lo demás es
    rechazo y NO entra al inventario), piezas y trazabilidad."""

    def __init__(self, parent=None, *, line: dict) -> None:
        super().__init__(parent, title=f"Conteo al llegar — {line['product_name']}")
        self._line_data = line
        declared = (f"{_plain(line['declared_quantity'])} {line.get('purchase_unit') or ''}"
                    f" · {_plain(line['declared_net_weight'])} kg · contenedor "
                    f"{line['container_code']}")
        self.form.addRow("Declarado en origen", QLabel(declared.strip(), self))
        self._received = DecimalInput(self, precision=3, minimum="0")
        self._accepted = DecimalInput(self, precision=3, minimum="0")
        self._pieces = DecimalInput(self, precision=0, minimum="0", nullable=True)
        self._notes = StandardTextArea(self)
        self._notes.setMaximumHeight(60)
        self.form.addRow("Recibido", self._received)
        self.form.addRow("Aceptado", self._accepted)
        self.form.addRow("Piezas", self._pieces)
        self._build_trace(self, weight_label="Peso real (kg)")
        self.form.addRow("Observaciones", self._notes)
        self._apply_requirements(line)
        received = line.get("received_quantity") or line["declared_quantity"]
        self._received.set_decimal(received)
        self._accepted.set_decimal(line.get("accepted_quantity") or received)
        self._weight.set_decimal(line.get("received_net_weight") or line["declared_net_weight"])
        if line.get("lot_number"):
            self._lot.setText(line["lot_number"])
        self.add_button_box(ok_text="Guardar conteo")

    def problem(self) -> str | None:
        received = self._received.decimal_value() or Decimal("0")
        accepted = self._accepted.decimal_value() or Decimal("0")
        if accepted > received:
            return "Lo aceptado no puede exceder lo recibido."
        return self._trace_problem(self._line_data, self._line_data["product_name"],
                                   applies=accepted > 0)

    def values(self) -> dict:
        pieces = self._pieces.decimal_value()
        return {"content_id": self._line_data["content_id"],
                "received_quantity": str(self._received.decimal_value() or "0"),
                "accepted_quantity": str(self._accepted.decimal_value() or "0"),
                "received_net_weight": str(self._weight.decimal_value() or "0"),
                "piece_count": int(pieces) if pieces is not None else None,
                "notes": self._notes.toPlainText().strip(), **self._trace_values()}


def _plain(value) -> str:
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except Exception:
        return str(value)
