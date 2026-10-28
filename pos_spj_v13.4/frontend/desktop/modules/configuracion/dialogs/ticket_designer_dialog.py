"""Diseñador del ticket (comparativa de tickets main ↔ ERP, 2026-10-16).

Bloques con su casilla (visible/oculto) y su orden; a la derecha las opciones
del bloque elegido; abajo la vista previa — generada con los BYTES del
renderizador real, con el logo y los datos reales de la sucursal y una venta de
ejemplo, al ancho de papel elegido. «Imprimir prueba» manda ese mismo diseño a
la impresora de la sucursal.

Guardar crea una NUEVA versión (borrador) de la plantilla, que sigue el flujo de
siempre: enviar a aprobación → aprobar (otra persona) → activar. Hasta activarla
no cambia ningún ticket.

Ninguna regla vive aquí: qué es válido lo decide `ticket_layout.validate` (el
presentador devuelve el motivo) y cómo se ve lo decide el renderizador.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QFormLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,QScrollArea,
    QStackedWidget, QVBoxLayout, QWidget,
)

from backend.domain.document_output.ticket_layout import (
    BLOCK_LABELS,
    MESSAGE_CATEGORIES,
    QR_PLACEHOLDERS,
    TicketBlock,
    TicketLayout,
    default_layout,
    is_layout_content,
    layout_for_document_type,
    parse,
)
from frontend.desktop.components import (
    IntegerInput,
    StandardCheckBox,
    StandardComboBox,
    StandardLineEdit,
    create_primary_button,
    create_secondary_button,
)
from frontend.desktop.components.dialogs import MessageDialog, StandardDialog

_ALIGN_LABELS = (("left", "Izquierda"), ("center", "Centro"), ("right", "Derecha"))
_PAPER_LABELS = (("AUTO", "Según la impresora"), ("58", "58 mm"), ("80", "80 mm"))
_CATEGORY_LABELS = {"LOYALTY": "Fidelidad", "FOMO": "Promociones (FOMO)", "CTA": "Invitaciones"}


class TicketDesignerDialog(StandardDialog):
    def __init__(self, presenter, *, document_type: str, content: str | None = None,
                 parent=None) -> None:
        super().__init__(parent, title="Diseñar ticket", width=1100)
        self.setObjectName("ticketDesignerDialog")
        self.setMinimumSize(980, 720)
        self._presenter = presenter
        self._document_type = document_type
        kind = layout_for_document_type(document_type)
        self._layout = (parse(content) if content and is_layout_content(content)
                        else default_layout(kind))
        self.layout_json: str | None = None
        self._loading = False

        root = QHBoxLayout()
        self.content_layout().addLayout(root, stretch=1)

        # ── columna izquierda: bloques y opciones ──────────────────────────
        left = QVBoxLayout()
        root.addLayout(left, stretch=1)
        general = QFormLayout()
        self._paper = StandardComboBox(self, accessible_name="Ancho de papel del diseño")
        for code, label in _PAPER_LABELS:
            self._paper.addItem(label, code)
        general.addRow("Papel:", self._paper)
        self._feed = IntegerInput(self, minimum=0, maximum=10)
        general.addRow("Líneas al final:", self._feed)
        self._cut = StandardCheckBox("Cortar el papel al terminar", self)
        general.addRow("", self._cut)
        left.addLayout(general)

        left.addWidget(QLabel("Bloques (marca los que se imprimen; ordénalos):", self))
        self._blocks = QListWidget(self)
        self._blocks.setObjectName("ticketDesignerBlocks")
        self._blocks.setMinimumHeight(260)
        left.addWidget(self._blocks, stretch=1)
        order = QHBoxLayout()
        self._up = create_secondary_button(self, "Subir")
        self._down = create_secondary_button(self, "Bajar")
        self._up.clicked.connect(lambda: self._move(-1))
        self._down.clicked.connect(lambda: self._move(1))
        order.addWidget(self._up)
        order.addWidget(self._down)
        left.addLayout(order)

        self._options = QStackedWidget(self)
        self._options.setObjectName("ticketDesignerOptions")
        left.addWidget(self._options)
        self._option_pages: dict[str, dict] = {}

        # ── columna derecha: vista previa ──────────────────────────────────
        right = QVBoxLayout()
        root.addLayout(right, stretch=1)
        preview_bar = QHBoxLayout()
        preview_bar.addWidget(QLabel("Vista previa en papel de:", self))
        self._preview_paper = StandardComboBox(self, accessible_name="Papel de la vista previa")
        self._preview_paper.addItem("80 mm", 80)
        self._preview_paper.addItem("58 mm", 58)
        preview_bar.addWidget(self._preview_paper)
        preview_bar.addStretch(1)
        right.addLayout(preview_bar)
        self._preview = QLabel(self)
        self._preview.setObjectName("ticketDesignerPreview")
        self._preview.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._preview)
        scroll.setMinimumWidth(340)
        self._scroll = scroll
        self._png: bytes | None = None
        right.addWidget(scroll, stretch=1)
        self._warnings = QLabel("", self)
        self._warnings.setObjectName("ticketDesignerWarnings")
        self._warnings.setWordWrap(True)
        self._warnings.setProperty("state", "warning")
        right.addWidget(self._warnings)

        footer = QWidget(self)
        actions = QHBoxLayout(footer)
        actions.setContentsMargins(0, 0, 0, 0)
        self._btn_defaults = create_secondary_button(self, "Restablecer diseño de fábrica")
        self._btn_defaults.clicked.connect(self._restore_defaults)
        actions.addWidget(self._btn_defaults)
        self._btn_test = create_secondary_button(self, "Imprimir prueba")
        self._btn_test.clicked.connect(self._print_test)
        actions.addWidget(self._btn_test)
        actions.addStretch(1)
        cancel = create_secondary_button(self, "Cancelar")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        self._btn_save = create_primary_button(self, "Guardar como nueva versión")
        self._btn_save.clicked.connect(self._save)
        actions.addWidget(self._btn_save)
        self.add_footer_widget(footer)

        self._load(self._layout)
        self._blocks.currentRowChanged.connect(self._show_options)
        self._blocks.itemChanged.connect(lambda _item: self._changed())
        self._paper.currentIndexChanged.connect(lambda _i: self._changed())
        self._feed.valueChanged.connect(lambda _v: self._changed())
        self._cut.toggled.connect(lambda _v: self._changed())
        self._preview_paper.currentIndexChanged.connect(lambda _i: self._refresh_preview())
        self._blocks.setCurrentRow(0)
        self._refresh_preview()

    # ── modelo ⇄ pantalla ────────────────────────────────────────────────
    def _load(self, layout: TicketLayout) -> None:
        self._loading = True
        self._paper.setCurrentIndex(max(0, self._paper.findData(layout.paper)))
        self._feed.setValue(layout.feed_lines)
        self._cut.setChecked(layout.cut)
        self._blocks.clear()
        while self._options.count():
            self._options.removeWidget(self._options.widget(0))
        self._option_pages.clear()
        for block in layout.blocks:
            item = QListWidgetItem(BLOCK_LABELS.get(block.type, block.type))
            item.setData(Qt.UserRole, block.type)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if block.enabled else Qt.Unchecked)
            self._blocks.addItem(item)
            self._build_options(block)
        self._loading = False

    def _build_options(self, block: TicketBlock) -> None:
        page = QWidget(self._options)
        form = QFormLayout(page)
        widgets: dict = {}
        align = StandardComboBox(page, accessible_name="Alineación")
        for code, label in _ALIGN_LABELS:
            align.addItem(label, code)
        align.setCurrentIndex(max(0, align.findData(block.align)))
        align.currentIndexChanged.connect(lambda _i: self._changed())
        form.addRow("Alineación:", align)
        widgets["align"] = align
        if block.type == "logo":
            width = IntegerInput(page, minimum=20, maximum=100)
            width.setValue(int(block.option("width_pct", 60)))
            width.valueChanged.connect(lambda _v: self._changed())
            form.addRow("Tamaño (% del ancho del papel):", width)
            widgets["width_pct"] = width
            form.addRow("", QLabel("El logo se carga en Configuración → Empresa y sucursales.",
                                   page))
        elif block.type == "items":
            unit = StandardCheckBox("Mostrar precio unitario", page)
            unit.setChecked(bool(block.option("show_unit_price", True)))
            unit.toggled.connect(lambda _v: self._changed())
            form.addRow("", unit)
            widgets["show_unit_price"] = unit
        elif block.type == "messages":
            limits = {**{c: 0 for c in MESSAGE_CATEGORIES}, **(block.option("max") or {})}
            spins = {}
            for category in MESSAGE_CATEGORIES:
                spin = IntegerInput(page, minimum=0, maximum=5)
                spin.setValue(int(limits.get(category, 0)))
                spin.valueChanged.connect(lambda _v: self._changed())
                form.addRow(f"{_CATEGORY_LABELS[category]} (máx.):", spin)
                spins[category] = spin
            widgets["max"] = spins
            form.addRow("", QLabel("Las campañas se administran en esta misma página.", page))
        elif block.type == "qr":
            url = StandardLineEdit(page, placeholder="https://misitio.mx/factura?folio={folio}")
            url.setText(str(block.option("url", "") or ""))
            url.textChanged.connect(lambda _t: self._changed())
            form.addRow("Dirección (URL):", url)
            caption = StandardLineEdit(page, placeholder="Texto bajo el QR (opcional)")
            caption.setText(str(block.option("caption", "") or ""))
            caption.textChanged.connect(lambda _t: self._changed())
            form.addRow("Leyenda:", caption)
            hint = QLabel("Marcadores: " + ", ".join("{" + p + "}" for p in QR_PLACEHOLDERS)
                          + ". Nunca datos del cliente.", page)
            hint.setWordWrap(True)
            form.addRow("", hint)
            widgets["url"], widgets["caption"] = url, caption
        elif block.type in ("thanks", "raffle_title", "legal_text"):
            text = StandardLineEdit(page, placeholder="Texto")
            text.setText(str(block.option("text", "") or ""))
            text.textChanged.connect(lambda _t: self._changed())
            form.addRow("Texto:", text)
            widgets["text"] = text
        elif block.type == "barcode":
            form.addRow("", QLabel("Código 128 con el folio de la venta (o el número de "
                                   "boleto).", page))
        self._options.addWidget(page)
        self._option_pages[block.type] = widgets

    def _current_layout(self) -> TicketLayout:
        blocks = []
        for row in range(self._blocks.count()):
            item = self._blocks.item(row)
            block_type = item.data(Qt.UserRole)
            widgets = self._option_pages.get(block_type, {})
            options: dict = {}
            for key, widget in widgets.items():
                if key == "align":
                    continue
                if key == "max":
                    options["max"] = {c: s.value() for c, s in widget.items()}
                elif isinstance(widget, StandardCheckBox):
                    options[key] = widget.isChecked()
                elif isinstance(widget, IntegerInput):
                    options[key] = widget.value()
                else:
                    value = widget.text().strip()
                    if value:
                        options[key] = value
            blocks.append(TicketBlock(type=block_type,
                                      enabled=item.checkState() == Qt.Checked,
                                      align=widgets["align"].currentData() if widgets else "center",
                                      options=options))
        return TicketLayout(kind=self._layout.kind, blocks=tuple(blocks),
                            paper=self._paper.currentData(), feed_lines=self._feed.value(),
                            cut=self._cut.isChecked())

    # ── interacción ──────────────────────────────────────────────────────
    def _show_options(self, row: int) -> None:
        if row < 0:
            return
        block_type = self._blocks.item(row).data(Qt.UserRole)
        widgets_index = list(self._option_pages).index(block_type)
        self._options.setCurrentIndex(widgets_index)

    def _move(self, delta: int) -> None:
        row = self._blocks.currentRow()
        target = row + delta
        if row < 0 or not 0 <= target < self._blocks.count():
            return
        layout = self._current_layout()
        blocks = list(layout.blocks)
        blocks[row], blocks[target] = blocks[target], blocks[row]
        self._load(TicketLayout(layout.kind, tuple(blocks), layout.paper, layout.feed_lines,
                                layout.cut))
        self._blocks.setCurrentRow(target)
        self._changed()

    def _restore_defaults(self) -> None:
        self._load(default_layout(self._layout.kind))
        self._blocks.setCurrentRow(0)
        self._changed()

    def _changed(self) -> None:
        if not self._loading:
            self._refresh_preview()

    def _json(self) -> str:
        return self._current_layout().to_json()

    def _refresh_preview(self) -> None:
        layout_json = self._json()
        problem = self._presenter.validate_ticket_layout(layout_json)
        if problem:
            self._preview.clear()
            self._warnings.setText(problem)
            self._btn_save.setEnabled(False)
            self._btn_test.setEnabled(False)
            return
        png, warnings, error = self._presenter.ticket_preview(
            layout_json=layout_json, document_type=self._document_type,
            paper_width_mm=int(self._preview_paper.currentData()))
        self._btn_save.setEnabled(error is None)
        self._btn_test.setEnabled(error is None)
        if error:
            self._preview.clear()
            self._warnings.setText(error)
            return
        self._png = png
        self._show_png()
        self._warnings.setText("\n".join(f"• {w}" for w in warnings))

    def _show_png(self) -> None:
        """La imagen del ticket, ajustada al ancho del panel (sin recortarla)."""
        if not self._png:
            return
        pixmap = QPixmap()
        pixmap.loadFromData(self._png, "PNG")
        width = max(200, self._scroll.viewport().width() - 8)
        if pixmap.width() > width:
            pixmap = pixmap.scaledToWidth(width, Qt.SmoothTransformation)
        self._preview.setPixmap(pixmap)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._show_png()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if getattr(self, "_png", None):
            self._show_png()

    def _print_test(self) -> None:
        ok, message = self._presenter.ticket_print_test(
            layout_json=self._json(), document_type=self._document_type)
        (MessageDialog.information if ok else MessageDialog.warning)(self, "Imprimir prueba", message)

    def _save(self) -> None:
        layout_json = self._json()
        problem = self._presenter.validate_ticket_layout(layout_json)
        if problem:
            MessageDialog.warning(self, "Diseño del ticket", problem)
            return
        self.layout_json = layout_json
        self.accept()
