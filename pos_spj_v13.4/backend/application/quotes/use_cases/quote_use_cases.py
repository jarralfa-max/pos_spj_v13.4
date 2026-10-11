"""Casos de uso de Cotizaciones (CRM-43, §50).

Cada uno: permiso → unidad de trabajo → regla de dominio → auditoría + evento.
Los errores de negocio vuelven como ``QuoteResult.fail`` con el mensaje del
dominio en español; nunca truenan hacia la pantalla.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from backend.application.quotes.authorization import QuotesAuthorizationPolicy
from backend.application.quotes.permissions import QuotePermissions
from backend.application.quotes.pricing import QuotePricing
from backend.application.quotes.result import QuoteResult
from backend.domain.quotes.entities import Quote
from backend.domain.quotes.events import QuoteEvents
from backend.domain.quotes.exceptions import (
    QuoteNotFoundError,
    QuotesDomainError,
    QuoteValidationError,
)
from backend.infrastructure.db.repositories.quotes.unit_of_work import QuotesUnitOfWork

#: Clientes a los que no se cotiza: el «público en general» no es una relación
#: comercial y uno bloqueado o cerrado no puede comprar.
_NOT_QUOTABLE_TYPES = ("PUBLIC_CUSTOMER", "INTERNAL")
_NOT_QUOTABLE_STATUSES = ("BLOCKED", "CLOSED", "MERGED")
_OPEN_OPPORTUNITY = ("OPEN", "ON_HOLD")


def _today(today: date | None) -> date:
    return today or date.today()


def _date(value) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise QuoteValidationError(f"Fecha inválida: {value!r}") from exc


def _decimal(value, label: str) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise QuoteValidationError(f"{label} inválido: {value!r}") from exc


def _fail(exc: Exception, operation_id: str | None) -> QuoteResult:
    code = getattr(exc, "code", "ERROR")
    return QuoteResult.fail(str(exc), code, operation_id=operation_id)


class _QuoteUseCase:
    permission: str = QuotePermissions.EDIT

    def __init__(self, authorization: QuotesAuthorizationPolicy | None = None, *,
                 pricing_factory=QuotePricing) -> None:
        self._auth = authorization or QuotesAuthorizationPolicy()
        self._pricing_factory = pricing_factory

    def _record(self, uow, quote: Quote, event: str, actor_user_id: str | None,
                operation_id: str | None, detail: str = "") -> None:
        uow.audit.record(quote_id=quote.id, action=event, actor_user_id=actor_user_id,
                         detail=detail, operation_id=operation_id)
        uow.outbox.enqueue(event, {
            "quote_id": quote.id, "quote_number": quote.quote_number,
            "customer_id": quote.customer_id, "opportunity_id": quote.opportunity_id,
            "branch_id": quote.branch_id, "status": quote.status.value,
            "total": str(quote.total), "user_id": actor_user_id,
        }, operation_id)

    @staticmethod
    def _load(uow, quote_id: str) -> Quote:
        quote = uow.quotes.get(quote_id)
        if quote is None:
            raise QuoteNotFoundError("La cotización no existe.")
        return quote


def _check_customer(connection, customer_id: str) -> None:
    from backend.infrastructure.db.repositories.customers.unit_of_work import (
        CustomerUnitOfWork,
    )
    customer = CustomerUnitOfWork(connection).customers.get(customer_id)
    if customer is None:
        raise QuoteValidationError("El cliente no existe.")
    if getattr(customer.customer_type, "value", customer.customer_type) in _NOT_QUOTABLE_TYPES:
        raise QuoteValidationError(
            "Elige un cliente identificado: no se cotiza al público en general.")
    status = getattr(customer.status, "value", customer.status)
    if status in _NOT_QUOTABLE_STATUSES:
        raise QuoteValidationError(f"No se puede cotizar: el cliente está {status.lower()}.")


def _opportunity_customer(connection, opportunity_id: str) -> str:
    from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork
    opportunity = CRMUnitOfWork(connection).opportunities.get(opportunity_id)
    if opportunity is None:
        raise QuoteValidationError("La oportunidad no existe.")
    if getattr(opportunity.status, "value", opportunity.status) not in _OPEN_OPPORTUNITY:
        raise QuoteValidationError("Sólo se cotiza una oportunidad abierta o en pausa.")
    return opportunity.customer_id


def _add_priced_line(pricing, quote: Quote, raw: dict) -> None:
    qty = _decimal(raw.get("quantity"), "Cantidad")
    if qty is None or qty <= 0:
        raise QuoteValidationError("La cantidad debe ser mayor que cero.")
    product = pricing.product(branch_id=quote.branch_id, customer_id=quote.customer_id,
                              product_id=raw["product_id"], quantity=qty)
    quote.add_line(product_id=product.product_id, product_code=product.code,
                   description=product.name, unit_code=product.unit_code,
                   weighed=product.weighed, quantity_value=qty,
                   list_price=product.list_price,
                   unit_price=_decimal(raw.get("unit_price"), "Precio"),
                   min_price=product.min_price, notes=str(raw.get("notes") or ""))


# ── alta y edición ─────────────────────────────────────────────────────────────
class CreateQuoteUseCase(_QuoteUseCase):
    def execute(self, connection, *, actor_user_id: str, operation_id: str, branch_id: str,
                valid_until, customer_id: str | None = None, opportunity_id: str | None = None,
                notes: str = "", internal_notes: str = "", lines: list | tuple = (),
                today: date | None = None) -> QuoteResult:
        try:
            self._auth.require(actor_user_id, QuotePermissions.CREATE)
            with QuotesUnitOfWork(connection) as uow:
                existing = uow.quotes.get_by_operation_id(operation_id)
                if existing is not None:
                    return QuoteResult.ok("Cotización ya registrada", entity_id=existing.id,
                                          operation_id=operation_id)
                if opportunity_id:
                    opp_customer = _opportunity_customer(connection, opportunity_id)
                    if customer_id and customer_id != opp_customer:
                        raise QuoteValidationError(
                            "La oportunidad es de otro cliente.")
                    customer_id = opp_customer
                if not customer_id:
                    raise QuoteValidationError("Elige el cliente.")
                _check_customer(connection, customer_id)
                quote = Quote.create(
                    quote_number=uow.quotes.next_number(), customer_id=customer_id,
                    branch_id=branch_id, valid_until=_date(valid_until),
                    created_by_user_id=actor_user_id, today=_today(today),
                    opportunity_id=opportunity_id or None, notes=notes or "",
                    internal_notes=internal_notes or "", operation_id=operation_id)
                if lines:
                    pricing = self._pricing_factory(connection)
                    for raw in lines:
                        _add_priced_line(pricing, quote, dict(raw))
                uow.quotes.save(quote)
                self._record(uow, quote, QuoteEvents.CREATED, actor_user_id, operation_id)
        except QuotesDomainError as exc:
            return _fail(exc, operation_id)
        return QuoteResult.ok(f"Cotización {quote.quote_number} creada", entity_id=quote.id,
                              operation_id=operation_id, quote_number=quote.quote_number)


class UpdateQuoteUseCase(_QuoteUseCase):
    def execute(self, connection, *, actor_user_id: str, quote_id: str, operation_id: str,
                valid_until=None, notes: str | None = None, internal_notes: str | None = None,
                today: date | None = None) -> QuoteResult:
        try:
            self._auth.require(actor_user_id, QuotePermissions.EDIT)
            with QuotesUnitOfWork(connection) as uow:
                quote = self._load(uow, quote_id)
                quote.update_header(valid_until=_date(valid_until), notes=notes,
                                    internal_notes=internal_notes, today=_today(today))
                uow.quotes.save(quote)
                self._record(uow, quote, QuoteEvents.UPDATED, actor_user_id, operation_id)
        except QuotesDomainError as exc:
            return _fail(exc, operation_id)
        return QuoteResult.ok("Cotización actualizada", entity_id=quote_id,
                              operation_id=operation_id)


class AddQuoteLineUseCase(_QuoteUseCase):
    def execute(self, connection, *, actor_user_id: str, quote_id: str, operation_id: str,
                product_id: str, quantity, unit_price=None, notes: str = "") -> QuoteResult:
        try:
            self._auth.require(actor_user_id, QuotePermissions.EDIT)
            with QuotesUnitOfWork(connection) as uow:
                quote = self._load(uow, quote_id)
                quote._require_draft()
                _add_priced_line(self._pricing_factory(connection), quote, {
                    "product_id": product_id, "quantity": quantity, "unit_price": unit_price,
                    "notes": notes})
                uow.quotes.save(quote)
                self._record(uow, quote, QuoteEvents.UPDATED, actor_user_id, operation_id,
                             detail=f"partida: {quote.lines[-1].description}")
        except QuotesDomainError as exc:
            return _fail(exc, operation_id)
        return QuoteResult.ok("Producto agregado", entity_id=quote_id, operation_id=operation_id)


class UpdateQuoteLineUseCase(_QuoteUseCase):
    def execute(self, connection, *, actor_user_id: str, quote_id: str, line_id: str,
                operation_id: str, quantity=None, unit_price=None,
                notes: str | None = None) -> QuoteResult:
        try:
            self._auth.require(actor_user_id, QuotePermissions.EDIT)
            with QuotesUnitOfWork(connection) as uow:
                quote = self._load(uow, quote_id)
                quote._require_draft()
                line = quote.line(line_id)
                qty = _decimal(quantity, "Cantidad")
                list_price = min_price = None
                if qty is not None and qty != line.quantity:
                    product = self._pricing_factory(connection).product(
                        branch_id=quote.branch_id, customer_id=quote.customer_id,
                        product_id=line.product_id, quantity=qty)
                    list_price, min_price = product.list_price, product.min_price
                quote.update_line(line_id, quantity_value=qty,
                                  unit_price=_decimal(unit_price, "Precio"),
                                  list_price=list_price, min_price=min_price, notes=notes)
                uow.quotes.save(quote)
                self._record(uow, quote, QuoteEvents.UPDATED, actor_user_id, operation_id,
                             detail=f"partida: {line.description}")
        except QuotesDomainError as exc:
            return _fail(exc, operation_id)
        return QuoteResult.ok("Partida actualizada", entity_id=quote_id,
                              operation_id=operation_id)


class RemoveQuoteLineUseCase(_QuoteUseCase):
    def execute(self, connection, *, actor_user_id: str, quote_id: str, line_id: str,
                operation_id: str) -> QuoteResult:
        try:
            self._auth.require(actor_user_id, QuotePermissions.EDIT)
            with QuotesUnitOfWork(connection) as uow:
                quote = self._load(uow, quote_id)
                description = quote.line(line_id).description
                quote.remove_line(line_id)
                uow.quotes.save(quote)
                self._record(uow, quote, QuoteEvents.UPDATED, actor_user_id, operation_id,
                             detail=f"quitada: {description}")
        except QuotesDomainError as exc:
            return _fail(exc, operation_id)
        return QuoteResult.ok("Partida quitada", entity_id=quote_id, operation_id=operation_id)


# ── ciclo de vida ──────────────────────────────────────────────────────────────
class _TransitionUseCase(_QuoteUseCase):
    event: str = ""
    done: str = ""
    permissions: tuple[str, ...] = ()

    def execute(self, connection, *, actor_user_id: str, quote_id: str, operation_id: str,
                today: date | None = None, **kwargs) -> QuoteResult:
        try:
            self._auth.require_any(actor_user_id, *self.permissions)
            with QuotesUnitOfWork(connection) as uow:
                quote = self._load(uow, quote_id)
                detail = self.apply(quote, actor_user_id=actor_user_id, today=_today(today),
                                    **kwargs)
                uow.quotes.save(quote)
                self._record(uow, quote, self.event_for(quote), actor_user_id, operation_id,
                             detail=detail or "")
        except QuotesDomainError as exc:
            return _fail(exc, operation_id)
        return QuoteResult.ok(self.message_for(quote), entity_id=quote_id,
                              operation_id=operation_id, status=quote.status.value)

    def apply(self, quote: Quote, **kwargs) -> str:  # pragma: no cover - abstracto
        raise NotImplementedError

    def event_for(self, quote: Quote) -> str:
        return self.event

    def message_for(self, quote: Quote) -> str:
        return self.done


class SubmitQuoteUseCase(_TransitionUseCase):
    """Termina el borrador: queda APROBADA, o POR APROBAR si va bajo lista."""
    permissions = (QuotePermissions.EDIT,)
    event = QuoteEvents.SUBMITTED

    def apply(self, quote, *, today, **_):
        quote.submit(today=today)
        return ""

    def event_for(self, quote):
        return QuoteEvents.SUBMITTED if quote.requires_approval else QuoteEvents.APPROVED

    def message_for(self, quote):
        if quote.requires_approval:
            return ("Cotización enviada a aprobación: hay precios por debajo de lista. "
                    "La aprueba otra persona con permiso.")
        return "Cotización lista para enviar al cliente."


class ApproveQuoteUseCase(_TransitionUseCase):
    permissions = (QuotePermissions.APPROVE,)
    event = QuoteEvents.APPROVED
    done = "Cotización aprobada."

    def apply(self, quote, *, actor_user_id, note: str = "", **_):
        quote.approve(approver_user_id=actor_user_id, note=note or "")
        return note or ""


class ReturnQuoteToDraftUseCase(_TransitionUseCase):
    """Rechazo de la aprobación (quien aprueba) o corrección (quien la hizo)."""
    permissions = (QuotePermissions.EDIT, QuotePermissions.APPROVE)
    event = QuoteEvents.RETURNED_TO_DRAFT
    done = "La cotización regresó a borrador."

    def apply(self, quote, *, reason: str = "", **_):
        quote.return_to_draft(reason=reason or "")
        return reason


class SendQuoteUseCase(_TransitionUseCase):
    permissions = (QuotePermissions.SEND,)
    event = QuoteEvents.SENT
    done = "Cotización marcada como enviada al cliente."

    def apply(self, quote, *, today, **_):
        quote.send(today=today)
        return ""


class AcceptQuoteUseCase(_TransitionUseCase):
    permissions = (QuotePermissions.RESPOND,)
    event = QuoteEvents.ACCEPTED
    done = "El cliente aceptó la cotización. Ya puedes convertirla en pedido."

    def apply(self, quote, *, today, **_):
        quote.accept(today=today)
        return ""


class RejectQuoteUseCase(_TransitionUseCase):
    permissions = (QuotePermissions.RESPOND,)
    event = QuoteEvents.REJECTED
    done = "Rechazo del cliente registrado."

    def apply(self, quote, *, reason: str = "", **_):
        quote.reject(reason=reason or "")
        return reason


class CancelQuoteUseCase(_TransitionUseCase):
    permissions = (QuotePermissions.CANCEL,)
    event = QuoteEvents.CANCELLED
    done = "Cotización cancelada."

    def apply(self, quote, *, reason: str = "", **_):
        quote.cancel(reason=reason or "")
        return reason


class ReviseQuoteUseCase(_QuoteUseCase):
    """Nueva versión en borrador. Los precios de lista se vuelven a pedir a
    Precios (pudieron cambiar); un precio negociado se conserva."""

    def execute(self, connection, *, actor_user_id: str, quote_id: str, operation_id: str,
                valid_until, today: date | None = None) -> QuoteResult:
        try:
            self._auth.require(actor_user_id, QuotePermissions.CREATE)
            with QuotesUnitOfWork(connection) as uow:
                existing = uow.quotes.get_by_operation_id(operation_id)
                if existing is not None:
                    return QuoteResult.ok("Versión ya creada", entity_id=existing.id,
                                          operation_id=operation_id)
                old = self._load(uow, quote_id)
                number = f"{old.quote_number.split('/')[0]}/{old.revision + 1}"
                new = old.revise(quote_number=number, created_by_user_id=actor_user_id,
                                 valid_until=_date(valid_until), today=_today(today),
                                 operation_id=operation_id)
                pricing = self._pricing_factory(connection)
                for line in list(new.lines):
                    try:
                        product = pricing.product(
                            branch_id=new.branch_id, customer_id=new.customer_id,
                            product_id=line.product_id, quantity=line.quantity)
                    except QuoteValidationError:
                        new.lines.remove(line)  # ya no se vende: no se arrastra
                        continue
                    new.update_line(line.id, list_price=product.list_price,
                                    min_price=product.min_price)
                uow.quotes.save(old)
                uow.quotes.save(new)
                self._record(uow, new, QuoteEvents.REVISED, actor_user_id, operation_id,
                             detail=f"versión de {old.quote_number}")
                if old.status.value == "CANCELLED":
                    self._record(uow, old, QuoteEvents.CANCELLED, actor_user_id, operation_id,
                                 detail=old.cancel_reason)
        except QuotesDomainError as exc:
            return _fail(exc, operation_id)
        return QuoteResult.ok(f"Nueva versión {new.quote_number} en borrador",
                              entity_id=new.id, operation_id=operation_id)


class ExpireQuotesUseCase:
    """Vence las cotizaciones cuya vigencia pasó (sistema; la corre el ciclo de fondo)."""

    BATCH = 500

    def execute(self, connection, *, today: date | None = None) -> int:
        day = _today(today)
        expired = 0
        with QuotesUnitOfWork(connection) as uow:
            for quote in uow.quotes.list_expirable(day, limit=self.BATCH):
                quote.expire(today=day)
                uow.quotes.save(quote)
                uow.audit.record(quote_id=quote.id, action=QuoteEvents.EXPIRED,
                                 actor_user_id="SYSTEM",
                                 detail=f"vigencia {quote.valid_until.isoformat()}")
                expired += 1
        return expired
