"""Use cases for the "Feature Flags" section of the Configuración
workspace — UI/UX phase. Thin orchestration over
`backend/domain/feature_flags/` (SET-21): load, apply domain rule, save.
No business logic lives here (that's `FeatureFlagChangeRequest.approve/
reject/apply` and `feature_flag_approval_policy.assert_can_approve`) —
these use cases only wire persistence around it, same division of labor
`CreateTransferRequestCommand`/`CreateTransferRequestUseCase` already
establish for Transfers.
"""

from __future__ import annotations

from backend.domain.feature_flags.entities.feature_flag_change_request import FeatureFlagChangeRequest
from backend.domain.feature_flags.entities.feature_flag_rule import FeatureFlagRule
from backend.domain.feature_flags.exceptions import FeatureFlagNotFoundError
from backend.domain.feature_flags.policies.feature_flag_approval_policy import assert_can_approve
from backend.infrastructure.db.repositories.feature_flags.feature_flag_change_request_repository import (
    SqliteFeatureFlagChangeRequestRepository,
)
from backend.infrastructure.db.repositories.feature_flags.feature_flag_rule_repository import (
    SqliteFeatureFlagRuleRepository,
)


class ApproveFeatureFlagChangeRequestUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._requests = SqliteFeatureFlagChangeRequestRepository(connection)

    def execute(self, *, request_id: str, approver_user_id: str) -> FeatureFlagChangeRequest:
        request = self._requests.get(request_id)
        if request is None:
            raise FeatureFlagNotFoundError(f"Solicitud {request_id} no encontrada")
        assert_can_approve(request, approver_user_id=approver_user_id)
        request.approve(approved_by_user_id=approver_user_id)
        self._requests.save(request)
        self._conn.commit()
        return request


class RejectFeatureFlagChangeRequestUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._requests = SqliteFeatureFlagChangeRequestRepository(connection)

    def execute(self, *, request_id: str, reason: str) -> FeatureFlagChangeRequest:
        request = self._requests.get(request_id)
        if request is None:
            raise FeatureFlagNotFoundError(f"Solicitud {request_id} no encontrada")
        request.reject(reason=reason)
        self._requests.save(request)
        self._conn.commit()
        return request


class ApplyFeatureFlagChangeRequestUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._requests = SqliteFeatureFlagChangeRequestRepository(connection)
        self._rules = SqliteFeatureFlagRuleRepository(connection)

    def execute(self, *, request_id: str) -> FeatureFlagRule:
        request = self._requests.get(request_id)
        if request is None:
            raise FeatureFlagNotFoundError(f"Solicitud {request_id} no encontrada")
        rule = request.apply()
        self._rules.save(rule)
        self._requests.save(request)
        self._conn.commit()
        return rule
