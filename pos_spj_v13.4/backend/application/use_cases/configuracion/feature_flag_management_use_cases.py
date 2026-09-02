"""Use cases for the "Flags" origination side of the Feature Flags
section — closes the gap `feature_flag_change_request_use_cases.py`
(Approve/Reject/Apply) leaves open: nothing previously called
`FeatureFlag.create()` or `FeatureFlagChangeRequest.create()` outside of
tests, so the approval screen could never have anything real to act on.
Same thin-orchestration shape as `notification_management_use_cases.py`.

`CreateFeatureFlagUseCase` checks `code` occupancy BEFORE inserting
(never lets a raw `IntegrityError` reach the UI) — same discipline
`CreateNotificationTemplateUseCase` (SET-20) already established.
"""

from __future__ import annotations

from enum import Enum

from backend.domain.feature_flags.entities.feature_flag import FeatureFlag
from backend.domain.feature_flags.entities.feature_flag_change_request import FeatureFlagChangeRequest
from backend.domain.feature_flags.enums import FeatureFlagScopeType
from backend.domain.feature_flags.exceptions import (
    FeatureFlagCodeOccupiedError,
    FeatureFlagNotFoundError,
)
from backend.infrastructure.db.repositories.feature_flags.feature_flag_change_request_repository import (
    SqliteFeatureFlagChangeRequestRepository,
)
from backend.infrastructure.db.repositories.feature_flags.feature_flag_repository import (
    SqliteFeatureFlagRepository,
)


class FeatureFlagStatusAction(str, Enum):
    ACTIVATE = "ACTIVATE"
    DEACTIVATE = "DEACTIVATE"


class CreateFeatureFlagUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._flags = SqliteFeatureFlagRepository(connection)

    def execute(
        self, *, code: str, name: str, description: str = "", default_enabled: bool = False,
    ) -> FeatureFlag:
        if self._flags.get_by_code(code) is not None:
            raise FeatureFlagCodeOccupiedError(f"Ya existe un feature flag con código {code!r}")
        flag = FeatureFlag.create(
            code=code, name=name, description=description, default_enabled=default_enabled,
        )
        self._flags.save(flag)
        self._conn.commit()
        return flag


class UpdateFeatureFlagUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._flags = SqliteFeatureFlagRepository(connection)

    def execute(
        self, *, flag_id: str, name: str, description: str = "", default_enabled: bool = False,
    ) -> FeatureFlag:
        flag = self._flags.get(flag_id)
        if flag is None:
            raise FeatureFlagNotFoundError(f"Feature flag {flag_id} no encontrado")
        flag.update_details(name=name, description=description, default_enabled=default_enabled)
        self._flags.save(flag)
        self._conn.commit()
        return flag


class ChangeFeatureFlagStatusUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._flags = SqliteFeatureFlagRepository(connection)

    def execute(self, *, flag_id: str, action: FeatureFlagStatusAction) -> FeatureFlag:
        flag = self._flags.get(flag_id)
        if flag is None:
            raise FeatureFlagNotFoundError(f"Feature flag {flag_id} no encontrado")

        if action is FeatureFlagStatusAction.ACTIVATE:
            flag.activate()
        elif action is FeatureFlagStatusAction.DEACTIVATE:
            flag.deactivate()

        self._flags.save(flag)
        self._conn.commit()
        return flag


class RequestFeatureFlagChangeUseCase:
    def __init__(self, connection) -> None:
        self._conn = connection
        self._flags = SqliteFeatureFlagRepository(connection)
        self._requests = SqliteFeatureFlagChangeRequestRepository(connection)

    def execute(
        self, *, flag_id: str, scope_type: FeatureFlagScopeType | str, scope_id: str | None,
        proposed_enabled: bool, requested_by_user_id: str, proposed_rollout_percentage: int = 100,
    ) -> FeatureFlagChangeRequest:
        if self._flags.get(flag_id) is None:
            raise FeatureFlagNotFoundError(f"Feature flag {flag_id} no encontrado")
        request = FeatureFlagChangeRequest.create(
            flag_id=flag_id, scope_type=FeatureFlagScopeType(scope_type), scope_id=scope_id,
            proposed_enabled=proposed_enabled, requested_by_user_id=requested_by_user_id,
            proposed_rollout_percentage=proposed_rollout_percentage,
        )
        self._requests.save(request)
        self._conn.commit()
        return request
