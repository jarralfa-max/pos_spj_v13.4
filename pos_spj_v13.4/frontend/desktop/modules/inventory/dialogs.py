"""Inventory action dialogs (P0-B/P0-C/P0-D — Cuarentena, Ajustes, Conteos,
Almacenes, Ubicaciones).

Presentation-only: capture values for the corresponding use cases (open,
dispose, create, reverse, capturar, confirmar, activar, bloquear). No
business logic, no backend calls — the page reads the captured values and
hands them to the presenter after the dialog is accepted. Product selection
goes through the canonical search provider (§P0-D) — never a hand-typed UUID.
"""

from __future__ import annotations

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from frontend.desktop.components import (
    ColumnSpec,
    StandardTable,
    create_danger_button,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.cards import SectionCard
from frontend.desktop.components.date_input import DateInput
from frontend.desktop.components.decimal_input import DecimalInput
from frontend.desktop.components.dialogs import FormDialog
from frontend.desktop.components.entity_search_input import EntitySearchInput
from frontend.desktop.components.text_inputs import StandardLineEdit, StandardTextArea
from frontend.desktop.modules.inventory.view_models import (
    ADJUSTMENT_REASON_ES,
    COUNT_TYPE_ES,
    LOT_ORIGIN_ES,
    LOT_QUALITY_ES,
    QUARANTINE_REASON_ES,
    RESERVATION_SOURCE_ES,
    TEMPERATURE_POINT_ES,
    WAREHOUSE_TYPE_ES,
    WAREHOUSE_ZONE_TYPE_ES,
    lot_origin_es,
    lot_quality_es,
    movement_status_es,
    movement_type_es,
)


class DisposeQuarantineDialog(FormDialog):
    """Motivo de disposición (baja definitiva) de una cuarentena — auditado."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Disponer cuarentena")
        self.reason_input = StandardTextArea(self, placeholder="Motivo de la disposición…")
        self.reason_input.setMaximumHeight(90)
        self.form.addRow("Motivo:", self.reason_input)
        self.add_button_box(ok_text="Disponer")

    def reason(self) -> str:
        return self.reason_input.value()


class OpenQuarantineDialog(FormDialog):
    """Poner stock en cuarentena: producto (búsqueda canónica), motivo,
    ubicación real (opcional — lista acotada del almacén, §P0-04 corolario) y
    cantidad."""

    def __init__(self, parent=None, *, product_provider, location_options=None) -> None:
        super().__init__(parent, title="Nueva cuarentena")
        self.product = EntitySearchInput(
            self, provider=product_provider,
            placeholder="Buscar producto por nombre, código o código de barras…")
        self.reason_combo = QComboBox(self)
        for code, label in QUARANTINE_REASON_ES.items():
            self.reason_combo.addItem(label, code)
        self.location_combo = QComboBox(self)
        self.location_combo.addItem("Automática (todo el almacén)", "")
        for option in (location_options or []):
            self.location_combo.addItem(option.label, option.id)
        self.quantity = DecimalInput(self, precision=3, minimum="0.001")
        self.note_input = StandardTextArea(self, placeholder="Nota (opcional)…")
        self.note_input.setMaximumHeight(70)
        self.form.addRow("Producto:", self.product)
        self.form.addRow("Motivo:", self.reason_combo)
        self.form.addRow("Ubicación:", self.location_combo)
        self.form.addRow("Cantidad:", self.quantity)
        self.form.addRow("Nota:", self.note_input)
        self.add_button_box(ok_text="Poner en cuarentena")

    def product_id(self) -> str | None:
        return self.product.selected_id()

    def reason_code(self) -> str:
        return str(self.reason_combo.currentData() or "")

    def location_id(self) -> str | None:
        return str(self.location_combo.currentData() or "") or None

    def quantity_value(self):
        return self.quantity.decimal_value()

    def note(self) -> str:
        return self.note_input.value()


class CreateAdjustmentDialog(FormDialog):
    """Nuevo ajuste de una sola línea: producto (búsqueda canónica), motivo,
    dirección (entrada/salida) y magnitud — el signo se arma aquí, el usuario
    nunca teclea un menos."""

    def __init__(self, parent=None, *, product_provider) -> None:
        super().__init__(parent, title="Nuevo ajuste")
        self.product = EntitySearchInput(
            self, provider=product_provider,
            placeholder="Buscar producto por nombre, código o código de barras…")
        self.reason_combo = QComboBox(self)
        for code, label in ADJUSTMENT_REASON_ES.items():
            self.reason_combo.addItem(label, code)
        self.direction_combo = QComboBox(self)
        self.direction_combo.addItem("Entrada (+)", "in")
        self.direction_combo.addItem("Salida (-)", "out")
        self.quantity = DecimalInput(self, precision=3, minimum="0.001")
        self.note_input = StandardTextArea(self, placeholder="Nota (opcional)…")
        self.note_input.setMaximumHeight(70)
        self.form.addRow("Producto:", self.product)
        self.form.addRow("Motivo:", self.reason_combo)
        self.form.addRow("Dirección:", self.direction_combo)
        self.form.addRow("Cantidad:", self.quantity)
        self.form.addRow("Nota:", self.note_input)
        self.add_button_box(ok_text="Crear ajuste")

    def product_id(self) -> str | None:
        return self.product.selected_id()

    def reason_code(self) -> str:
        return str(self.reason_combo.currentData() or "")

    def quantity_delta(self):
        magnitude = self.quantity.decimal_value()
        if magnitude is None:
            return None
        return -magnitude if self.direction_combo.currentData() == "out" else magnitude

    def note(self) -> str:
        return self.note_input.value()


class ReverseAdjustmentDialog(FormDialog):
    """Motivo de reverso de un ajuste posteado — auditado, irreversible."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Reversar ajuste")
        self.reason_input = StandardTextArea(self, placeholder="Motivo del reverso…")
        self.reason_input.setMaximumHeight(90)
        self.form.addRow("Motivo:", self.reason_input)
        self.add_button_box(ok_text="Reversar")

    def reason(self) -> str:
        return self.reason_input.value()


