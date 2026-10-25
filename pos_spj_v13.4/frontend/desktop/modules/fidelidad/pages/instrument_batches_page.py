"""Lotes físicos de cupones y vales (auditoría de Fidelidad 968e0bc).

Ciclo: Borrador → Por aprobar → Aprobado (piezas emitidas, sin efecto
contable) → Impreso → Activo (los vales ya tienen saldo y Finanzas reconoce el
pasivo) → Cancelado. Quien crea no aprueba: lo decide el caso de uso.

La página sólo presenta y pide datos; cada botón llama a un comando del
presenter y muestra el mensaje que devuelve el backend. El código completo de
una pieza sólo existe al generar el PDF del pliego; la tabla muestra el folio y
el prefijo.
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt5.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel

from frontend.desktop.components import ColumnSpec, StandardTable
from frontend.desktop.components.buttons import (
    create_danger_button,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.date_input import DateInput
from frontend.desktop.components.dialogs import ConfirmationDialog, FormDialog
from frontend.desktop.components.integer_input import IntegerInput
from frontend.desktop.components.money_input import MoneyInput
from frontend.desktop.components.pages import StandardPage
from frontend.desktop.components.percent_input import PercentInput
from frontend.desktop.components.selection_controls import StandardComboBox
from frontend.desktop.components.text_inputs import StandardLineEdit
from frontend.desktop.themes.tokens import Spacing

from backend.application.commercial_instruments.queries.instrument_batch_query_service import (
    FUNDING_LABELS,
    KIND_LABELS,
    MODE_LABELS,
    PIECE_STATUS_LABELS,
    STATUS_LABELS,
)
from backend.application.loyalty.permissions import LoyaltyPermissions as LP

# El prepagado se vende en caja, pieza por pieza; un lote no lo ofrece.
_FUNDING_CHOICES = ("PROMOTIONAL", "COMPENSATION", "THIRD_PARTY")
_LEFTOVER_LABELS = {"REQUIRE_FULL_USE": "Debe usarse completo",
                    "FORFEIT": "El sobrante se pierde"}
_BASE_LABELS = {"GROSS": "Sobre el total antes de descuentos",
                "NET": "Sobre el total después de descuentos"}


class BatchFormDialog(FormDialog):
    """Captura de un lote nuevo. `values()` devuelve los argumentos del comando."""

    def __init__(self, definitions: dict, branch_id: str, parent=None) -> None:
        super().__init__(parent, title="Nuevo lote de vales o cupones")
        self._definitions = definitions
        self._branch_id = branch_id
        self.kind = StandardComboBox(self)
        for clave in ("VOUCHER", "COUPON"):
            self.kind.addItem(KIND_LABELS[clave], clave)
        self.definition = StandardComboBox(self)
        self.name = StandardLineEdit(self)
        self.quantity = IntegerInput(self, minimum=1, maximum=5000)
        self.unit_value = MoneyInput(self)
        self.funding = StandardComboBox(self)
        for clave in _FUNDING_CHOICES:
            self.funding.addItem(FUNDING_LABELS[clave], clave)
        self.mode = StandardComboBox(self)
        for clave in ("ONE_EVENT", "MULTI_EVENT"):
            self.mode.addItem(MODE_LABELS[clave], clave)
        self.max_redemptions = IntegerInput(self, minimum=0, maximum=999)
        self.max_percent = PercentInput(self)
        self.percent_base = StandardComboBox(self)
        for clave, texto in _BASE_LABELS.items():
            self.percent_base.addItem(texto, clave)
        self.leftover = StandardComboBox(self)
        for clave, texto in _LEFTOVER_LABELS.items():
            self.leftover.addItem(texto, clave)
        self.has_valid_to = QCheckBox("Con fecha de vencimiento", self)
        self.valid_to = DateInput(self)
        self.valid_to.setEnabled(False)
        self.only_this_branch = QCheckBox("Sólo en esta sucursal", self)
        self.only_this_branch.setEnabled(bool(branch_id))

        self.form.addRow("Tipo", self.kind)
        self.form.addRow("Definición", self.definition)
        self.form.addRow("Nombre del lote", self.name)
        self.form.addRow("Piezas", self.quantity)
        self.form.addRow("Valor de cada vale", self.unit_value)
        self.form.addRow("Quién lo paga", self.funding)
        self.form.addRow("Uso", self.mode)
        self.form.addRow("Canjes máximos (0 = sin tope)", self.max_redemptions)
        self.form.addRow("Tope por venta (% · 0 = sin tope)", self.max_percent)
        self.form.addRow("Base del porcentaje", self.percent_base)
        self.form.addRow("Si sobra saldo en un solo uso", self.leftover)
        self.form.addRow(self.has_valid_to)
        self.form.addRow("Válido hasta", self.valid_to)
        self.form.addRow(self.only_this_branch)
        self.add_button_box(ok_text="Crear borrador")

        self.kind.currentIndexChanged.connect(self._on_kind_changed)
        self.has_valid_to.toggled.connect(self.valid_to.setEnabled)
        self._on_kind_changed()

    def _on_kind_changed(self, *_args) -> None:
        tipo = self.kind.currentData()
        self.definition.clear()
        for ident, etiqueta in self._definitions.get(tipo, ()):
            self.definition.addItem(etiqueta, ident)
        es_vale = tipo == "VOUCHER"
        # Un cupón vale lo que dice su definición y siempre es de un solo uso.
        for campo in (self.unit_value, self.mode, self.max_redemptions, self.max_percent,
                      self.percent_base, self.leftover):
            campo.setEnabled(es_vale)

    def values(self) -> dict:
        es_vale = self.kind.currentData() == "VOUCHER"
        tope = self.max_percent.decimal_value()
        canjes = int(self.max_redemptions.value())
        valores = {
            "kind": self.kind.currentData(),
            "definition_id": self.definition.currentData() or "",
            "name": self.name.text().strip(),
            "quantity": int(self.quantity.value()),
            "funding_source": self.funding.currentData(),
            "valid_to": (self.valid_to.date_value().isoformat()
                         if self.has_valid_to.isChecked() else None),
            "branch_ids": ((self._branch_id,) if self.only_this_branch.isChecked()
                           and self._branch_id else ()),
        }
        if es_vale:
            valores.update(
                unit_value=self.unit_value.decimal_value(),
                redemption_mode=self.mode.currentData(),
                max_redemptions=canjes or None,
                max_percent_per_sale=tope if tope > 0 else None,
                percent_base=self.percent_base.currentData(),
                leftover_policy=self.leftover.currentData())
        return valores


def _ask_text(parent, title: str, label: str) -> str | None:
    texto, aceptado = FormDialog.get_text(parent, title, label)
    return texto.strip() if aceptado and texto.strip() else None


def _ask_pdf_path(parent, suggested: str) -> str | None:
    from PyQt5.QtWidgets import QFileDialog

    ruta, _ = QFileDialog.getSaveFileName(parent, "Guardar pliego", suggested, "PDF (*.pdf)")
    return ruta or None


def _confirm(parent, title: str, message: str) -> bool:
    dialogo = ConfirmationDialog(parent, title=title, message=message)
    return dialogo.exec_() == QDialog.Accepted


@dataclass
class _Dialogs:
    """Fábricas de diálogos modales. Las pruebas las sustituyen para no bloquear."""

    batch_form = BatchFormDialog
    ask_text = staticmethod(_ask_text)
    save_pdf = staticmethod(_ask_pdf_path)
    confirm = staticmethod(_confirm)


class InstrumentBatchesPage(StandardPage):
    def __init__(self, presenter, parent=None, *, dialogs: _Dialogs | None = None) -> None:
        super().__init__(parent, title="Lotes de vales y cupones",
                         subtitle="Diseña, aprueba, imprime y activa piezas físicas. "
                                  "Quien crea un lote no puede aprobarlo.")
        self.setObjectName("fidelidadInstrumentBatchesPage")
        self._presenter = presenter
        self.dialogs = dialogs or _Dialogs()
        self._loaded = False
        self._rows: dict = {}

        layout = self.content_layout
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(Spacing.MD)

        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        layout.addWidget(self.status_label)

        acciones = QHBoxLayout()
        self.buttons = {}
        for clave, texto, permiso, fabrica in (
                ("create", "Nuevo lote", LP.BATCH_CREATE, create_primary_button),
                ("submit", "Enviar a aprobación", LP.BATCH_CREATE, create_secondary_button),
                ("approve", "Aprobar", LP.BATCH_APPROVE, create_secondary_button),
                ("print", "Imprimir pliego", LP.BATCH_PRINT, create_secondary_button),
                ("activate", "Activar", LP.BATCH_APPROVE, create_secondary_button),
                ("cancel", "Cancelar lote", LP.BATCH_APPROVE, create_danger_button)):
            boton = fabrica(self, texto)
            boton.setVisible(presenter.can(permiso))
            boton.clicked.connect(getattr(self, f"_{clave}"))
            acciones.addWidget(boton)
            self.buttons[clave] = boton
        acciones.addStretch(1)
        layout.addLayout(acciones)

        self.batches_table = StandardTable(
            [ColumnSpec("Lote"), ColumnSpec("Tipo"), ColumnSpec("Estado", "status"),
             ColumnSpec("Piezas", "numeric"), ColumnSpec("Valor", "numeric"),
             ColumnSpec("Uso"), ColumnSpec("Quién lo paga"), ColumnSpec("Vence"),
             ColumnSpec("Impresiones", "numeric")], self)
        self.batches_table.itemSelectionChanged.connect(self._load_pieces)
        layout.addWidget(self.batches_table)

        piezas = QHBoxLayout()
        piezas.addWidget(QLabel("Piezas del lote seleccionado", self))
        piezas.addStretch(1)
        self.buttons["revoke"] = create_danger_button(self, "Retirar pieza y reponer")
        self.buttons["revoke"].setVisible(presenter.can(LP.BATCH_REVOKE))
        self.buttons["revoke"].clicked.connect(self._revoke)
        piezas.addWidget(self.buttons["revoke"])
        layout.addLayout(piezas)

        self.pieces_table = StandardTable(
            [ColumnSpec("Folio"), ColumnSpec("Estado", "status"), ColumnSpec("Código"),
             ColumnSpec("Impresiones", "numeric"), ColumnSpec("Canjes", "numeric")], self)
        layout.addWidget(self.pieces_table)

    # -- carga -------------------------------------------------------------
    def ensure_loaded(self) -> None:
        if not self._loaded:
            self._loaded = True
            self.refresh()

    def refresh(self) -> None:
        try:
            filas = self._presenter.instrument_batches()
        except Exception as exc:   # el backend negó o falló: se explica, no se oculta
            self._show(f"No fue posible leer los lotes: {exc}", error=True)
            return
        self._rows = {fila.id: fila for fila in filas}
        self.batches_table.load_rows(
            [[f.name, KIND_LABELS.get(f.kind, f.kind), STATUS_LABELS.get(f.status, f.status),
              str(f.quantity), f"$ {f.unit_value:,.2f}", MODE_LABELS.get(f.mode, f.mode),
              FUNDING_LABELS.get(f.funding, f.funding), f.valid_to or "Sin vencimiento",
              str(f.printed_count)] for f in filas],
            row_ids=[f.id for f in filas])
        self.pieces_table.load_rows([])
        if not filas:
            self._show("Todavía no hay lotes. Crea uno con «Nuevo lote».", error=False)

    def _load_pieces(self) -> None:
        lote = self.batches_table.selected_row_id()
        if not lote:
            self.pieces_table.load_rows([])
            return
        try:
            piezas = self._presenter.instrument_batch_pieces(lote)
        except Exception as exc:
            self._show(f"No fue posible leer las piezas: {exc}", error=True)
            return
        self.pieces_table.load_rows(
            [[p.folio, PIECE_STATUS_LABELS.get(p.status, p.status), p.code_hint,
              str(p.print_count), str(p.redemptions)] for p in piezas],
            row_ids=[p.id for p in piezas])

    # -- acciones ----------------------------------------------------------
    def _selected(self) -> str | None:
        lote = self.batches_table.selected_row_id()
        if not lote:
            self._show("Selecciona un lote.", error=True)
        return lote

    def _run(self, command: str, success: str, **kwargs):
        resultado = self._presenter.run_command(command, **kwargs)
        self._show(success if resultado.success else resultado.message,
                   error=not resultado.success)
        if resultado.success:
            self.refresh()
        return resultado

    def _create(self) -> None:
        dialogo = self.dialogs.batch_form(self._presenter.instrument_definitions(),
                                          self._presenter.current_branch_id(), self)
        if dialogo.exec_() != QDialog.Accepted:
            return
        self._run("batch_create", "Borrador creado. Envíalo a aprobación.", **dialogo.values())

    def _submit(self) -> None:
        if (lote := self._selected()) is not None:
            self._run("batch_submit", "Lote enviado a aprobación.", batch_id=lote)

    def _approve(self) -> None:
        if (lote := self._selected()) is not None:
            self._run("batch_approve", "Lote aprobado: piezas emitidas. Imprime el pliego.",
                      batch_id=lote)

    def _activate(self) -> None:
        lote = self._selected()
        if lote is None or not self.dialogs.confirm(
                self, "Activar lote",
                "Las piezas podrán canjearse desde este momento y los vales quedarán con "
                "saldo. ¿Activar?"):
            return
        self._run("batch_activate", "Lote activo: ya se puede canjear en el punto de venta.",
                  batch_id=lote)

    def _cancel(self) -> None:
        lote = self._selected()
        if lote is None:
            return
        motivo = self.dialogs.ask_text(self, "Cancelar lote", "Motivo")
        if motivo is None:
            return
        self._run("batch_cancel", "Lote cancelado.", batch_id=lote, reason=motivo)

    def _print(self) -> None:
        lote = self._selected()
        if lote is None:
            return
        fila = self._rows.get(lote)
        nombre = fila.name if fila is not None else "lote"
        ruta = self.dialogs.save_pdf(self, f"{nombre}.pdf")
        if not ruta:
            return
        resultado = self._presenter.run_command("batch_print", batch_id=lote)
        if not resultado.success:
            self._show(resultado.message, error=True)
            return
        self._write_sheet(resultado.data.get("pieces") or (), ruta,
                          resultado.data.get("batch_name") or nombre)
        self.refresh()

    def _write_sheet(self, piezas, ruta: str, nombre: str) -> None:
        from backend.infrastructure.commercial_instruments.batch_sheet_pdf import (
            render_batch_sheet_pdf,
        )
        try:
            render_batch_sheet_pdf(piezas, ruta, batch_name=nombre)
        except Exception as exc:
            self._show(f"No fue posible generar el PDF: {exc}", error=True)
            return
        self._show(f"Pliego guardado en {ruta} ({len(piezas)} piezas).", error=False)

    def _revoke(self) -> None:
        pieza = self.pieces_table.selected_row_id()
        if not pieza:
            self._show("Selecciona la pieza que se va a retirar.", error=True)
            return
        motivo = self.dialogs.ask_text(self, "Retirar pieza", "Motivo (extravío, daño…)")
        if motivo is None:
            return
        resultado = self._presenter.run_command("batch_revoke_piece", item_id=pieza,
                                                reason=motivo, reissue=True)
        if not resultado.success:
            self._show(resultado.message, error=True)
            return
        nueva = resultado.data.get("piece")
        if nueva is not None:
            ruta = self.dialogs.save_pdf(self, f"reposicion-{nueva.folio}.pdf")
            if ruta:
                self._write_sheet((nueva,), ruta, resultado.data.get("batch_name") or "")
                self._load_pieces()
                return
        self._show("Pieza retirada; su código anterior ya no se acepta.", error=False)
        self._load_pieces()

    def _show(self, message: str, *, error: bool) -> None:
        if not message:
            self.status_label.hide()
            return
        self.status_label.setProperty("state", "ERROR" if error else "READY")
        self.status_label.setText(message)
        self.status_label.show()


__all__ = ["BatchFormDialog", "InstrumentBatchesPage"]
