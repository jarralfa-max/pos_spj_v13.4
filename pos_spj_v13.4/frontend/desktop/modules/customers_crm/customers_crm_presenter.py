"""Presenter bridge between the Clientes y CRM desktop UI and backend
services (CRM-14).

Mirrors ``frontend/desktop/modules/cash_register/cash_register_presenter.py``'s
thin-bridge shape: the workspace/pages ask this presenter for capabilities
and named dependencies, never touching a repository or raw SQL themselves,
and never receiving the whole app's dependency container wholesale
(enforced by the CRM-1 UI guardrails). Query services and
command handlers are intentionally EMPTY dicts by default — CRM-14 only
built the routing/navigation shell; wiring each of the ~50 already-built
QueryServices/UseCases from CRM-3..13 to a page is each later phase's own
job as that page gets built, not fabricated here ahead of need.

CRM-15 added ``dashboard()`` — a named presenter method wrapping
``CustomerDashboardQueryService`` (looked up from ``query_services["dashboard"]``,
never imported/constructed here), same "presenter exposes a named business
method, not a raw QueryService" shape as
``frontend/desktop/modules/purchasing/pages/procurement_dashboard_page.py``'s
``presenter.analytics_kpis()``. Returns an empty, all-zero
``CustomerDashboardView`` when nothing is wired yet (no live DB connection
plugged into ``query_services`` — that wiring is the composition root's job,
still not built as of CRM-15, same deferred-top-level-registration decision
CRM-14 already documented) rather than raising — a page must always have
something safe to render.

CRM-16 adds four directory methods (``customers_directory()``/
``leads_directory()``/``opportunities_directory()``/``cases_directory()``),
same lookup-and-degrade-to-empty shape. None of CRM-3/4/5/7's
``list_directory()`` methods take a search/status filter — adding one would
mean touching each bounded context's repository layer across four separate
packages, out of proportion for a "Directorios" phase whose own name is
about *listing*, not extending four other phases' read paths. Instead this
presenter fetches the caller's already-scoped page (``limit=200``, same
default every ``list_directory()`` already uses) and filters by search
text/status in plain Python — a display refinement over already-authorized
data, not a recomputed business metric, so it does not violate "la UI no
calcula KPIs" (§90) the way inventing a new count or total would.

CRM-17 adds ``customer_360()`` wrapping ``Customer360QueryService``
(``query_services["customer_360"]``). Unlike ``dashboard()``, it does NOT
degrade to an empty DTO when unwired — ``Customer360View.profile`` has no
sensible default (it's a real customer's identity, not a zeroable KPI set),
so an unwired/failed lookup raises instead; ``CustomerProfilePage.reload()``
already catches any exception and shows an error state, the same contract
every CRM-15/16 page already relies on.

CRM-18 adds ``create_customer()`` — the first WRITE this presenter exposes
(every prior method is read-only). Unlike the read methods, it goes through
``command_handlers["create_customer"]`` rather than ``query_services``:
running ``CreateCustomerUseCase`` needs a live sqlite connection as its
first positional argument (every use case in this codebase does — the
Unit-of-Work-per-call convention), and this presenter deliberately never
holds one itself, matching its own "never touches SQL/a connection
directly" contract. A command handler is a pre-bound callable the
composition root closes over the connection with — the exact
``command_handlers: dict[str, Callable[..., object]]`` slot CRM-14 already
declared in ``__init__`` and left unused until now, mirroring
``CashRegisterPresenter``'s own established command-handler pattern.

This phase also adds ``update_customer()`` — same shape as
``create_customer()`` (a ``command_handlers["update_customer"]`` lookup,
degrading to ``CustomerResult.fail(..., "NOT_WIRED")``), and the module's
first real composition root
(``frontend/desktop/modules/customers_crm/composition.py``), wiring both
handlers to ``CreateCustomerUseCase``/``UpdateCustomerUseCase`` for the
first time against a real, live connection — previously only exercised via
fakes in tests.
"""

from __future__ import annotations

from collections.abc import Callable

from backend.application.crm.data_scope import CRMScopeContext
from backend.application.crm.queries.customer_dashboard_query_service import (
    CustomerDashboardView,
)
from backend.application.customers.data_scope import CustomerScopeContext
from backend.application.customers.queries.customer_360_query_service import Customer360View
from backend.application.customers.result import CustomerResult
from backend.shared.ids import new_uuid
from frontend.desktop.modules.customers_crm.capability_resolver import (
    resolve_customer_crm_capabilities,
)
from frontend.desktop.modules.customers_crm.view_models import CustomerCrmCapabilities


