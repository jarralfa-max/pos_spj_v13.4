"""Quote / QuoteLine — la cotización y sus partidas (CRM-43, §50).

Reglas (decisión del usuario, 2026-10-09):

* El precio de lista lo pone Precios (mismo motor que el mostrador: sucursal,
  canal, cliente y cantidad). Quien cotiza puede bajar el precio de una
  partida; si alguna queda **por debajo de lista**, la cotización necesita la
  aprobación de OTRA persona con permiso — nunca de quien la hizo. A precio de
  lista no se aprueba nada. No hay porcentajes de tolerancia inventados.
* Sólo un borrador se edita. Para cambiar algo ya aprobado o enviado se
  regresa a borrador (pierde la aprobación) o se saca una nueva versión.
* La vigencia es una fecha que elige quien cotiza; pasada la fecha la
  cotización vence sola (salvo si el cliente ya la aceptó).
* Aceptada se convierte en Pedido (tipo «Cotización convertida»), a los
  precios cotizados.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from backend.domain.quotes.enums import (
    EXPIRABLE_STATUSES,
    OPEN_STATUSES,
    REVISABLE_STATUSES,
    QuoteStatus,
)
from backend.domain.quotes.exceptions import (
    InvalidQuoteStateError,
    QuoteSegregationError,
    QuoteValidationError,
)
from backend.shared.ids import new_uuid

_CENT = Decimal("0.01")
_QTY = Decimal("0.001")


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def money(value) -> Decimal:
    try:
        return Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise QuoteValidationError(f"Importe inválido: {value!r}") from exc


def quantity(value) -> Decimal:
    try:
        return Decimal(str(value)).quantize(_QTY, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise QuoteValidationError(f"Cantidad inválida: {value!r}") from exc


@dataclass(slots=True)
class QuoteLine:
    id: str
    quote_id: str
    line_number: int
    product_id: str
    product_code: str
    description: str
    unit_code: str
    weighed: bool
    quantity: Decimal
    list_price: Decimal
    unit_price: Decimal
    min_price: Decimal | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        self.quantity = quantity(self.quantity)
        self.list_price = money(self.list_price)
        self.unit_price = money(self.unit_price)
        self.min_price = None if self.min_price is None else money(self.min_price)
        if self.quantity <= 0:
            raise QuoteValidationError("La cantidad debe ser mayor que cero.")
        if self.unit_price < 0 or self.list_price < 0:
            raise QuoteValidationError("El precio no puede ser negativo.")

    @property
    def line_total(self) -> Decimal:
        return money(self.quantity * self.unit_price)

    @property
    def list_total(self) -> Decimal:
        return money(self.quantity * self.list_price)

    @property
    def discount(self) -> Decimal:
        return max(Decimal("0.00"), self.list_total - self.line_total)

    @property
    def below_list(self) -> bool:
        return self.unit_price < self.list_price

    @property
    def below_minimum(self) -> bool:
        return self.min_price is not None and self.unit_price < self.min_price


@dataclass(slots=True)
class Quote:
    id: str
    quote_number: str
    customer_id: str
    branch_id: str
    valid_until: date
    created_by_user_id: str
    status: QuoteStatus = QuoteStatus.DRAFT
    revision: int = 1
    parent_quote_id: str | None = None
    opportunity_id: str | None = None
    currency: str = "MXN"
    notes: str = ""
    internal_notes: str = ""
    submitted_at: str | None = None
    approved_by_user_id: str | None = None
    approved_at: str | None = None
    approval_note: str = ""
    sent_at: str | None = None
    accepted_at: str | None = None
    rejected_at: str | None = None
    reject_reason: str = ""
    cancelled_at: str | None = None
    cancel_reason: str = ""
    expired_at: str | None = None
    converted_order_id: str | None = None
    converted_at: str | None = None
    lines: list[QuoteLine] = field(default_factory=list)
    version: int = 1
    operation_id: str | None = None
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    # ── alta ──────────────────────────────────────────────────────────────────
    @classmethod
    def create(cls, *, quote_number: str, customer_id: str, branch_id: str, valid_until: date,
               created_by_user_id: str, today: date, opportunity_id: str | None = None,
               notes: str = "", internal_notes: str = "",
               operation_id: str | None = None) -> "Quote":
        if not customer_id:
            raise QuoteValidationError("Elige el cliente.")
        if not branch_id:
            raise QuoteValidationError("La cotización necesita una sucursal.")
        if not created_by_user_id:
            raise QuoteValidationError("Operación sin usuario autenticado.")
        _check_validity(valid_until, today)
        return cls(id=new_uuid(), quote_number=quote_number, customer_id=customer_id,
                   branch_id=branch_id, valid_until=valid_until,
                   created_by_user_id=created_by_user_id, opportunity_id=opportunity_id,
                   notes=notes.strip(), internal_notes=internal_notes.strip(),
                   operation_id=operation_id)

    # ── partidas ──────────────────────────────────────────────────────────────
    def add_line(self, *, product_id: str, product_code: str, description: str,
                 unit_code: str, weighed: bool, quantity_value, list_price, unit_price=None,
                 min_price=None, notes: str = "") -> QuoteLine:
        self._require_draft()
        if any(line.product_id == product_id for line in self.lines):
            raise QuoteValidationError(
                f"«{description}» ya está en la cotización; cambia su cantidad.")
        line = QuoteLine(
            id=new_uuid(), quote_id=self.id,
            line_number=max((line.line_number for line in self.lines), default=0) + 1,
            product_id=product_id, product_code=product_code, description=description,
            unit_code=unit_code, weighed=weighed, quantity=quantity_value,
            list_price=list_price, unit_price=list_price if unit_price is None else unit_price,
            min_price=min_price, notes=notes)
        self.lines.append(line)
        self._touch()
        return line

    def update_line(self, line_id: str, *, quantity_value=None, unit_price=None,
                    list_price=None, min_price=None, notes: str | None = None) -> QuoteLine:
        """Cambiar la cantidad re-tarifica la lista (precios por volumen): quien
        llama pasa la nueva ``list_price``. Si la partida iba a precio de lista,
        sigue a la lista; si tenía un precio negociado, se conserva."""
        self._require_draft()
        line = self.line(line_id)
        followed_list = line.unit_price == line.list_price
        if quantity_value is not None:
            line.quantity = quantity(quantity_value)
            if line.quantity <= 0:
                raise QuoteValidationError("La cantidad debe ser mayor que cero.")
        if list_price is not None:
            line.list_price = money(list_price)
            line.min_price = None if min_price is None else money(min_price)
            if followed_list and unit_price is None:
                line.unit_price = line.list_price
        if unit_price is not None:
            price = money(unit_price)
            if price < 0:
                raise QuoteValidationError("El precio no puede ser negativo.")
            line.unit_price = price
        if notes is not None:
            line.notes = notes
        self._touch()
        return line

    def remove_line(self, line_id: str) -> None:
        self._require_draft()
        line = self.line(line_id)
        self.lines.remove(line)
        self._touch()

    def line(self, line_id: str) -> QuoteLine:
        for line in self.lines:
            if line.id == line_id:
                return line
        raise QuoteValidationError("La partida no pertenece a esta cotización.")

    def update_header(self, *, valid_until: date | None = None, notes: str | None = None,
                      internal_notes: str | None = None, today: date) -> None:
        self._require_draft()
        if valid_until is not None:
            _check_validity(valid_until, today)
            self.valid_until = valid_until
        if notes is not None:
            self.notes = notes.strip()
        if internal_notes is not None:
            self.internal_notes = internal_notes.strip()
        self._touch()

    # ── importes ──────────────────────────────────────────────────────────────
    @property
    def list_subtotal(self) -> Decimal:
        return money(sum((line.list_total for line in self.lines), Decimal("0")))

    @property
    def total(self) -> Decimal:
        return money(sum((line.line_total for line in self.lines), Decimal("0")))

    @property
    def discount_total(self) -> Decimal:
        return max(Decimal("0.00"), self.list_subtotal - self.total)

    @property
    def requires_approval(self) -> bool:
        return any(line.below_list for line in self.lines)

    # ── ciclo de vida ─────────────────────────────────────────────────────────
    def submit(self, *, today: date) -> None:
        """Termina el borrador. Sin precios bajo lista queda APROBADA de una vez."""
        self._require_draft()
        if not self.lines:
            raise QuoteValidationError("Agrega al menos un producto.")
        _check_validity(self.valid_until, today)
        self.submitted_at = _utcnow()
        self.status = (QuoteStatus.PENDING_APPROVAL if self.requires_approval
                       else QuoteStatus.APPROVED)
        self._bump()

    def approve(self, *, approver_user_id: str, note: str = "") -> None:
        if self.status is not QuoteStatus.PENDING_APPROVAL:
            raise InvalidQuoteStateError("Sólo se aprueba una cotización que está por aprobar.")
        if approver_user_id == self.created_by_user_id:
            raise QuoteSegregationError(
                "Quien hizo la cotización no puede aprobar sus propios precios.")
        self.approved_by_user_id = approver_user_id
        self.approved_at = _utcnow()
        self.approval_note = note.strip()
        self.status = QuoteStatus.APPROVED
        self._bump()

    def return_to_draft(self, *, reason: str) -> None:
        """Rechazo de la aprobación, o corrección antes de enviar."""
        if self.status not in (QuoteStatus.PENDING_APPROVAL, QuoteStatus.APPROVED):
            raise InvalidQuoteStateError(
                "Sólo regresa a borrador una cotización por aprobar o aprobada sin enviar.")
        if not reason.strip():
            raise QuoteValidationError("Indica el motivo.")
        self.status = QuoteStatus.DRAFT
        self.approved_by_user_id = None
        self.approved_at = None
        self.approval_note = reason.strip()
        self._bump()

    def send(self, *, today: date) -> None:
        if self.status is not QuoteStatus.APPROVED:
            raise InvalidQuoteStateError("Sólo se envía una cotización aprobada.")
        self._require_valid(today)
        self.status = QuoteStatus.SENT
        self.sent_at = _utcnow()
        self._bump()

    def accept(self, *, today: date) -> None:
        if self.status not in (QuoteStatus.APPROVED, QuoteStatus.SENT):
            raise InvalidQuoteStateError("Sólo se acepta una cotización aprobada o enviada.")
        self._require_valid(today)
        self.status = QuoteStatus.ACCEPTED
        self.accepted_at = _utcnow()
        self._bump()

    def reject(self, *, reason: str) -> None:
        if self.status not in (QuoteStatus.APPROVED, QuoteStatus.SENT):
            raise InvalidQuoteStateError("Sólo el cliente rechaza una cotización aprobada o enviada.")
        if not reason.strip():
            raise QuoteValidationError("Indica por qué la rechazó el cliente.")
        self.status = QuoteStatus.REJECTED
        self.rejected_at = _utcnow()
        self.reject_reason = reason.strip()
        self._bump()

    def cancel(self, *, reason: str) -> None:
        if self.status not in OPEN_STATUSES:
            raise InvalidQuoteStateError("La cotización ya está cerrada.")
        if not reason.strip():
            raise QuoteValidationError("Indica el motivo de la cancelación.")
        self.status = QuoteStatus.CANCELLED
        self.cancelled_at = _utcnow()
        self.cancel_reason = reason.strip()
        self._bump()

    def is_expired(self, today: date) -> bool:
        return self.status in EXPIRABLE_STATUSES and self.valid_until < today

    def expire(self, *, today: date) -> None:
        if not self.is_expired(today):
            raise InvalidQuoteStateError("La cotización sigue vigente.")
        self.status = QuoteStatus.EXPIRED
        self.expired_at = _utcnow()
        self._bump()

    def convert(self, *, order_id: str) -> None:
        if self.status is not QuoteStatus.ACCEPTED:
            raise InvalidQuoteStateError("Sólo se convierte una cotización aceptada.")
        if not order_id:
            raise QuoteValidationError("Falta el pedido.")
        self.status = QuoteStatus.CONVERTED
        self.converted_order_id = order_id
        self.converted_at = _utcnow()
        self._bump()

    def revise(self, *, quote_number: str, created_by_user_id: str, valid_until: date,
               today: date, operation_id: str | None = None) -> "Quote":
        """Nueva versión en borrador con las mismas partidas. Si la anterior seguía
        viva (aprobada o enviada) queda cancelada como reemplazada."""
        if self.status not in REVISABLE_STATUSES:
            raise InvalidQuoteStateError(
                "Sólo se saca una nueva versión de una cotización aprobada, enviada, "
                "rechazada o vencida.")
        _check_validity(valid_until, today)
        new = Quote(
            id=new_uuid(), quote_number=quote_number, customer_id=self.customer_id,
            branch_id=self.branch_id, valid_until=valid_until,
            created_by_user_id=created_by_user_id, revision=self.revision + 1,
            parent_quote_id=self.id, opportunity_id=self.opportunity_id,
            currency=self.currency, notes=self.notes, internal_notes=self.internal_notes,
            operation_id=operation_id)
        for line in self.lines:
            new.lines.append(QuoteLine(
                id=new_uuid(), quote_id=new.id, line_number=line.line_number,
                product_id=line.product_id, product_code=line.product_code,
                description=line.description, unit_code=line.unit_code, weighed=line.weighed,
                quantity=line.quantity, list_price=line.list_price,
                unit_price=line.unit_price, min_price=line.min_price, notes=line.notes))
        if self.status in (QuoteStatus.APPROVED, QuoteStatus.SENT):
            self.status = QuoteStatus.CANCELLED
            self.cancelled_at = _utcnow()
            self.cancel_reason = f"Reemplazada por {quote_number}"
            self._bump()
        return new

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    # ── internos ──────────────────────────────────────────────────────────────
    def _require_draft(self) -> None:
        if self.status is not QuoteStatus.DRAFT:
            raise InvalidQuoteStateError(
                "Sólo se modifica un borrador. Regrésala a borrador o saca una nueva versión.")

    def _require_valid(self, today: date) -> None:
        if self.valid_until < today:
            raise InvalidQuoteStateError(
                f"La cotización venció el {self.valid_until.strftime('%d/%m/%Y')}.")

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def _bump(self) -> None:
        self.version += 1
        self._touch()


def _check_validity(valid_until: date, today: date) -> None:
    if not isinstance(valid_until, date):
        raise QuoteValidationError("Indica hasta cuándo es válida la cotización.")
    if valid_until < today:
        raise QuoteValidationError("La vigencia no puede ser una fecha pasada.")
