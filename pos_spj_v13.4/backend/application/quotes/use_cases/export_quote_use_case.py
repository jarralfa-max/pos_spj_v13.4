"""ExportQuotePdfUseCase — el documento que se le entrega al cliente (CRM-43).

Sólo de una cotización aprobada en adelante: un borrador o una por aprobar
todavía puede tener precios que nadie autorizó. Queda en la auditoría.
"""

from __future__ import annotations

from backend.application.quotes.authorization import QuotesAuthorizationPolicy
from backend.application.quotes.permissions import QuotePermissions
from backend.application.quotes.result import QuoteResult
from backend.domain.quotes.enums import QuoteStatus
from backend.domain.quotes.events import QuoteEvents
from backend.domain.quotes.exceptions import (
    InvalidQuoteStateError,
    QuoteNotFoundError,
    QuotesDomainError,
)
from backend.infrastructure.db.repositories.quotes.unit_of_work import QuotesUnitOfWork

_PRINTABLE = (QuoteStatus.APPROVED, QuoteStatus.SENT, QuoteStatus.ACCEPTED,
              QuoteStatus.CONVERTED)


def _money(value) -> str:
    return f"${value:,.2f}"


def _qty(value) -> str:
    text = f"{value:,.3f}".rstrip("0").rstrip(".")
    return text or "0"


class ExportQuotePdfUseCase:
    def __init__(self, authorization: QuotesAuthorizationPolicy | None = None, *,
                 renderer=None, user_name=None) -> None:
        self._auth = authorization or QuotesAuthorizationPolicy()
        self._renderer = renderer
        self._user_name = user_name or (lambda _uid: "")

    def execute(self, connection, *, actor_user_id: str, quote_id: str, path: str,
                operation_id: str) -> QuoteResult:
        try:
            self._auth.require(actor_user_id, QuotePermissions.EXPORT)
            with QuotesUnitOfWork(connection) as uow:
                quote = uow.quotes.get(quote_id)
                if quote is None:
                    raise QuoteNotFoundError("La cotización no existe.")
                if quote.status not in _PRINTABLE:
                    raise InvalidQuoteStateError(
                        "Sólo se imprime una cotización aprobada: un borrador o una por "
                        "aprobar puede llevar precios que nadie autorizó.")
                document = self._document(connection, quote)
                renderer = self._renderer
                if renderer is None:
                    from backend.infrastructure.quotes.quote_pdf_renderer import (
                        render_quote_pdf,
                    )
                    renderer = render_quote_pdf
                renderer(document, path)
                uow.audit.record(quote_id=quote.id, action=QuoteEvents.EXPORTED,
                                 actor_user_id=actor_user_id, detail=path,
                                 operation_id=operation_id)
        except QuotesDomainError as exc:
            return QuoteResult.fail(str(exc), exc.code, operation_id=operation_id)
        except OSError as exc:
            return QuoteResult.fail(f"No se pudo escribir el archivo: {exc}", "IO_ERROR",
                                    operation_id=operation_id)
        return QuoteResult.ok(f"PDF guardado en {path}", entity_id=quote_id,
                              operation_id=operation_id, path=path)

    def _document(self, connection, quote):
        from backend.infrastructure.db.repositories.customers.unit_of_work import (
            CustomerUnitOfWork,
        )
        from backend.infrastructure.db.repositories.settings.company_profile_repository import (
            SqliteCompanyProfileRepository,
        )
        from backend.infrastructure.quotes.quote_pdf_renderer import (
            QuoteDocument,
            QuoteDocumentLine,
        )
        from backend.shared.business_dates import local_business_date

        companies = SqliteCompanyProfileRepository(connection).list_active()
        company = companies[0] if companies else None
        company_name = ((company.commercial_name or company.legal_name) if company else "")
        company_lines = ()
        if company is not None:
            company_lines = tuple(x for x in (
                company.legal_name if company.commercial_name else "",
                f"RFC {company.tax_id}" if company.tax_id else "", company.address,
                " · ".join(x for x in (company.phone, company.email) if x)) if x)
        customers = CustomerUnitOfWork(connection)
        customer = customers.customers.get(quote.customer_id)
        tax = customers.tax_profiles.get_for_customer(quote.customer_id)
        customer_lines = tuple(x for x in (
            (tax.legal_name if tax and tax.legal_name else ""),
            (f"RFC {tax.tax_identifier}" if tax and tax.tax_identifier else ""),
            (customer.customer_number if customer and getattr(customer, "customer_number", "")
             else "")) if x)
        number = quote.quote_number + (f" (versión {quote.revision})" if quote.revision > 1
                                       else "")
        return QuoteDocument(
            company_name=company_name or "Cotización", company_lines=company_lines,
            number=number,
            issued_on=local_business_date(quote.submitted_at or quote.created_at
                                          ).strftime("%d/%m/%Y"),
            valid_until=quote.valid_until.strftime("%d/%m/%Y"),
            customer_name=customer.display_name if customer else quote.customer_id,
            customer_lines=customer_lines,
            lines=tuple(QuoteDocumentLine(
                code=line.product_code, description=line.description,
                quantity=_qty(line.quantity), unit=line.unit_code,
                unit_price=_money(line.unit_price), amount=_money(line.line_total))
                for line in quote.lines),
            list_subtotal=_money(quote.list_subtotal),
            discount_total=_money(quote.discount_total), total=_money(quote.total),
            currency=quote.currency, notes=quote.notes,
            prepared_by=self._user_name(quote.created_by_user_id))