class CreateCountDialog(FormDialog):
    """Nuevo conteo de una sola línea (§27): producto (búsqueda canónica),
    tipo de conteo y modalidad (a ciegas por defecto — no se muestra la
    cantidad esperada durante la captura)."""

    def __init__(self, parent=None, *, product_provider) -> None:
        super().__init__(parent, title="Nuevo conteo")
        self.product = EntitySearchInput(
            self, provider=product_provider,
            placeholder="Buscar producto por nombre, código o código de barras…")
        self.type_combo = QComboBox(self)
        for code, label in COUNT_TYPE_ES.items():
            self.type_combo.addItem(label, code)
        self.blind_check = QCheckBox("Conteo a ciegas (no muestra la cantidad esperada)", self)
        self.blind_check.setChecked(True)
        self.form.addRow("Producto:", self.product)
        self.form.addRow("Tipo:", self.type_combo)
        self.form.addRow("", self.blind_check)
        self.add_button_box(ok_text="Iniciar conteo")

    def product_id(self) -> str | None:
        return self.product.selected_id()

    def count_type_code(self) -> str:
        return str(self.type_combo.currentData() or "")

    def blind(self) -> bool:
        return self.blind_check.isChecked()


class RecordCountDialog(FormDialog):
    """Captura la cantidad contada de la línea (§27) — sin exponer la
    cantidad esperada cuando el conteo es a ciegas."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Capturar conteo")
        self.quantity = DecimalInput(self, precision=3, minimum="0")
        self.form.addRow("Cantidad contada:", self.quantity)
        self.add_button_box(ok_text="Capturar")

    def counted_quantity(self):
        return self.quantity.decimal_value()


class CreateWarehouseDialog(FormDialog):
    """Alta de almacén (§12): código, nombre, tipo, perfil de temperatura y
    capacidad (opcionales). Sin ubicaciones técnicas aquí — eso lo hace el
    aprovisionamiento automático (§20, ver ``EnsureTechnicalLocationsUseCase``)
    tras crear el almacén; esta alta manual es para almacenes adicionales con
    nombre propio."""

    def __init__(self, parent=None, *, title: str = "Nuevo almacén",
                 ok_text: str = "Crear almacén") -> None:
        super().__init__(parent, title=title)
        self.code_input = StandardLineEdit(self, placeholder="Código (p.ej. WH-002)")
        self.name_input = StandardLineEdit(self, placeholder="Nombre")
        self.type_combo = QComboBox(self)
        for code, label in WAREHOUSE_TYPE_ES.items():
            self.type_combo.addItem(label, code)
        self.temperature_input = StandardLineEdit(
            self, placeholder="Perfil de temperatura (opcional, p.ej. REFRIGERADO 0-4°C)")
        self.capacity_input = DecimalInput(self, precision=3, minimum="0", nullable=True)
        self.capacity_uom_input = StandardLineEdit(
            self, placeholder="Unidad (p.ej. m3, kg, tarimas)")
        self.form.addRow("Código:", self.code_input)
        self.form.addRow("Nombre:", self.name_input)
        self.form.addRow("Tipo:", self.type_combo)
        self.form.addRow("Perfil de temperatura:", self.temperature_input)
        self.form.addRow("Capacidad:", self.capacity_input)
        self.form.addRow("Unidad de capacidad:", self.capacity_uom_input)
        self.add_button_box(ok_text=ok_text)

    def code(self) -> str:
        return self.code_input.value()

    def name(self) -> str:
        return self.name_input.value()

    def warehouse_type(self) -> str:
        return str(self.type_combo.currentData() or "")

    def temperature_profile(self) -> str:
        return self.temperature_input.value()

    def capacity(self):
        return self.capacity_input.decimal_value()

    def capacity_uom(self) -> str:
        return self.capacity_uom_input.value()

    def set_warehouse_type(self, code: str) -> None:
        idx = self.type_combo.findData(str(code or ""))
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)


class EditWarehouseDialog(CreateWarehouseDialog):
    """Edita un almacén existente (§24 "Editar almacén"): mismos campos que el
    alta, prellenados, salvo el código (identidad estable, no editable)."""

    def __init__(self, parent=None, *, warehouse: dict) -> None:
        super().__init__(parent, title="Editar almacén", ok_text="Guardar cambios")
        self.code_input.setText(str(warehouse.get("code") or ""))
        self.code_input.setReadOnly(True)
        self.name_input.setText(str(warehouse.get("name") or ""))
        self.set_warehouse_type(warehouse.get("warehouse_type"))
        self.temperature_input.setText(str(warehouse.get("temperature_profile") or ""))
        self.capacity_input.set_decimal(warehouse.get("capacity"))
        self.capacity_uom_input.setText(str(warehouse.get("capacity_uom") or ""))


class CreateZoneDialog(FormDialog):
    """Alta de zona (§24 "Zonas"): código, nombre y tipo funcional dentro del
    almacén (recepción, surtido, frío, cuarentena, …)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nueva zona")
        self.code_input = StandardLineEdit(self, placeholder="Código (p.ej. Z-FRIO)")
        self.name_input = StandardLineEdit(self, placeholder="Nombre")
        self.type_combo = QComboBox(self)
        for code, label in WAREHOUSE_ZONE_TYPE_ES.items():
            self.type_combo.addItem(label, code)
        self.form.addRow("Código:", self.code_input)
        self.form.addRow("Nombre:", self.name_input)
        self.form.addRow("Tipo:", self.type_combo)
        self.add_button_box(ok_text="Crear zona")

    def code(self) -> str:
        return self.code_input.value()

    def name(self) -> str:
        return self.name_input.value()

    def zone_type(self) -> str:
        return str(self.type_combo.currentData() or "")


