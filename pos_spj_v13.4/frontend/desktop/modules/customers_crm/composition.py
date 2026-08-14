"""Composition root for the Clientes y CRM desktop module.

This is the ONLY place that wires a real, live ``connection``/
``session_context`` into query services, use cases and the presenter. Takes
only plain arguments — never the app's whole dependency bundle, whatever it
may be called elsewhere in this codebase — enforced by a CRM-1 guardrail
that scans every file under this package for that broader-bundle shape.
The outer unwrapping step (pulling a raw db handle off that bundle) lives
OUTSIDE this package, in ``modulos/clientes_crm.py`` — mirrors
``frontend/desktop/modules/finance/finance_routes.py``'s split, except
finance has no such guardrail and keeps both layers in one file; this
package can't.
"""

from __future__ import annotations

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.data_scope import CRMDataScopeResolver
from backend.application.crm.queries.customer_dashboard_query_service import (
    CustomerDashboardQueryService,
)
from backend.application.crm.queries.lead_directory_query_service import (
    LeadDirectoryQueryService,
)
from backend.application.crm.queries.opportunity_directory_query_service import (
    OpportunityDirectoryQueryService,
)
from backend.application.customer_service.queries.service_case_query_service import (
    ServiceCaseQueryService,
)
from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.data_scope import CustomerDataScopeResolver
from backend.application.customers.queries.customer_360_query_service import (
    Customer360QueryService,
)
from backend.application.customers.queries.customer_profile_query_service import (
    CustomerProfileQueryService,
)
from backend.application.customers.session_authorization import (
    CustomerSessionPermissionChecker,
)
from backend.application.customers.use_cases.lifecycle_use_cases import (
    CreateCustomerUseCase,
    UpdateCustomerUseCase,
)
from frontend.desktop.modules.customers_crm.customers_crm_presenter import (
    CustomerCrmPresenter,
)


def build_customers_crm_presenter(connection, session_context=None) -> CustomerCrmPresenter:
    checker = CustomerSessionPermissionChecker(session_context)
    customer_auth = CustomerAuthorizationPolicy(checker)
    crm_auth = CRMAuthorizationPolicy(checker)
    customer_scope_resolver = CustomerDataScopeResolver(checker)
    crm_scope_resolver = CRMDataScopeResolver(checker)

    query_services = {
        "dashboard": CustomerDashboardQueryService(connection, crm_scope_resolver, crm_auth),
        "customers_directory": CustomerProfileQueryService(connection, customer_scope_resolver),
        "leads_directory": LeadDirectoryQueryService(connection, crm_scope_resolver, crm_auth),
        "opportunities_directory": OpportunityDirectoryQueryService(
            connection, crm_scope_resolver),
        "cases_directory": ServiceCaseQueryService(connection, crm_scope_resolver, crm_auth),
        "customer_360": Customer360QueryService(
            connection, customer_scope_resolver, crm_scope_resolver, customer_auth, crm_auth),
    }

    def _create_customer_handler(**kwargs):
        run = CreateCustomerUseCase(customer_auth).execute
        return run(connection, **kwargs)

    def _update_customer_handler(**kwargs):
        run = UpdateCustomerUseCase(customer_auth).execute
        return run(connection, **kwargs)

    command_handlers = {
        "create_customer": _create_customer_handler,
        "update_customer": _update_customer_handler,
    }

    return CustomerCrmPresenter(
        session_context=session_context,
        query_services=query_services,
        command_handlers=command_handlers,
    )


def create_customers_crm_view(connection, session_context=None, parent=None):
    """Factory used by ``modulos/clientes_crm.py``. Never receives the
    container itself — only what it needs, already unwrapped."""
    from frontend.desktop.modules.customers_crm.customers_crm_workspace import (
        CustomersCrmWorkspace,
    )

    presenter = build_customers_crm_presenter(connection, session_context)
    return CustomersCrmWorkspace(presenter, parent)
