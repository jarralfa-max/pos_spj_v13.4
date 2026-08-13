"""CustomerDataRetentionPolicy administration (§44: "plazos nunca
hardcodeados"). Gated by ``SETTINGS_MANAGE``/``SETTINGS_VIEW`` — the
existing generic module-configuration permissions (CRM-2) are the right
fit here (retention policy is configuration, not a case/request workflow),
unlike CRM-5's CRMStageDefinition, where no such fitting permission existed
at all and CRUD was deliberately left unbuilt.
"""

from __future__ import annotations

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customer_privacy.result import CustomerPrivacyResult
from backend.domain.customer_privacy.entities.customer_data_retention_policy import (
    CustomerDataRetentionPolicy,
)
from backend.domain.customer_privacy.exceptions import CustomerPrivacyDomainError
from backend.domain.customers.enums import CustomerStatus, CustomerType
from backend.domain.customers.exceptions import CustomerDomainError
from backend.infrastructure.db.repositories.customer_privacy.unit_of_work import (
    CustomerPrivacyUnitOfWork,
)


class CreateDataRetentionPolicyUseCase:
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CustomerAuthorizationPolicy()

    def execute(
        self, connection, *, actor_user_id: str, code: str, name: str, data_category: str,
        retention_days: int, operation_id: str, legal_basis: str = "",
        customer_type: str | None = None, customer_status: str | None = None,
    ) -> CustomerPrivacyResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.SETTINGS_MANAGE)
        except CustomerDomainError as exc:
            return CustomerPrivacyResult.fail(str(exc), "PERMISSION_DENIED",
                                              operation_id=operation_id)
        with CustomerPrivacyUnitOfWork(connection) as uow:
            try:
                policy = CustomerDataRetentionPolicy.create(
                    code, name, data_category, retention_days, legal_basis=legal_basis,
                    customer_type=CustomerType(customer_type) if customer_type else None,
                    customer_status=CustomerStatus(customer_status) if customer_status else None)
            except (CustomerPrivacyDomainError, ValueError) as exc:
                return CustomerPrivacyResult.fail(str(exc), "VALIDATION",
                                                  operation_id=operation_id)
            uow.retention_policies.save(policy)
        return CustomerPrivacyResult.ok("Política de retención creada", entity_id=policy.id,
                                        operation_id=operation_id, code=policy.code)
