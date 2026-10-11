"""Cotizaciones (CRM-43, §50): bandeja, por aprobar y detalle con partidas.

Viven dentro de Clientes y CRM (decisión del usuario). Toda acción pasa por su
caso de uso de ``backend/application/quotes``; aquí sólo se presenta:

* el precio de lista lo pone Precios; bajar un precio manda la cotización a
  aprobación de otra persona;
* sólo un borrador se edita;
* aceptada se convierte en Pedido a los precios cotizados.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QFormLayout, QHBoxLayout, QLabel, QWidget

from backend.application.quotes.permissions import QuotePermissions
from frontend.desktop.components import ColumnSpec, SectionCard, StandardTable
from frontend.desktop.components.icons import Icons
from frontend.desktop.modules.customers_crm.formatting import fmt_date, fmt_datetime, fmt_money
from frontend.desktop.modules.customers_crm.forms import FieldSpec, ask
from frontend.desktop.modules.customers_crm.labels import label, options
from frontend.desktop.modules.customers_crm.pages._outcomes import Fail
from frontend.desktop.modules.customers_crm.pages._workbench import (
    Action,
    CrmWorkbenchPage,
    FilterSpec,
    Kpi,
    Row,
)
from frontend.desktop.themes.tokens import Spacing

_OPEN = ("DRAFT", "PENDING_APPROVAL", "APPROVED", "SENT", "ACCEPTED")
_TRAIL_LABELS = {
    "QUOTE_CREATED": "Creada", "QUOTE_UPDATED": "Modificada",
    "QUOTE_SUBMITTED": "Enviada a aprobación", "QUOTE_APPROVED": "Aprobada",
    "QUOTE_RETURNED_TO_DRAFT": "Regresó a borrador", "QUOTE_SENT": "Enviada al cliente",
    "QUOTE_ACCEPTED": "Aceptada por el cliente", "QUOTE_REJECTED": "Rechazada por el cliente",
    "QUOTE_CANCELLED": "Cancelada", "QUOTE_EXPIRED": "Vencida",
    "QUOTE_REVISED": "Nueva versión", "QUOTE_CONVERTED": "Convertida en pedido",
    "QUOTE_EXPORTED": "PDF generado",
}


def _value(status) -> str:
    return getattr(status, "value", status)


def _qty(value) -> str:
    text = f"{value:,.3f}".rstrip("0").rstrip(".")
    return text or "0"


def _decimal_or_fail(text: str, caption: str):
    try:
        value = Decimal(str(text).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None, Fail(f"{caption}: escribe un número (por ejemplo 2.5).")
    if value <= 0:
        return None, Fail(f"{caption} debe ser mayor que cero.")
    return value, None


# -- diálogos -------------------------------------------------------------------------
def create_quote_dialog(parent, presenter, *, customer_id: str | None = None,
                        customer_label: str = "", opportunity_id: str | None = None):
    fields = []
    if not opportunity_id:
        fields.append(FieldSpec("customer", "Cliente", "customer", required=True,
                                default=customer_id, default_label=customer_label))
    fields += [
        FieldSpec("valid_until", "Válida hasta", "date", required=True,
                  helper="Pasada esta fecha la cotización vence sola."),
        FieldSpec("notes", "Condiciones para el cliente", "textarea",
                  helper="Aparecen en el PDF: entrega, forma de pago, observaciones."),
        FieldSpec("internal_notes", "Notas internas", "textarea"),
    ]

    def submit(v):
        return presenter.run(
            "create_quote", customer_id=v.get("customer") or customer_id,
            opportunity_id=opportunity_id, branch_id=presenter.branch_id(),
            valid_until=v["valid_until"], notes=v["notes"], internal_notes=v["internal_notes"])

    return ask(parent, title="Nueva cotización", submit_text="Crear", intro=(
        "Después agrega los productos: el precio de lista lo pone Precios para este "
        "cliente."), fields=tuple(fields),
        customer_provider=presenter.customer_search_options, on_submit=submit)


def add_line_dialog(parent, presenter, quote_id: str):
    def submit(v):
        qty, problem = _decimal_or_fail(v["quantity"], "Cantidad")
        if problem:
            return problem
        price = v["unit_price"] or None
        return presenter.run("add_quote_line", quote_id=quote_id, product_id=v["product"],
                             quantity=str(qty), unit_price=str(price) if price else None,
                             notes=v["notes"])

    return ask(parent, title="Agregar producto", submit_text="Agregar", fields=(
        FieldSpec("product", "Producto", "product", required=True),
        FieldSpec("quantity", "Cantidad", required=True, placeholder="Ej. 2.5"),
        FieldSpec("unit_price", "Precio negociado", "money",
                  helper="Déjalo en $0.00 para usar el precio de lista. Un precio menor a la "
                         "lista requiere aprobación de otra persona."),
        FieldSpec("notes", "Nota de la partida"),
    ), product_provider=presenter.quote_product_options,
        product_empty_reason=presenter.quote_products_empty_reason, on_submit=submit)


def edit_line_dialog(parent, presenter, quote_id: str, line):
    def submit(v):
        qty, problem = _decimal_or_fail(v["quantity"], "Cantidad")
        if problem:
            return problem
        price = v["unit_price"]
        return presenter.run("update_quote_line", quote_id=quote_id, line_id=line.id,
                             quantity=str(qty), unit_price=str(price) if price else None)

    return ask(parent, title=f"Partida: {line.description}", submit_text="Guardar", fields=(
        FieldSpec("quantity", "Cantidad", required=True, default=_qty(line.quantity)),
        FieldSpec("unit_price", "Precio", "money", default=line.unit_price,
                  helper=f"Precio de lista: {fmt_money(line.list_price)}. Si cambias la "
                         "cantidad, la lista se recalcula (precios por volumen)."),
    ), on_submit=submit)


def edit_header_dialog(parent, presenter, quote):
    return ask(parent, title=f"Datos de {quote.quote_number}", submit_text="Guardar", fields=(
        FieldSpec("valid_until", "Válida hasta", "date", required=True,
                  default=quote.valid_until),
        FieldSpec("notes", "Condiciones para el cliente", "textarea", default=quote.notes),
        FieldSpec("internal_notes", "Notas internas", "textarea",
                  default=quote.internal_notes),
    ), on_submit=lambda v: presenter.run(
        "update_quote", quote_id=quote.id, valid_until=v["valid_until"], notes=v["notes"],
        internal_notes=v["internal_notes"]))


def _reason(parent, presenter, command: str, title: str, submit: str, quote_id: str,
            caption: str = "Motivo"):
    return ask(parent, title=title, submit_text=submit, fields=(
        FieldSpec("reason", caption, "textarea", required=True),),
        on_submit=lambda v: presenter.run(command, quote_id=quote_id, reason=v["reason"]))


def convert_dialog(parent, presenter, quote_id: str):
    return ask(parent, title="Convertir en pedido", submit_text="Crear pedido", intro=(
        "Se crea un pedido en borrador en Pedidos, a los precios cotizados. Ahí se "
        "completa la entrega (dirección, horario) y se confirma."), fields=(
        FieldSpec("fulfillment", "Cómo se entrega", "choice", required=True,
                  options=tuple(options("fulfillment"))),),
        on_submit=lambda v: presenter.run("convert_quote", quote_id=quote_id,
                                          fulfillment_type=v["fulfillment"]))


def revise_dialog(parent, presenter, quote):
    return ask(parent, title=f"Nueva versión de {quote.quote_number}", submit_text="Crear versión",
               intro=("Se copia en borrador con los precios de lista actuales; un precio "
                      "negociado se conserva. Si la anterior seguía vigente, queda cancelada."),
               fields=(FieldSpec("valid_until", "Válida hasta", "date", required=True),),
               on_submit=lambda v: presenter.run("revise_quote", quote_id=quote.id,
                                                 valid_until=v["valid_until"]))


def export_pdf(parent, presenter, quote_number: str, quote_id: str):
    path, _ = QFileDialog.getSaveFileName(parent, "Guardar cotización en PDF",
                                          f"{quote_number.replace('/', '-')}.pdf",
                                          "PDF (*.pdf)")
    if not path:
        return None
    return presenter.run("export_quote_pdf", quote_id=quote_id, path=path)


def quote_actions(page, presenter, quote_of, *, with_open: bool) -> list[Action]:
    """Acciones de estado. ``quote_of(row)`` da (id, folio, estado) de la fila (en
    la bandeja) o de la cotización abierta (en el detalle, ``row`` es ``None``)."""
    p = presenter

    def st(row) -> str:
        info = quote_of(row)
        return info[2] if info else ""

    def qid(row) -> str:
        return quote_of(row)[0]

    actions = []
    if with_open:
        actions.append(Action("Abrir", lambda r: page.open_row(r), primary=True,
                              permission=QuotePermissions.VIEW))
    actions += [
        Action("Terminar", lambda r: page.report(p.run("submit_quote", quote_id=qid(r))),
               enabled=lambda r: st(r) == "DRAFT", permission=QuotePermissions.EDIT,
               tooltip="Cierra el borrador: queda aprobada, o por aprobar si hay precios "
                       "bajo lista."),
        Action("Aprobar", lambda r: page.report(ask(
            page, title="Aprobar precios", submit_text="Aprobar", fields=(
                FieldSpec("note", "Comentario", "textarea"),),
            on_submit=lambda v: p.run("approve_quote", quote_id=qid(r), note=v["note"]))),
            enabled=lambda r: st(r) == "PENDING_APPROVAL", permission=QuotePermissions.APPROVE),
        Action("Regresar a borrador", lambda r: page.report(_reason(
            page, p, "return_quote_to_draft", "Regresar a borrador", "Regresar", qid(r))),
            enabled=lambda r: st(r) in ("PENDING_APPROVAL", "APPROVED"),
            permission=QuotePermissions.EDIT),
        Action("Marcar enviada", lambda r: page.report(p.run("send_quote", quote_id=qid(r))),
               enabled=lambda r: st(r) == "APPROVED", permission=QuotePermissions.SEND,
               tooltip="Registra que se le entregó al cliente (correo, WhatsApp, en mano)."),
        Action("Aceptó", lambda r: page.report(p.run("accept_quote", quote_id=qid(r))),
               enabled=lambda r: st(r) in ("APPROVED", "SENT"),
               permission=QuotePermissions.RESPOND),
        Action("Rechazó", lambda r: page.report(_reason(
            page, p, "reject_quote", "Rechazo del cliente", "Registrar", qid(r),
            "¿Por qué la rechazó?")), enabled=lambda r: st(r) in ("APPROVED", "SENT"),
            permission=QuotePermissions.RESPOND),
        Action("Convertir en pedido", lambda r: page.report(convert_dialog(page, p, qid(r))),
               enabled=lambda r: st(r) == "ACCEPTED", permission=QuotePermissions.CONVERT),
        Action("PDF", lambda r: page.report(export_pdf(page, p, quote_of(r)[1], qid(r))),
               enabled=lambda r: st(r) in ("APPROVED", "SENT", "ACCEPTED", "CONVERTED"),
               permission=QuotePermissions.EXPORT),
        Action("Nueva versión", lambda r: page.after_revise(revise_dialog(page, p, page.quote_for(r))),
               enabled=lambda r: st(r) in ("APPROVED", "SENT", "REJECTED", "EXPIRED"),
               permission=QuotePermissions.CREATE),
        Action("Cancelar", lambda r: page.report(_reason(
            page, p, "cancel_quote", "Cancelar cotización", "Cancelar cotización", qid(r))),
            enabled=lambda r: st(r) in _OPEN, permission=QuotePermissions.CANCEL),
    ]
    return actions


def quote_cells(presenter, q, names) -> Row:
    customer = names.get(q.customer_id, "")
    status = label("quote_status", q.status)
    discount = fmt_money(q.discount_total) if q.discount_total else "—"
    expires = fmt_date(q.valid_until)
    return Row(q.id, [
        q.quote_number, customer, status, expires, fmt_money(q.total), discount,
        str(q.line_count), presenter.user_name(q.created_by_user_id), fmt_datetime(q.created_at),
    ], q, [
        ("Folio", q.quote_number), ("Cliente", customer), ("Estado", status),
        ("Válida hasta", expires), ("Total", fmt_money(q.total)), ("Descuento", discount),
        ("Requiere aprobación", "Sí" if q.requires_approval else "No"),
        ("Elaboró", presenter.user_name(q.created_by_user_id)),
        # Mismo identificador corto que usa Pedidos cuando aún no hay folio.
        ("Pedido", f"{q.converted_order_id[:8]} (en Pedidos)" if q.converted_order_id else "—"),
    ])


# -- páginas ---------------------------------------------------------------------------
class QuotesPage(CrmWorkbenchPage):
    route_id = "crm.quotes"
    title = "Cotizaciones"
    subtitle = ("Cotizaciones a clientes. Bajo lista requieren aprobación; aceptadas se "
                "convierten en pedido.")
    icon = Icons.PRICE
    search_placeholder = "Buscar por folio, cliente o quien elaboró…"
    empty_message = "No hay cotizaciones en tu alcance. Crea una con «Nueva cotización»."
    show_detail = True
    detail_title = "Cotización"
    columns = (ColumnSpec("Folio"), ColumnSpec("Cliente", stretch=True), ColumnSpec("Estado"),
               ColumnSpec("Válida hasta", "date"), ColumnSpec("Total", "numeric"),
               ColumnSpec("Descuento", "numeric"), ColumnSpec("Partidas", "numeric"),
               ColumnSpec("Elaboró"), ColumnSpec("Creada", "date"))
    filters = (FilterSpec("status", "Abiertas", options=tuple(options("quote_status"))),)
    reader = "quotes"

    def page_actions(self):
        return [Action("Nueva cotización", lambda _r: self.after_create(
            create_quote_dialog(self, self._presenter)), permission=QuotePermissions.CREATE,
            primary=True, needs_row=False)]

    #: En la bandeja sólo las acciones del día a día; el resto (rechazo, nueva
    #: versión, cancelar, regresar a borrador) vive en el detalle. Con las once
    #: la fila de botones desbordaba la pantalla.
    tray_actions = ("Abrir", "Terminar", "Aprobar", "Marcar enviada", "Aceptó",
                    "Convertir en pedido", "PDF")

    def row_actions(self):
        return [a for a in quote_actions(self, self._presenter, self._info, with_open=True)
                if a.label in self.tray_actions]

    @staticmethod
    def _info(row):
        if row is None:
            return None
        q = row.data
        return q.id, q.quote_number, _value(q.status)

    def quote_for(self, row):
        return row.data

    def after_create(self, result) -> None:
        if self.report(result) and result.entity_id:
            self.row_opened.emit(result.entity_id)

    def after_revise(self, result) -> None:
        self.after_create(result)

    def _fetch_rows(self, filters):
        wanted = filters.get("status")
        return self._presenter.read(self.reader, statuses=(wanted,) if wanted else _OPEN)

    def fetch(self, filters):
        items = self._fetch_rows(filters)
        names = self._presenter.customer_names({q.customer_id for q in items})
        return [quote_cells(self._presenter, q, names) for q in items]

    def kpis(self, rows):
        items = [r.data for r in rows]
        by = lambda *s: [q for q in items if _value(q.status) in s]  # noqa: E731
        return [
            Kpi("Borradores", str(len(by("DRAFT")))),
            Kpi("Por aprobar", str(len(by("PENDING_APPROVAL"))), "warning"),
            Kpi("Enviadas", fmt_money(sum((q.total for q in by("APPROVED", "SENT")),
                                          Decimal("0"))), "accent"),
            Kpi("Aceptadas por convertir", str(len(by("ACCEPTED"))), "success"),
            Kpi("Vencen hoy", str(len([
                q for q in by("APPROVED", "SENT") if q.valid_until == date.today()])), "danger"),
        ]


class QuoteApprovalsPage(QuotesPage):
    route_id = "crm.quote_approvals"
    title = "Cotizaciones por aprobar"
    subtitle = ("Precios por debajo de lista. Aprueba otra persona, nunca quien hizo la "
                "cotización.")
    icon = Icons.APPROVAL
    empty_message = "No hay cotizaciones esperando aprobación."
    filters = ()
    tray_actions = ("Abrir", "Aprobar", "Regresar a borrador")

    def page_actions(self):
        return []

    def _fetch_rows(self, filters):
        return self._presenter.read("quote_approvals")

    def kpis(self, rows):
        items = [r.data for r in rows]
        return [Kpi("Por aprobar", str(len(items)), "warning"),
                Kpi("Descuento total", fmt_money(sum((q.discount_total for q in items),
                                                     Decimal("0"))), "danger")]


class QuoteDetailPage(CrmWorkbenchPage):
    """Una cotización: datos, partidas, importes, historial y sus acciones."""

    quote_opened = pyqtSignal(str)

    route_id = "crm.quote_detail"
    title = "Detalle de cotización"
    subtitle = "Abre una cotización desde «Cotizaciones» (doble clic)."
    icon = Icons.DOCUMENT
    searchable = False
    show_detail = True
    detail_title = "Partida"
    empty_message = "Sin productos. Agrega el primero con «Agregar producto»."
    columns = (ColumnSpec("#", "numeric", min_width=40, preferred_width=48),
               ColumnSpec("Código"), ColumnSpec("Producto", stretch=True),
               ColumnSpec("Cantidad", "numeric"), ColumnSpec("Lista", "numeric"),
               ColumnSpec("Precio", "numeric"), ColumnSpec("Importe", "numeric"),
               ColumnSpec("Aviso"))

    def __init__(self, presenter, parent=None) -> None:
        self._quote = None
        self._quote_id: str | None = None
        super().__init__(presenter, parent)

    # acciones -----------------------------------------------------------------
    def _info(self, _row):
        q = self._quote
        return None if q is None else (q.id, q.quote_number, _value(q.status))

    def quote_for(self, _row):
        return self._quote

    def page_actions(self):
        draft = lambda _r: self._info(None) is not None and self._info(None)[2] == "DRAFT"  # noqa: E731
        base = [
            Action("Agregar producto", lambda _r: self.report(
                add_line_dialog(self, self._presenter, self._quote_id)), enabled=draft,
                permission=QuotePermissions.EDIT, primary=True, needs_row=False),
            Action("Editar datos", lambda _r: self.report(
                edit_header_dialog(self, self._presenter, self._quote)), enabled=draft,
                permission=QuotePermissions.EDIT, needs_row=False),
        ]
        states = quote_actions(self, self._presenter, self._info, with_open=False)
        return base + [Action(a.label, a.handler, enabled=a.enabled, permission=a.permission,
                              needs_row=False, tooltip=a.tooltip) for a in states]

    def row_actions(self):
        draft = lambda _r: self._quote is not None and _value(self._quote.status) == "DRAFT"  # noqa: E731
        return [
            Action("Cambiar cantidad o precio", lambda r: self.report(edit_line_dialog(
                self, self._presenter, self._quote_id, r.data)), enabled=draft,
                permission=QuotePermissions.EDIT, primary=True),
            Action("Quitar", lambda r: self.report(self._presenter.run(
                "remove_quote_line", quote_id=self._quote_id, line_id=r.id)), enabled=draft,
                permission=QuotePermissions.EDIT),
        ]

    def after_revise(self, result) -> None:
        if self.report(result) and result.entity_id:
            self.show_quote(result.entity_id)

    def open_row(self, row) -> None:
        if self._quote is not None and _value(self._quote.status) == "DRAFT":
            self.report(edit_line_dialog(self, self._presenter, self._quote_id, row.data))

    # contenido ----------------------------------------------------------------
    def _build_before_table(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(Spacing.MD)
        facts_card = SectionCard(self, title="Datos")
        self._facts = QWidget(facts_card)
        self._facts_form = QFormLayout(self._facts)
        self._facts_form.setContentsMargins(0, 0, 0, 0)
        facts_card.add(self._facts)
        row.addWidget(facts_card, stretch=3)
        trail_card = SectionCard(self, title="Historial")
        self._trail = StandardTable([ColumnSpec("Fecha", "date"), ColumnSpec("Qué"),
                                     ColumnSpec("Quién"), ColumnSpec("Detalle", stretch=True)],
                                    trail_card)
        self._trail.setAccessibleName("Historial de la cotización")
        self._trail.setMinimumHeight(140)
        trail_card.add(self._trail)
        row.addWidget(trail_card, stretch=4)
        self._root.addLayout(row)

    def show_quote(self, quote_id: str) -> None:
        self._quote_id = quote_id
        self.reload()

    def fetch(self, filters):
        if not self._quote_id:
            self._quote = None
            return []
        detail = self._presenter.read("quote_detail", quote_id=self._quote_id)
        q = self._quote = detail.quote
        names = self._presenter.customer_names([q.customer_id])
        version = f" · versión {q.revision}" if q.revision > 1 else ""
        self.header.set_title(f"Cotización {q.quote_number}")
        self.header.set_subtitle(f"{names.get(q.customer_id, '')} · "
                                 f"{label('quote_status', q.status)}{version}")
        self._render_facts(q, names, detail)
        self._trail.load_rows([
            [fmt_datetime(t["created_at"]), _TRAIL_LABELS.get(t["action"], t["action"]),
             self._presenter.user_name(t["actor_user_id"]) if t["actor_user_id"] not in (
                 None, "SYSTEM") else "Sistema", t["detail"] or "—"]
            for t in reversed(detail.trail)], row_ids=[str(i) for i in range(len(detail.trail))])
        rows = []
        for line in q.lines:
            warn = ("Bajo el mínimo" if line.below_minimum
                    else "Bajo lista" if line.below_list else "")
            rows.append(Row(line.id, [
                str(line.line_number), line.product_code, line.description,
                f"{_qty(line.quantity)} {line.unit_code}".strip(), fmt_money(line.list_price),
                fmt_money(line.unit_price), fmt_money(line.line_total), warn,
            ], line, [
                ("Producto", line.description), ("Código", line.product_code),
                ("Cantidad", f"{_qty(line.quantity)} {line.unit_code}".strip()),
                ("Precio de lista", fmt_money(line.list_price)),
                ("Precio mínimo", fmt_money(line.min_price)),
                ("Precio cotizado", fmt_money(line.unit_price)),
                ("Descuento", fmt_money(line.discount)), ("Nota", line.notes or "—"),
            ]))
        return rows

    def _render_facts(self, q, names, detail) -> None:
        while self._facts_form.rowCount():
            self._facts_form.removeRow(0)
        user = self._presenter.user_name
        facts = [
            ("Cliente", names.get(q.customer_id, "")),
            ("Válida hasta", fmt_date(q.valid_until)),
            ("Elaboró", user(q.created_by_user_id)),
            ("Aprobó", user(q.approved_by_user_id) if q.approved_by_user_id else
             ("No requiere" if q.status.value not in ("DRAFT", "PENDING_APPROVAL")
              and not q.requires_approval else "—")),
            ("Enviada", fmt_datetime(q.sent_at)),
            ("Pedido", f"{detail.order_reference} · {label('order_status', detail.order_status)}"
             " (en Pedidos)" if detail.order_reference else "—"),
            ("Condiciones", q.notes or "—"),
            ("Notas internas", q.internal_notes or "—"),
        ]
        if q.reject_reason:
            facts.append(("Motivo del rechazo", q.reject_reason))
        if q.cancel_reason:
            facts.append(("Motivo de cancelación", q.cancel_reason))
        if q.approval_note:
            facts.append(("Nota de aprobación", q.approval_note))
        for caption, value in facts:
            text = QLabel(value or "—", self._facts)
            text.setWordWrap(True)
            self._facts_form.addRow(f"{caption}:", text)

    def kpis(self, rows):
        q = self._quote
        if q is None:
            return []
        return [
            Kpi("A precio de lista", fmt_money(q.list_subtotal)),
            Kpi("Descuento", fmt_money(q.discount_total),
                "warning" if q.discount_total else "neutral"),
            Kpi("Total", fmt_money(q.total), "accent"),
            Kpi("Estado", label("quote_status", q.status),
                "warning" if q.requires_approval and _value(q.status) == "PENDING_APPROVAL"
                else "info"),
        ]


QUOTE_ROUTE_PAGES = {
    "crm.quotes": QuotesPage,
    "crm.quote_approvals": QuoteApprovalsPage,
}