class CreateLocationDialog(FormDialog):
    """Alta de ubicación (§12): código, nombre, nivel y capacidad (opcional).
    ``parent_label`` — si se abrió desde el menú contextual de una ubicación
    existente — deja claro que se está creando una sub-ubicación, no una raíz
    nueva."""

    def __init__(self, parent=None, *, parent_label: str | None = None,
                 title: str | None = None, ok_text: str = "Crear ubicación") -> None:
        if title is None:
            title = (f"Nueva sub-ubicación de «{parent_label}»" if parent_label
                     else "Nueva ubicación")
        super().__init__(parent, title=title)
        self.code_input = StandardLineEdit(self, placeholder="Código (p.ej. A1)")
        self.name_input = StandardLineEdit(self, placeholder="Nombre")
        self.level_spin = QSpinBox(self)
        self.level_spin.setRange(0, 10)
        self.capacity_input = DecimalInput(self, precision=3, minimum="0", nullable=True)
        self.form.addRow("Código:", self.code_input)
        self.form.addRow("Nombre:", self.name_input)
        self.form.addRow("Nivel:", self.level_spin)
        self.form.addRow("Capacidad:", self.capacity_input)
        self.add_button_box(ok_text=ok_text)

    def code(self) -> str:
        return self.code_input.value()

    def name(self) -> str:
        return self.name_input.value()

    def level(self) -> int:
        return self.level_spin.value()

    def capacity(self):
        return self.capacity_input.decimal_value()


class EditLocationDialog(FormDialog):
    """Edita una ubicación existente (§24 "Editar ubicación"): nombre y
    capacidad — el código y la jerarquía son identidad estable, no editables
    aquí."""

    def __init__(self, parent=None, *, location: dict) -> None:
        super().__init__(parent, title="Editar ubicación")
        self.code_input = StandardLineEdit(self)
        self.code_input.setText(str(location.get("code") or ""))
        self.code_input.setReadOnly(True)
        self.name_input = StandardLineEdit(self, placeholder="Nombre")
        self.name_input.setText(str(location.get("name") or ""))
        self.capacity_input = DecimalInput(self, precision=3, minimum="0", nullable=True)
        self.capacity_input.set_decimal(location.get("capacity"))
        self.form.addRow("Código:", self.code_input)
        self.form.addRow("Nombre:", self.name_input)
        self.form.addRow("Capacidad:", self.capacity_input)
        self.add_button_box(ok_text="Guardar cambios")

    def name(self) -> str:
        return self.name_input.value()

    def capacity(self):
        return self.capacity_input.decimal_value()


class BlockReasonDialog(FormDialog):
    """Motivo de bloqueo — reutilizado por Almacenes, Ubicaciones e
    Inspección: todos bloquean/rechazan por el mismo tipo de razón operativa
    (mantenimiento, cierre, incidente, falla de calidad) y no ameritan
    varias clases casi idénticas."""

    def __init__(self, parent=None, *, title: str = "Bloquear",
                 ok_text: str = "Bloquear") -> None:
        super().__init__(parent, title=title)
        self.reason_input = StandardTextArea(self, placeholder="Motivo…")
        self.reason_input.setMaximumHeight(90)
        self.form.addRow("Motivo:", self.reason_input)
        self.add_button_box(ok_text=ok_text)

    def reason(self) -> str:
        return self.reason_input.value()


class ManageZonesDialog(QDialog):
    """Zonas del almacén seleccionado + alta de zona nueva (§24 "Zonas").

    Presentation-only like the rest of this module: receives the already
    resolved rows (a ``TableViewModel``) and a ``create_zone`` callback the
    page wires to the presenter — no backend access here directly."""

    def __init__(self, parent=None, *, warehouse_label: str, table,
                 create_zone) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Zonas — {warehouse_label}")
        self.resize(480, 360)
        self._create_zone = create_zone

        layout = QVBoxLayout(self)
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.create_button = create_primary_button(text="Nueva zona")
        self.create_button.clicked.connect(self._on_create)
        actions.addWidget(self.create_button)
        layout.addLayout(actions)

        self._table = StandardTable(columns=[
            ColumnSpec("Código", "text"),
            ColumnSpec("Nombre", "text"),
            ColumnSpec("Tipo", "text"),
        ])
        self.set_rows(table)
        layout.addWidget(self._table)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_button = create_secondary_button(text="Cerrar")
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)

    def set_rows(self, table) -> None:
        self._table.load_rows(table.rows, row_ids=table.row_ids)

    def _on_create(self) -> None:
        dlg = CreateZoneDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        code, name = dlg.code(), dlg.name()
        if code and name:
            self._create_zone(code=code, name=name, zone_type=dlg.zone_type())


