"""Presenter bridge between the Clientes y CRM desktop UI and backend
services (CRM-14).

Mirrors ``frontend/desktop/modules/cash_register/cash_register_presenter.py``'s
thin-bridge shape: the workspace/pages ask this presenter for capabilities
and named dependencies, never touching a repository or raw SQL themselves,
and never receiving the whole app's dependency container wholesale
(enforced by the CRM-1 UI guardrails). Query services and
command handlers are intentionally EMPTY dicts by default — CRM-14 only
builds the routing/navigation shell; wiring each of the ~50 already-built
QueryServices/UseCases from CRM-3..13 to a page is each later phase's own
job as that page gets built, not fabricated here ahead of need.
"""

from __future__ import annotations

from collections.abc import Callable

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
    ) -> None:
        self._session = session_context
        self._query_services = dict(query_services or {})
        self._use_cases = dict(use_cases or {})
        self._command_handlers = dict(command_handlers or {})

    def can(self, permission: str) -> bool:
        checker = getattr(self._session, "tiene_permiso", None)
        return bool(callable(checker) and checker(permission))

    def capabilities(self) -> CustomerCrmCapabilities:
        return resolve_customer_crm_capabilities(self.can)

    def query_service(self, key: str) -> object | None:
        return self._query_services.get(key)

    def use_case(self, key: str) -> object | None:
        return self._use_cases.get(key)
