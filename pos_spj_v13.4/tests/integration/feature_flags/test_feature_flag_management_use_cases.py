"""SET-21 repegado — CreateFeatureFlagUseCase/UpdateFeatureFlagUseCase/
ChangeFeatureFlagStatusUseCase/RequestFeatureFlagChangeUseCase against a
real (in-memory) SQLite born-clean schema (migration 221). These close
the origination gap: before this round nothing called `FeatureFlag
.create()`/`FeatureFlagChangeRequest.create()` outside of tests, so the
existing Approve/Reject/Apply use cases could never have anything real
to act on.
"""

from __future__ import annotations

import pytest

from backend.domain.feature_flags.enums import FeatureFlagScopeType
from backend.domain.feature_flags.exceptions import (
    FeatureFlagCodeOccupiedError,
    FeatureFlagNotFoundError,
    FeatureFlagsInvalidValueError,
)
from backend.application.use_cases.configuracion.feature_flag_management_use_cases import (
    ChangeFeatureFlagStatusUseCase,
    CreateFeatureFlagUseCase,
    FeatureFlagStatusAction,
    RequestFeatureFlagChangeUseCase,
    UpdateFeatureFlagUseCase,
)
from backend.infrastructure.db.repositories.feature_flags.feature_flag_change_request_repository import (
    SqliteFeatureFlagChangeRequestRepository,
)
from backend.infrastructure.db.repositories.feature_flags.feature_flag_repository import (
    SqliteFeatureFlagRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


class TestCreateFeatureFlagUseCase:
    def test_creates_and_persists(self, conn):
        uc = CreateFeatureFlagUseCase(conn)
        flag = uc.execute(code="delivery_auto_asign", name="Auto-asignación", default_enabled=True)
        assert SqliteFeatureFlagRepository(conn).get(flag.id) is not None
        assert flag.default_enabled is True

    def test_rejects_duplicate_code(self, conn):
        uc = CreateFeatureFlagUseCase(conn)
        uc.execute(code="dup_code", name="A")
        with pytest.raises(FeatureFlagCodeOccupiedError):
            uc.execute(code="dup_code", name="B")


class TestUpdateFeatureFlagUseCase:
    def test_updates_persisted_fields(self, conn):
        flag = CreateFeatureFlagUseCase(conn).execute(code="f1", name="Original")
        updated = UpdateFeatureFlagUseCase(conn).execute(
            flag_id=flag.id, name="Actualizado", description="d", default_enabled=True)
        assert updated.name == "Actualizado"
        stored = SqliteFeatureFlagRepository(conn).get(flag.id)
        assert stored.name == "Actualizado"
        assert stored.default_enabled is True

    def test_raises_when_missing(self, conn):
        with pytest.raises(FeatureFlagNotFoundError):
            UpdateFeatureFlagUseCase(conn).execute(flag_id=new_uuid(), name="X")


class TestChangeFeatureFlagStatusUseCase:
    def test_deactivate_then_activate(self, conn):
        flag = CreateFeatureFlagUseCase(conn).execute(code="f2", name="F2")
        uc = ChangeFeatureFlagStatusUseCase(conn)
        deactivated = uc.execute(flag_id=flag.id, action=FeatureFlagStatusAction.DEACTIVATE)
        assert deactivated.active is False
        activated = uc.execute(flag_id=flag.id, action=FeatureFlagStatusAction.ACTIVATE)
        assert activated.active is True

    def test_raises_when_missing(self, conn):
        with pytest.raises(FeatureFlagNotFoundError):
            ChangeFeatureFlagStatusUseCase(conn).execute(
                flag_id=new_uuid(), action=FeatureFlagStatusAction.ACTIVATE)


class TestRequestFeatureFlagChangeUseCase:
    def test_creates_pending_request(self, conn):
        flag = CreateFeatureFlagUseCase(conn).execute(code="f3", name="F3")
        uc = RequestFeatureFlagChangeUseCase(conn)
        request = uc.execute(
            flag_id=flag.id, scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None,
            proposed_enabled=True, requested_by_user_id=new_uuid(), proposed_rollout_percentage=50,
        )
        stored = SqliteFeatureFlagChangeRequestRepository(conn).get(request.id)
        assert stored is not None
        assert stored.proposed_rollout_percentage == 50
        assert stored in SqliteFeatureFlagChangeRequestRepository(conn).list_pending()

    def test_raises_when_flag_missing(self, conn):
        with pytest.raises(FeatureFlagNotFoundError):
            RequestFeatureFlagChangeUseCase(conn).execute(
                flag_id=new_uuid(), scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None,
                proposed_enabled=True, requested_by_user_id=new_uuid(),
            )

    def test_surfaces_domain_validation_for_invalid_rollout(self, conn):
        flag = CreateFeatureFlagUseCase(conn).execute(code="f4", name="F4")
        with pytest.raises(FeatureFlagsInvalidValueError):
            RequestFeatureFlagChangeUseCase(conn).execute(
                flag_id=flag.id, scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None,
                proposed_enabled=True, requested_by_user_id=new_uuid(), proposed_rollout_percentage=200,
            )

    def test_allows_multiple_pending_requests_for_same_flag(self, conn):
        flag = CreateFeatureFlagUseCase(conn).execute(code="f5", name="F5")
        uc = RequestFeatureFlagChangeUseCase(conn)
        first = uc.execute(
            flag_id=flag.id, scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None,
            proposed_enabled=True, requested_by_user_id=new_uuid(),
        )
        second = uc.execute(
            flag_id=flag.id, scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None,
            proposed_enabled=False, requested_by_user_id=new_uuid(),
        )
        pending = SqliteFeatureFlagChangeRequestRepository(conn).list_pending()
        ids = {r.id for r in pending}
        assert {first.id, second.id} <= ids
