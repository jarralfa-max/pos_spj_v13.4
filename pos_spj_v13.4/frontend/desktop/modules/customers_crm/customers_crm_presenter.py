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

from backend.application.crm.queries.customer_dashboard_query_service import (
    CustomerDashboardView,
)
from backend.application.customers.queries.customer_360_query_service import Customer360View
from backend.application.customers.read_context import CrmReadContext
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
        address_search_factory: Callable[[], object] | None = None,
        readers: dict[str, Callable[..., object]] | None = None,
    ) -> None:
        self._session = session_context
        self._readers = dict(readers or {})
        self._user_cache: list[tuple[str, str]] | None = None
        self._address_search_factory = address_search_factory
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

    # -- CRM-43: comandos y lecturas genéricos ---------------------------------
    def branch_id(self) -> str | None:
        branch = str(getattr(self._session, "active_branch_id", "") or "").strip()
        return branch or None

    def read_context(self) -> CrmReadContext:
        return CrmReadContext(user_id=self.current_user_id(), branch_id=self.branch_id(),
                              team_member_ids=self._team_member_ids)

    def has_reader(self, name: str) -> bool:
        return name in self._readers

    def read(self, reader_name: str, /, **kwargs):
        """Lectura cableada por la raíz de composición (nunca SQL aquí)."""
        reader = self._readers.get(reader_name)
        if reader is None:
            raise RuntimeError(f"La consulta «{reader_name}» no está disponible.")
        return reader(self.read_context(), **kwargs)

    def run(self, command: str, /, **kwargs):
        """Ejecuta un caso de uso cableado. Inyecta el actor y una
        ``operation_id`` nueva (idempotencia por intento) si no vienen.
        ``command`` es posicional: varios casos de uso reciben un campo
        ``name`` (segmentos, territorios, etapas…)."""
        handler = self._command_handlers.get(command)
        if handler is None:
            return CustomerResult.fail(
                "La operación no está disponible: falta la conexión al backend.", "NOT_WIRED")
        kwargs.setdefault("actor_user_id", self.current_user_id())
        kwargs.setdefault("operation_id", new_uuid())
        return handler(**kwargs)

    def users(self) -> list[tuple[str, str]]:
        """``(user_id, nombre)`` de los usuarios activos, para asignar."""
        if self._user_cache is None:
            try:
                self._user_cache = [(u.user_id, u.name) for u in self.read("assignable_users")]
            except Exception:  # noqa: BLE001 — sin lector, no hay a quién asignar
                self._user_cache = []
        return list(self._user_cache)

    def user_name(self, user_id: str | None) -> str:
        if not user_id:
            return "Sin asignar"
        return dict(self.users()).get(user_id, "Otro usuario")

    def customer_names(self, customer_ids) -> dict[str, str]:
        ids = [i for i in customer_ids if i]
        if not ids or not self.has_reader("customer_names"):
            return {}
        return self.read("customer_names", customer_ids=ids)

    def customer_search_options(self, query: str) -> list:
        """Proveedor de ``CustomerSearchBox``: busca por nombre, código, teléfono…"""
        from frontend.desktop.components.search_selector import SearchOption

        if len(query.strip()) < 2 or not self.has_reader("customer_lookup"):
            return []
        return [SearchOption(id=r.customer_id, label=r.display_name,
                             subtitle=r.code) for r in self.read("customer_lookup", query=query)]

    def dashboard(self) -> CustomerDashboardView:
        service = self.query_service("dashboard")
        if service is None:
            return CustomerDashboardView()
        return service.get_dashboard(
            actor_user_id=self.current_user_id(), team_member_ids=self._team_member_ids)

    def customer_360(self, customer_id: str) -> Customer360View:
        service = self.query_service("customer_360")
        if service is None:
            raise RuntimeError(
                "El expediente del cliente no está disponible: falta la conexión al backend.")
        return service.get_360(
            customer_id, actor_user_id=self.current_user_id(),
            team_member_ids=self._team_member_ids, branch_id=self.branch_id())

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

    def customer_birthday(self, customer_id: str):
        """Cumpleaños registrado (con consentimiento) o None (2026-10-03)."""
        consulta = self.query_service("customer_birthday")
        return consulta(customer_id) if consulta is not None else None

    def set_customer_birthday(self, customer_id: str, *, month: int | None, day: int | None,
                              year: int | None, consent: bool) -> CustomerResult:
        handler = self.command_handler("set_customer_birthday")
        if handler is None:
            return CustomerResult.fail("El cumpleaños no está disponible.", "NOT_WIRED")
        return handler(actor_user_id=self.current_user_id(), customer_id=customer_id,
                       operation_id=new_uuid(), month=month, day=day, year=year,
                       consent=consent)

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

    def address_search_service(self):
        """Servicio estándar de direcciones (Configuración → Integraciones).
        `None` si no está inyectado o falla: se captura a mano."""
        if self._address_search_factory is None:
            return None
        try:
            return self._address_search_factory()
        except Exception:
            import logging
            logging.getLogger("spj.customers_crm.presenter").exception(
                "No se pudo preparar la búsqueda de direcciones")
            return None

    def can_add_address(self) -> bool:
        """Para habilitar el botón. Ocultar no es seguridad —el caso de uso
        revalida con `require()`— pero ofrecer una acción que va a denegarse
        es peor."""
        from backend.application.customers.permissions import CustomerPermissions
        return self.can(CustomerPermissions.ADDRESS_CREATE)

    def add_customer_address(
        self, customer_id: str, *, address, address_type: str, is_default: bool = False,
    ) -> CustomerResult:
        """Alta de dirección desde la ficha, con lo que devuelve `AddressInput`.

        Las coordenadas sólo viajan si vienen de un proveedor de mapas: si el
        usuario corrigió a mano lo que ubica la dirección, el componente ya las
        descartó y aquí llegan vacías.
        """
        handler = self.command_handler("add_address")
        if handler is None:
            return CustomerResult.fail(
                "El alta de direcciones no está disponible: falta la conexión al backend.",
                "NOT_WIRED")
        return handler(
            actor_user_id=self.current_user_id(), customer_id=customer_id,
            operation_id=new_uuid(), address_type=address_type,
            street=address.street, external_number=address.exterior_number,
            internal_number=address.interior_number, neighborhood=address.neighborhood,
            postal_code=address.postal_code, municipality=address.municipality,
            state=address.state, country=address.country_code,
            references=address.references,
            latitude=address.latitude if address.is_geocoded else None,
            longitude=address.longitude if address.is_geocoded else None,
            is_default=bool(is_default))