class ReverseReasonDialog(FormDialog):
    """Motivo de reverso — capturado antes de reversar cualquier movimiento
    posteado (§6). Mismo patrón que ``BlockReasonDialog``/``ReverseAdjustmentDialog``:
    una razón obligatoria, auditada, para una acción irreversible."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Reversar movimiento")
        self.reason_input = StandardTextArea(self, placeholder="Motivo del reverso…")
        self.reason_input.setMaximumHeight(90)
        self.form.addRow("Motivo:", self.reason_input)
        self.add_button_box(ok_text="Reversar")

    def reason(self) -> str:
        return self.reason_input.value()


class MovementDetailDialog(QDialog):
    """Detalle de un movimiento del ledger (§6 detalle/líneas/documento
    origen/auditoría/reverso).

    Presentation-only like the rest of this module: receives the already
    resolved header dict + three ``TableViewModel``s (lines, source-document
    siblings, audit trail) plus a ``reverse`` callback the page wires to the
    presenter. ``can_reverse`` is the caller's resolved capability — hiding
    the button is UX, the backend re-validates independently."""

    def __init__(self, parent=None, *, header: dict, lines, source_document,
                 audit, can_reverse: bool, reverse) -> None:
        super().__init__(parent)
        self.setWindowTitle("Detalle del movimiento")
        self.resize(640, 640)
        self._reverse = reverse

        layout = QVBoxLayout(self)

        info = SectionCard(self, title="Encabezado")
        form = QFormLayout()
        form.addRow("Tipo:", QLabel(movement_type_es(header.get("movement_type"))))
        form.addRow("Estado:", QLabel(movement_status_es(header.get("status"))))
        form.addRow("Fecha:", QLabel(str(header.get("occurred_at") or "—")[:19]))
        form.addRow("Módulo origen:", QLabel(str(header.get("source_module") or "—")))
        doc = (f"{header.get('source_document_type') or ''} "
               f"{header.get('source_document_id') or ''}").strip() or "—"
        form.addRow("Documento origen:", QLabel(doc))
        form.addRow("Creado por:", QLabel(str(header.get("created_by_user_id") or "—")))
        if header.get("authorized_by_user_id"):
            form.addRow("Autorizado por:", QLabel(str(header["authorized_by_user_id"])))
        if header.get("reversal_of_id"):
            form.addRow("Reverso de:", QLabel(str(header["reversal_of_id"])))
        info.add(_wrap(form))
        layout.addWidget(info)

        lines_card = SectionCard(self, title="Líneas")
        self._lines_table = StandardTable(columns=[
            ColumnSpec("Producto", "text"),
            ColumnSpec("Lote", "text"),
            ColumnSpec("Cantidad", "text"),
            ColumnSpec("Origen", "text"),
            ColumnSpec("Destino", "text"),
            ColumnSpec("Costo unitario", "text"),
        ])
        self._lines_table.load_rows(lines.rows, row_ids=lines.row_ids)
        lines_card.add(self._lines_table)
        layout.addWidget(lines_card)

        doc_card = SectionCard(self, title="Documento origen")
        self._doc_table = StandardTable(columns=[
            ColumnSpec("Fecha", "text"), ColumnSpec("Tipo", "text"),
            ColumnSpec("Módulo", "text"), ColumnSpec("Documento", "text"),
            ColumnSpec("Estado", "status"),
        ])
        self._doc_table.load_rows(source_document.rows, row_ids=source_document.row_ids)
        doc_card.add(self._doc_table)
        layout.addWidget(doc_card)

        audit_card = SectionCard(self, title="Auditoría")
        self._audit_table = StandardTable(columns=[
            ColumnSpec("Fecha", "text"), ColumnSpec("Entidad", "text"),
            ColumnSpec("Acción", "text"), ColumnSpec("Usuario", "text"),
            ColumnSpec("Autorizó", "text"),
        ])
        self._audit_table.load_rows(audit.rows, row_ids=audit.row_ids)
        audit_card.add(self._audit_table)
        layout.addWidget(audit_card)

        actions = QHBoxLayout()
        actions.addStretch(1)
        already_reversed = str(header.get("status") or "") == "REVERSED"
        self.reverse_button = create_danger_button(text="Reversar")
        self.reverse_button.setVisible(can_reverse)
        self.reverse_button.setEnabled(not already_reversed)
        self.reverse_button.clicked.connect(self._on_reverse)
        actions.addWidget(self.reverse_button)
        close_button = create_secondary_button(text="Cerrar")
        close_button.clicked.connect(self.accept)
        actions.addWidget(close_button)
        layout.addLayout(actions)

    def set_audit_rows(self, table) -> None:
        self._audit_table.load_rows(table.rows, row_ids=table.row_ids)

    def _on_reverse(self) -> None:
        dlg = ReverseReasonDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        reason = dlg.reason()
        if reason:
            self._reverse(reason)


class CreateLotDialog(FormDialog):
    """Alta de lote (§26 "Registrar lote"): código, origen y las fechas/
    referencias que se conocen al recibirlo. El producto ya está elegido por
    la página (no se vuelve a pedir aquí — ya se está viendo sus lotes)."""

    def __init__(self, parent=None, *, title: str = "Nuevo lote",
                 ok_text: str = "Registrar lote") -> None:
        super().__init__(parent, title=title)
        self.code_input = StandardLineEdit(self, placeholder="Código de lote")
        self.origin_combo = QComboBox(self)
        for code, label in LOT_ORIGIN_ES.items():
            self.origin_combo.addItem(label, code)
        self.supplier_code_input = StandardLineEdit(
            self, placeholder="Código de lote del proveedor (opcional)")
        self.production_code_input = StandardLineEdit(
            self, placeholder="Código de lote de producción (opcional)")
        self.origin_document_input = StandardLineEdit(
            self, placeholder="Documento origen (opcional)")
        self.has_production_date = QCheckBox("Captura fecha de producción", self)
        self.production_date_input = DateInput(self)
        self.production_date_input.setEnabled(False)
        self.has_production_date.toggled.connect(self.production_date_input.setEnabled)
        self.has_expiration_date = QCheckBox("Captura fecha de caducidad", self)
        self.has_expiration_date.setChecked(True)
        self.expiration_date_input = DateInput(self)
        self.has_expiration_date.toggled.connect(self.expiration_date_input.setEnabled)
        self.form.addRow("Código:", self.code_input)
        self.form.addRow("Origen:", self.origin_combo)
        self.form.addRow("Lote proveedor:", self.supplier_code_input)
        self.form.addRow("Lote producción:", self.production_code_input)
        self.form.addRow("Documento origen:", self.origin_document_input)
        self.form.addRow("", self.has_production_date)
        self.form.addRow("Fecha de producción:", self.production_date_input)
        self.form.addRow("", self.has_expiration_date)
        self.form.addRow("Fecha de caducidad:", self.expiration_date_input)
        self.add_button_box(ok_text=ok_text)

    def lot_code(self) -> str:
        return self.code_input.value()

    def origin_type(self) -> str:
        return str(self.origin_combo.currentData() or "")

    def supplier_lot_code(self) -> str:
        return self.supplier_code_input.value()

    def production_lot_code(self) -> str:
        return self.production_code_input.value()

    def origin_document_id(self) -> str:
        return self.origin_document_input.value()

    def production_date(self) -> str:
        if not self.has_production_date.isChecked():
            return ""
        return self.production_date_input.date_value().isoformat()

    def expiration_date(self) -> str:
        if not self.has_expiration_date.isChecked():
            return ""
        return self.expiration_date_input.date_value().isoformat()


class EditLotDialog(FormDialog):
    """Edita los datos permitidos de un lote (§26 "Editar datos permitidos") —
    no el código, el producto, el origen ni el estado de calidad."""

    def __init__(self, parent=None, *, lot: dict) -> None:
        super().__init__(parent, title=f"Editar lote {lot.get('lot_code') or ''}")
        self.supplier_code_input = StandardLineEdit(self)
        self.supplier_code_input.setText(str(lot.get("supplier_lot_code") or ""))
        self.production_code_input = StandardLineEdit(self)
        self.production_code_input.setText(str(lot.get("production_lot_code") or ""))
        self.origin_document_input = StandardLineEdit(self)
        self.origin_document_input.setText(str(lot.get("origin_document_id") or ""))
        self.has_expiration_date = QCheckBox("Tiene fecha de caducidad", self)
        self.expiration_date_input = DateInput(self)
        existing_expiration = lot.get("expiration_date")
        if existing_expiration:
            from datetime import date as _date
            self.has_expiration_date.setChecked(True)
            self.expiration_date_input.set_date_value(
                _date.fromisoformat(str(existing_expiration)[:10]))
        else:
            self.has_expiration_date.setChecked(False)
            self.expiration_date_input.setEnabled(False)
        self.has_expiration_date.toggled.connect(self.expiration_date_input.setEnabled)
        self.form.addRow("Lote proveedor:", self.supplier_code_input)
        self.form.addRow("Lote producción:", self.production_code_input)
        self.form.addRow("Documento origen:", self.origin_document_input)
        self.form.addRow("", self.has_expiration_date)
        self.form.addRow("Fecha de caducidad:", self.expiration_date_input)
        self.add_button_box(ok_text="Guardar cambios")

    def supplier_lot_code(self) -> str:
        return self.supplier_code_input.value()

    def production_lot_code(self) -> str:
        return self.production_code_input.value()

    def origin_document_id(self) -> str:
        return self.origin_document_input.value()

    def expiration_date(self) -> str:
        if not self.has_expiration_date.isChecked():
            return ""
        return self.expiration_date_input.date_value().isoformat()


class LotQualityStatusDialog(FormDialog):
    """Un único diálogo para las tres acciones de calidad del lote (§26/§31):
    liberar, bloquear o enviar a cuarentena — mismo caso de uso
    (``SetLotQualityStatusUseCase``), el estado destino es el diferenciador."""

    _TARGETS = ("RELEASED", "BLOCKED", "QUARANTINED")

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Cambiar estado de calidad del lote")
        self.status_combo = QComboBox(self)
        for code in self._TARGETS:
            self.status_combo.addItem(lot_quality_es(code), code)
        self.reason_input = StandardTextArea(self, placeholder="Motivo…")
        self.reason_input.setMaximumHeight(90)
        self.form.addRow("Nuevo estado:", self.status_combo)
        self.form.addRow("Motivo:", self.reason_input)
        self.add_button_box(ok_text="Aplicar")

    def new_status(self) -> str:
        return str(self.status_combo.currentData() or "")

    def reason(self) -> str:
        return self.reason_input.value()


class LotDetailDialog(QDialog):
    """Detalle de un lote (§26 detalle/stock/movimientos/trazabilidad) +
    acciones (editar, cambiar estado de calidad, imprimir etiqueta).

    Presentation-only like ``MovementDetailDialog``: receives the already
    resolved header dict + three ``TableViewModel``s (stock, movements,
    traceability) plus callbacks the page wires to the presenter."""

    def __init__(self, parent=None, *, header: dict, stock, movements, traceability,
                 can_edit: bool, can_change_status: bool, can_print: bool,
                 can_reprint: bool, edit, change_status, print_label) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Lote {header.get('lot_code') or ''}")
        self.resize(640, 640)
        self._edit = edit
        self._change_status = change_status
        self._print_label = print_label

        layout = QVBoxLayout(self)

        info = SectionCard(self, title="Encabezado")
        form = QFormLayout()
        form.addRow("Código:", QLabel(str(header.get("lot_code") or "—")))
        form.addRow("Origen:", QLabel(lot_origin_es(header.get("origin_type"))))
        form.addRow("Calidad:", QLabel(lot_quality_es(header.get("quality_status"))))
        form.addRow("Lote proveedor:", QLabel(str(header.get("supplier_lot_code") or "—")))
        form.addRow("Lote producción:", QLabel(str(header.get("production_lot_code") or "—")))
        form.addRow("Documento origen:", QLabel(str(header.get("origin_document_id") or "—")))
        form.addRow("Fecha de producción:", QLabel(str(header.get("production_date") or "—")))
        form.addRow("Fecha de caducidad:", QLabel(str(header.get("expiration_date") or "—")))
        form.addRow("Recibido:", QLabel(str(header.get("received_at") or "—")[:19]))
        info.add(_wrap(form))
        layout.addWidget(info)

        stock_card = SectionCard(self, title="Existencias")
        self._stock_table = StandardTable(columns=[
            ColumnSpec("Producto", "text"), ColumnSpec("Almacén", "text"),
            ColumnSpec("Estado", "status"), ColumnSpec("Cantidad", "text"),
            ColumnSpec("Reservado", "text"),
        ])
        self._stock_table.load_rows(stock.rows, row_ids=stock.row_ids)
        stock_card.add(self._stock_table)
        layout.addWidget(stock_card)

        movements_card = SectionCard(self, title="Movimientos")
        self._movements_table = StandardTable(columns=[
            ColumnSpec("Fecha", "text"), ColumnSpec("Tipo", "text"),
            ColumnSpec("Módulo", "text"), ColumnSpec("Documento", "text"),
            ColumnSpec("Estado", "status"),
        ])
        self._movements_table.load_rows(movements.rows, row_ids=movements.row_ids)
        movements_card.add(self._movements_table)
        layout.addWidget(movements_card)

        trace_card = SectionCard(self, title="Trazabilidad")
        self._trace_table = StandardTable(columns=[
            ColumnSpec("Fecha", "text"), ColumnSpec("Movimiento", "text"),
            ColumnSpec("Dirección", "text"), ColumnSpec("Módulo", "text"),
            ColumnSpec("Documento", "text"),
        ])
        self._trace_table.load_rows(traceability.rows, row_ids=traceability.row_ids)
        trace_card.add(self._trace_table)
        layout.addWidget(trace_card)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.edit_button = create_secondary_button(text="Editar")
        self.edit_button.setVisible(can_edit)
        self.edit_button.clicked.connect(self._on_edit)
        actions.addWidget(self.edit_button)
        self.status_button = create_secondary_button(text="Cambiar estado de calidad")
        self.status_button.setVisible(can_change_status)
        self.status_button.clicked.connect(self._on_change_status)
        actions.addWidget(self.status_button)
        self.print_button = create_secondary_button(text="Imprimir etiqueta")
        self.print_button.setVisible(can_print)
        self.print_button.clicked.connect(lambda: self._print_label(False))
        actions.addWidget(self.print_button)
        self.reprint_button = create_secondary_button(text="Reimprimir")
        self.reprint_button.setVisible(can_reprint)
        self.reprint_button.clicked.connect(lambda: self._print_label(True))
        actions.addWidget(self.reprint_button)
        close_button = create_secondary_button(text="Cerrar")
        close_button.clicked.connect(self.accept)
        actions.addWidget(close_button)
        layout.addLayout(actions)

    def _on_edit(self) -> None:
        self._edit()

    def _on_change_status(self) -> None:
        dlg = LotQualityStatusDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return
        reason = dlg.reason()
        if reason:
            self._change_status(dlg.new_status(), reason)


class CaptureWeightDialog(FormDialog):
    """Captura de peso variable (§18/§28-29): producto, ubicación, piezas
    reconciliadas y la lectura de peso — de báscula ("Leer báscula", vista
    previa contra el gateway cableado vía el callback de la página) o manual
    (bruto/tara/unidad). El campo "Autorizador" sólo se necesita cuando la
    captura manual queda fuera del rango permitido — el use case exige esa
    autorización aguas abajo; el mensaje de error lo indica si falta.

    "Leer báscula" es sólo una vista previa: la lectura autoritativa (la que
    se valida y postea) se vuelve a tomar del gateway al confirmar — igual
    que con hardware real, donde el peso puede cambiar entre la vista previa
    y la confirmación."""

    def __init__(self, parent=None, *, product_provider, location_options=None,
                 read_scale=None) -> None:
        super().__init__(parent, title="Capturar peso")
        self._read_scale = read_scale
        self._scale_reading: dict | None = None

        self.product = EntitySearchInput(
            self, provider=product_provider,
            placeholder="Buscar producto por nombre, código o código de barras…")
        self.location_combo = QComboBox(self)
        self.location_combo.addItem("Automática (todo el almacén)", "")
        for option in (location_options or []):
            self.location_combo.addItem(option.label, option.id)

        self.direction_combo = QComboBox(self)
        self.direction_combo.addItem("Entrada (+)", "in")
        self.direction_combo.addItem("Salida (-)", "out")
        self.pieces_input = DecimalInput(self, precision=3, minimum="0", nullable=True)

        scale_row = QHBoxLayout()
        self.scale_button = create_secondary_button(text="Leer báscula")
        self.scale_button.clicked.connect(self._on_read_scale)
        scale_row.addWidget(self.scale_button)
        self.scale_status = QLabel("Sin lectura de báscula.", self)
        scale_row.addWidget(self.scale_status, 1)
        scale_wrap = QWidget(self)
        scale_wrap.setLayout(scale_row)

        self.gross_input = DecimalInput(self, precision=3, minimum="0", nullable=True)
        self.tare_input = DecimalInput(self, precision=3, minimum="0")
        self.tare_input.set_decimal(0)
        self.unit_combo = QComboBox(self)
        for code in ("KG", "LB", "G"):
            self.unit_combo.addItem(code, code)

        self.authorizer_input = StandardLineEdit(
            self, placeholder="Autorizador (sólo si el peso queda fuera de rango)")
        self.note_input = StandardTextArea(self, placeholder="Nota (opcional)…")
        self.note_input.setMaximumHeight(70)

        self.form.addRow("Producto:", self.product)
        self.form.addRow("Ubicación:", self.location_combo)
        self.form.addRow("Dirección piezas:", self.direction_combo)
        self.form.addRow("Piezas:", self.pieces_input)
        self.form.addRow("Báscula:", scale_wrap)
        self.form.addRow("Peso bruto (manual):", self.gross_input)
        self.form.addRow("Tara:", self.tare_input)
        self.form.addRow("Unidad:", self.unit_combo)
        self.form.addRow("Autorizador:", self.authorizer_input)
        self.form.addRow("Nota:", self.note_input)
        self.add_button_box(ok_text="Capturar peso")

    def _on_read_scale(self) -> None:
        reading = self._read_scale() if self._read_scale else None
        if reading is None:
            self._scale_reading = None
            self.scale_status.setText("Sin lectura disponible; capture manualmente.")
            return
        self._scale_reading = reading
        stability = "estable" if reading.get("stable") else "inestable"
        self.scale_status.setText(
            f"Neto {reading.get('net')} {reading.get('unit')} ({stability})")

    def product_id(self) -> str | None:
        return self.product.selected_id()

    def location_id(self) -> str | None:
        return str(self.location_combo.currentData() or "") or None

    def pieces_delta(self):
        magnitude = self.pieces_input.decimal_value() or 0
        return -magnitude if self.direction_combo.currentData() == "out" else magnitude

    def use_scale(self) -> bool:
        return self._scale_reading is not None

    def gross(self):
        return self.gross_input.decimal_value()

    def tare(self):
        return self.tare_input.decimal_value() or 0

    def unit(self) -> str:
        return str(self.unit_combo.currentData() or "KG")

    def authorizer_user_id(self) -> str:
        return self.authorizer_input.value()

    def note(self) -> str:
        return self.note_input.value()


class WeightHistoryDialog(QDialog):
    """Historial de capturas de peso (§28 "Ver historial"): ajustes con
    motivo ``WEIGHT_VARIANCE``, más recientes primero. Sólo lectura — el
    mismo patrón de ``ManageZonesDialog`` sin la acción de alta."""

    def __init__(self, parent=None, *, table) -> None:
        super().__init__(parent)
        self.setWindowTitle("Historial de capturas de peso")
        self.resize(520, 360)

        layout = QVBoxLayout(self)
        self._table = StandardTable(columns=[
            ColumnSpec("Folio", "text"),
            ColumnSpec("Motivo", "text"),
            ColumnSpec("Almacén", "text"),
            ColumnSpec("Estado", "status"),
            ColumnSpec("Creado", "text"),
        ])
        self._table.load_rows(table.rows, row_ids=table.row_ids)
        layout.addWidget(self._table)

        close_row = QHBoxLayout()
        close_row.addStretch(1)
        close_button = create_secondary_button(text="Cerrar")
        close_button.clicked.connect(self.accept)
        close_row.addWidget(close_button)
        layout.addLayout(close_row)


class RecordTemperatureReadingDialog(FormDialog):
    """Registra una lectura de temperatura (§21 "Registrar lectura"): sensor,
    almacén, punto de lectura y el rango configurado para esta captura. El
    producto/lote es opcional — sólo aplica cuando la excursión debe poder
    bloquear un lote específico (auto-bloqueo); sin lote, una excursión sólo
    genera alerta. Sólo Celsius (igual que el resto del módulo — el perfil de
    temperatura de los almacenes tampoco expone Fahrenheit)."""

    def __init__(self, parent=None, *, warehouse_options=None, product_provider,
                 lots_provider) -> None:
        super().__init__(parent, title="Registrar lectura de temperatura")
        self._lots_provider = lots_provider

        self.sensor_input = StandardLineEdit(self, placeholder="Sensor (p.ej. TEMP-01)")
        self.warehouse_combo = QComboBox(self)
        for option in (warehouse_options or []):
            self.warehouse_combo.addItem(option.label, option.id)
        self.point_combo = QComboBox(self)
        for code, label in TEMPERATURE_POINT_ES.items():
            self.point_combo.addItem(label, code)
        self.temperature_input = DecimalInput(self, precision=2, suffix="°C")
        self.min_temp_input = DecimalInput(self, precision=2, suffix="°C")
        self.max_temp_input = DecimalInput(self, precision=2, suffix="°C")
        self.warning_margin_input = DecimalInput(self, precision=2, minimum="0",
                                                 nullable=True, suffix="°C")
        self.product = EntitySearchInput(
            self, provider=product_provider,
            placeholder="Buscar producto (opcional, para vincular un lote)…")
        self.product.selected.connect(self._on_product_selected)
        self.lot_combo = QComboBox(self)
        self.lot_combo.addItem("Ninguno", "")
        self.auto_block_check = QCheckBox(
            "Bloquear lote automáticamente si excede el rango", self)

        self.form.addRow("Sensor:", self.sensor_input)
        self.form.addRow("Almacén:", self.warehouse_combo)
        self.form.addRow("Punto de lectura:", self.point_combo)
        self.form.addRow("Temperatura:", self.temperature_input)
        self.form.addRow("Mín. permitido:", self.min_temp_input)
        self.form.addRow("Máx. permitido:", self.max_temp_input)
        self.form.addRow("Margen de advertencia:", self.warning_margin_input)
        self.form.addRow("Producto (opcional):", self.product)
        self.form.addRow("Lote:", self.lot_combo)
        self.form.addRow("", self.auto_block_check)
        self.add_button_box(ok_text="Registrar lectura")

    def _on_product_selected(self, product_id) -> None:
        self.lot_combo.clear()
        self.lot_combo.addItem("Ninguno", "")
        pid = str(product_id or "")
        if pid and self._lots_provider:
            table = self._lots_provider(pid)
            for row, lid in zip(table.rows, table.row_ids):
                self.lot_combo.addItem(str(row[0]), lid)

    def sensor_id(self) -> str:
        return self.sensor_input.value()

    def warehouse_id(self) -> str | None:
        return str(self.warehouse_combo.currentData() or "") or None

    def reading_point(self) -> str:
        return str(self.point_combo.currentData() or "")

    def temperature(self):
        return self.temperature_input.decimal_value()

    def min_temp(self):
        return self.min_temp_input.decimal_value()

    def max_temp(self):
        return self.max_temp_input.decimal_value()

    def warning_margin(self):
        return self.warning_margin_input.decimal_value() or 0

    def lot_id(self) -> str | None:
        return str(self.lot_combo.currentData() or "") or None

    def auto_block(self) -> bool:
        return self.auto_block_check.isChecked()


class ResolveExcursionDialog(FormDialog):
    """Resuelve una excursión abierta (§21 "Resolver excursión"): libera o
    rechaza el lote (si el auto-bloqueo lo puso en cuarentena) y cierra la
    excursión — mismo patrón de motivo obligatorio que
    ``ReverseAdjustmentDialog``/``BlockReasonDialog``."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Resolver excursión")
        self.action_combo = QComboBox(self)
        self.action_combo.addItem("Liberar lote", "RELEASE")
        self.action_combo.addItem("Rechazar lote", "REJECT")
        self.note_input = StandardTextArea(self, placeholder="Motivo de la resolución…")
        self.note_input.setMaximumHeight(90)
        self.form.addRow("Acción:", self.action_combo)
        self.form.addRow("Motivo:", self.note_input)
        self.add_button_box(ok_text="Resolver")

    def resolution(self) -> str:
        return str(self.action_combo.currentData() or "RELEASE")

    def note(self) -> str:
        return self.note_input.value()


