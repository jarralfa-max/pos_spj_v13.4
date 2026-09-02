"""UI/UX phase — the 2 write flows wired for Configuración: feature flag
change-request approve/reject/apply (SET-21), set default theme (SET-22).
Against a real (in-memory) SQLite born-clean schema.
"""

from __future__ import annotations

import pytest

from backend.application.use_cases.configuracion.feature_flag_change_request_use_cases import (
    ApplyFeatureFlagChangeRequestUseCase,
    ApproveFeatureFlagChangeRequestUseCase,
    RejectFeatureFlagChangeRequestUseCase,
)
from backend.application.use_cases.configuracion.set_default_theme_use_case import SetDefaultThemeUseCase
from backend.domain.appearance.entities.theme import Theme
from backend.domain.appearance.enums import ThemeMode
from backend.domain.appearance.exceptions import ThemeNotFoundError
from backend.domain.feature_flags.entities.feature_flag import FeatureFlag
from backend.domain.feature_flags.entities.feature_flag_change_request import FeatureFlagChangeRequest
from backend.domain.feature_flags.enums import FeatureFlagChangeStatus, FeatureFlagScopeType
from backend.domain.feature_flags.exceptions import (
    FeatureFlagApprovalRequiredError,
    FeatureFlagChangeTransitionNotAllowedError,
    FeatureFlagNotFoundError,
)
from backend.infrastructure.db.repositories.appearance.theme_repository import SqliteThemeRepository
from backend.infrastructure.db.repositories.feature_flags.feature_flag_change_request_repository import (
    SqliteFeatureFlagChangeRequestRepository,
)
from backend.infrastructure.db.repositories.feature_flags.feature_flag_repository import (
    SqliteFeatureFlagRepository,
)
from backend.infrastructure.db.repositories.feature_flags.feature_flag_rule_repository import (
    SqliteFeatureFlagRuleRepository,
)
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


@pytest.fixture
def conn():
    connection = make_db()
    yield connection
    connection.close()


def _pending_request(conn, *, requested_by="admin-1"):
    flag_repo = SqliteFeatureFlagRepository(conn)
    flag = FeatureFlag.create(code="delivery_auto", name="Auto delivery")
    flag_repo.save(flag)
    conn.commit()
    request_repo = SqliteFeatureFlagChangeRequestRepository(conn)
    request = FeatureFlagChangeRequest.create(
        flag_id=flag.id, scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None, proposed_enabled=True,
        requested_by_user_id=requested_by,
    )
    request_repo.save(request)
    conn.commit()
    return request


class TestApproveFeatureFlagChangeRequestUseCase:
    def test_approves_and_persists(self, conn):
        request = _pending_request(conn)
        use_case = ApproveFeatureFlagChangeRequestUseCase(conn)
        result = use_case.execute(request_id=request.id, approver_user_id="admin-2")
        assert result.status is FeatureFlagChangeStatus.APPROVED

        fetched = SqliteFeatureFlagChangeRequestRepository(conn).get(request.id)
        assert fetched.status is FeatureFlagChangeStatus.APPROVED
        assert fetched.approved_by_user_id == "admin-2"

    def test_rejects_self_approval(self, conn):
        request = _pending_request(conn, requested_by="admin-1")
        use_case = ApproveFeatureFlagChangeRequestUseCase(conn)
        with pytest.raises(FeatureFlagApprovalRequiredError):
            use_case.execute(request_id=request.id, approver_user_id="admin-1")

    def test_unknown_request_raises(self, conn):
        use_case = ApproveFeatureFlagChangeRequestUseCase(conn)
        with pytest.raises(FeatureFlagNotFoundError):
            use_case.execute(request_id=new_uuid(), approver_user_id="admin-2")


class TestRejectFeatureFlagChangeRequestUseCase:
    def test_rejects_and_persists_reason(self, conn):
        request = _pending_request(conn)
        use_case = RejectFeatureFlagChangeRequestUseCase(conn)
        result = use_case.execute(request_id=request.id, reason="No autorizado")
        assert result.status is FeatureFlagChangeStatus.REJECTED
        assert result.reason == "No autorizado"


class TestApplyFeatureFlagChangeRequestUseCase:
    def test_apply_creates_a_rule_and_marks_applied(self, conn):
        request = _pending_request(conn)
        ApproveFeatureFlagChangeRequestUseCase(conn).execute(request_id=request.id, approver_user_id="admin-2")

        use_case = ApplyFeatureFlagChangeRequestUseCase(conn)
        rule = use_case.execute(request_id=request.id)
        assert rule.enabled is True
        assert rule.flag_id == request.flag_id

        fetched_rule = SqliteFeatureFlagRuleRepository(conn).get(rule.id)
        assert fetched_rule is not None
        fetched_request = SqliteFeatureFlagChangeRequestRepository(conn).get(request.id)
        assert fetched_request.status is FeatureFlagChangeStatus.APPLIED

    def test_apply_before_approval_raises(self, conn):
        request = _pending_request(conn)
        use_case = ApplyFeatureFlagChangeRequestUseCase(conn)
        with pytest.raises(FeatureFlagChangeTransitionNotAllowedError):
            use_case.execute(request_id=request.id)


class TestSetDefaultThemeUseCase:
    def _two_themes(self, conn):
        theme_repo = SqliteThemeRepository(conn)
        light = Theme.create(code="claro", name="Claro", mode=ThemeMode.LIGHT, is_default=True)
        dark = Theme.create(code="oscuro", name="Oscuro", mode=ThemeMode.DARK)
        theme_repo.save(light)
        theme_repo.save(dark)
        conn.commit()
        return light, dark

    def test_switches_default_atomically(self, conn):
        light, dark = self._two_themes(conn)
        use_case = SetDefaultThemeUseCase(conn)
        result = use_case.execute(theme_id=dark.id)
        assert result.is_default is True

        theme_repo = SqliteThemeRepository(conn)
        assert theme_repo.get(light.id).is_default is False
        assert theme_repo.get(dark.id).is_default is True

    def test_switching_back_and_forth_stays_consistent(self, conn):
        light, dark = self._two_themes(conn)
        use_case = SetDefaultThemeUseCase(conn)
        use_case.execute(theme_id=dark.id)
        use_case.execute(theme_id=light.id)

        theme_repo = SqliteThemeRepository(conn)
        assert theme_repo.get(light.id).is_default is True
        assert theme_repo.get(dark.id).is_default is False

    def test_re_setting_the_current_default_is_idempotent(self, conn):
        light, _dark = self._two_themes(conn)
        use_case = SetDefaultThemeUseCase(conn)
        result = use_case.execute(theme_id=light.id)
        assert result.is_default is True

    def test_unknown_theme_raises(self, conn):
        use_case = SetDefaultThemeUseCase(conn)
        with pytest.raises(ThemeNotFoundError):
            use_case.execute(theme_id=new_uuid())