class CustomerCrmPresenter:
    def __init__(
        self, *, session_context,
        query_services: dict[str, object] | None = None,
        use_cases: dict[str, object] | None = None,
        command_handlers: dict[str, Callable[..., object]] | None = None,
        team_member_ids: tuple[str, ...] = (),
    ) -> None:
        self._session = session_context
        self._query_services = dict(query_services or {})
        self._use_cases = dict(use_cases or {})
        self._command_handlers = dict(command_handlers or {})
        self._team_member_ids = team_member_ids

    def can(self, permission: str) -> bool:
        checker = getattr(self._session, "tiene_permiso", None)
        return bool(callable(checker) and checker(permission))

    def capabilities(self) -> CustomerCrmCapabilities:
        return resolve_customer_crm_capabilities(self.can)

    def query_service(self, key: str) -> object | None:
        return self._query_services.get(key)

    def use_case(self, key: str) -> object | None:
        return self._use_cases.get(key)

    def command_handler(self, key: str) -> Callable[..., object] | None:
        return self._command_handlers.get(key)

    def current_user_id(self) -> str:
        return str(getattr(self._session, "user_id", "") or "")

    def dashboard(self) -> CustomerDashboardView:
        service = self.query_service("dashboard")
        if service is None:
            return CustomerDashboardView()
        return service.get_dashboard(
            actor_user_id=self.current_user_id(), team_member_ids=self._team_member_ids)

    def customers_directory(self, *, search: str = "", status: str | None = None) -> list:
        service = self.query_service("customers_directory")
        if service is None:
            return []
        context = CustomerScopeContext(
            user_id=self.current_user_id(), team_member_ids=self._team_member_ids)
        customers = service.list_directory(context, limit=200)
        return self._filtered(
            customers, search=search, status=status,
            text_fields=lambda c: (c.display_name, c.legal_name, str(c.code)))

    def leads_directory(self, *, search: str = "", status: str | None = None) -> list:
        service = self.query_service("leads_directory")
        if service is None:
            return []
        context = CRMScopeContext(
            user_id=self.current_user_id(), team_member_ids=self._team_member_ids)
        leads = service.list_directory(context, limit=200)
        return self._filtered(
            leads, search=search, status=status,
            text_fields=lambda lead: (lead.display_name, lead.company_name))

    def opportunities_directory(self, *, search: str = "", status: str | None = None) -> list:
        service = self.query_service("opportunities_directory")
        if service is None:
            return []
        context = CRMScopeContext(
            user_id=self.current_user_id(), team_member_ids=self._team_member_ids)
        opportunities = service.list_directory(context, limit=200)
        return self._filtered(
            opportunities, search=search, status=status, text_fields=lambda o: (o.name,))

    def cases_directory(self, *, search: str = "", status: str | None = None) -> list:
        service = self.query_service("cases_directory")
        if service is None:
            return []
        context = CRMScopeContext(
            user_id=self.current_user_id(), team_member_ids=self._team_member_ids)
        cases = service.list_directory(context, limit=200)
        return self._filtered(
            cases, search=search, status=status,
            text_fields=lambda case: (case.subject, str(case.code)))

    def customer_360(self, customer_id: str) -> Customer360View:
        service = self.query_service("customer_360")
        if service is None:
            raise RuntimeError(
                "El expediente del cliente no está disponible: falta la conexión al backend.")
        return service.get_360(
            customer_id, actor_user_id=self.current_user_id(),
            team_member_ids=self._team_member_ids)

    def create_customer(
        self, *, display_name: str, customer_type: str, tax_identifier: str = "",
        phone_e164: str = "", email: str = "",
    ) -> CustomerResult:
        handler = self.command_handler("create_customer")
        if handler is None:
            return CustomerResult.fail(
                "El alta de clientes no está disponible: falta la conexión al backend.",
                "NOT_WIRED")
        return handler(
            actor_user_id=self.current_user_id(), display_name=display_name,
            operation_id=new_uuid(), customer_type=customer_type,
            tax_identifier=tax_identifier or None, phone_e164=phone_e164 or None,
            email=email or None)

    def update_customer(
        self, customer_id: str, *, display_name: str | None = None,
        legal_name: str | None = None, commercial_name: str | None = None,
        source: str | None = None,
    ) -> CustomerResult:
        """Only the fields ``UpdateCustomerUseCase`` actually supports today
        (``backend/application/customers/use_cases/lifecycle_use_cases.py``)
        — no tax_identifier/phone_e164/email edit path exists yet in this
        bounded context, unlike ``create_customer()``'s wider field set."""
        handler = self.command_handler("update_customer")
        if handler is None:
            return CustomerResult.fail(
                "La edición de clientes no está disponible: falta la conexión al backend.",
                "NOT_WIRED")
        return handler(
            actor_user_id=self.current_user_id(), customer_id=customer_id,
            operation_id=new_uuid(), display_name=display_name,
            legal_name=legal_name, commercial_name=commercial_name, source=source)

    @staticmethod
    def _filtered(entities, *, search: str, status: str | None, text_fields) -> list:
        result = entities
        if status:
            result = [e for e in result if e.status.value == status]
        needle = search.strip().lower()
        if needle:
            result = [e for e in result
                     if any(needle in (field or "").lower() for field in text_fields(e))]
        return result