class CreateReservationDialog(FormDialog):
    """Nueva reserva (§22) para el producto ya seleccionado en la página: origen,
    documento, cantidad, almacén y vencimiento opcional. Reduce el disponible a
    prometer sin mover stock físico — la asignación a lotes concretos es un paso
    aparte ("Asignar"), así que no se pide lote aquí."""

    def __init__(self, parent=None, *, warehouse_options=None, location_options=None) -> None:
        super().__init__(parent, title="Nueva reserva")
        self.source_combo = QComboBox(self)
        for code, label in RESERVATION_SOURCE_ES.items():
            self.source_combo.addItem(label, code)
        self.document_input = StandardLineEdit(self, placeholder="Documento origen")
        self.quantity_input = DecimalInput(self, precision=3, minimum="0.001")
        self.weight_input = DecimalInput(self, precision=3, minimum="0", nullable=True)
        self.warehouse_combo = QComboBox(self)
        for option in (warehouse_options or []):
            self.warehouse_combo.addItem(option.label, option.id)
        self.location_combo = QComboBox(self)
        self.location_combo.addItem("Automática (todo el almacén)", "")
        for option in (location_options or []):
            self.location_combo.addItem(option.label, option.id)
        self.expiry_check = QCheckBox("Con vencimiento", self)
        self.expiry_input = DateInput(self)
        self.expiry_input.setEnabled(False)
        self.expiry_check.toggled.connect(self.expiry_input.setEnabled)

        self.form.addRow("Origen:", self.source_combo)
        self.form.addRow("Documento:", self.document_input)
        self.form.addRow("Cantidad:", self.quantity_input)
        self.form.addRow("Peso (opcional):", self.weight_input)
        self.form.addRow("Almacén:", self.warehouse_combo)
        self.form.addRow("Ubicación:", self.location_combo)
        self.form.addRow("", self.expiry_check)
        self.form.addRow("Vence:", self.expiry_input)
        self.add_button_box(ok_text="Crear reserva")

    def source_code(self) -> str:
        return str(self.source_combo.currentData() or "")

    def source_document_id(self) -> str:
        return self.document_input.value()

    def quantity(self):
        return self.quantity_input.decimal_value()

    def weight(self):
        return self.weight_input.decimal_value() or 0

    def warehouse_id(self) -> str | None:
        return str(self.warehouse_combo.currentData() or "") or None

    def location_id(self) -> str | None:
        return str(self.location_combo.currentData() or "") or None

    def expires_at(self) -> str | None:
        return self.expiry_input.date_value().isoformat() if self.expiry_check.isChecked() else None


class ReleaseReservationDialog(FormDialog):
    """Motivo de liberación — capturado antes de liberar cualquier reserva
    activa (§22). Mismo patrón que ``ReverseAdjustmentDialog``/``BlockReasonDialog``:
    una razón obligatoria, auditada."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Liberar reserva")
        self.reason_input = StandardTextArea(self, placeholder="Motivo de la liberación…")
        self.reason_input.setMaximumHeight(90)
        self.form.addRow("Motivo:", self.reason_input)
        self.add_button_box(ok_text="Liberar")

    def reason(self) -> str:
        return self.reason_input.value()


def _wrap(layout):
    """A bare ``QFormLayout`` can't be added to another layout directly —
    ``SectionCard.add`` expects a widget. Wraps it in a plain container."""
    container = QWidget()
    container.setLayout(layout)
    return container
