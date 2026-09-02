"""SET-21 — SqliteFeatureFlagRepository + SqliteFeatureFlagRuleRepository
+ SqliteFeatureFlagChangeRequestRepository against a real (in-memory)
SQLite born-clean schema (migration 221).
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.domain.feature_flags.entities.feature_flag import FeatureFlag
from backend.domain.feature_flags.entities.feature_flag_change_request import FeatureFlagChangeRequest
from backend.domain.feature_flags.entities.feature_flag_rule import FeatureFlagRule
from backend.domain.feature_flags.enums import FeatureFlagChangeStatus, FeatureFlagScopeType
from backend.domain.feature_flags.policies.feature_flag_approval_policy import assert_can_approve
from backend.domain.feature_flags.policies.feature_flag_evaluation_policy import resolve_flag_value
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


@pytest.fixture
def flag_repo(conn):
    return SqliteFeatureFlagRepository(conn)


@pytest.fixture
def rule_repo(conn):
    return SqliteFeatureFlagRuleRepository(conn)


@pytest.fixture
def request_repo(conn):
    return SqliteFeatureFlagChangeRequestRepository(conn)


class TestFeatureFlagRepository:
    def test_save_get_roundtrip(self, conn, flag_repo):
        flag = FeatureFlag.create(code="delivery_auto_asign", name="Auto-asignación de delivery")
        flag_repo.save(flag)
        conn.commit()

        fetched = flag_repo.get(flag.id)
        assert fetched.code == "delivery_auto_asign"
        assert fetched.default_enabled is False

    def test_get_by_code(self, conn, flag_repo):
        flag = FeatureFlag.create(code="delivery_auto_asign", name="Auto-asignación")
        flag_repo.save(flag)
        conn.commit()
        assert flag_repo.get_by_code("delivery_auto_asign").id == flag.id

    def test_code_is_unique(self, conn, flag_repo):
        flag_repo.save(FeatureFlag.create(code="delivery_auto_asign", name="A"))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            flag_repo.save(FeatureFlag.create(code="delivery_auto_asign", name="B"))
            conn.commit()
        conn.rollback()

    def test_list_active_excludes_inactive(self, conn, flag_repo):
        active = FeatureFlag.create(code="a", name="A")
        inactive = FeatureFlag.create(code="b", name="B")
        inactive.deactivate()
        flag_repo.save(active)
        flag_repo.save(inactive)
        conn.commit()

        codes = {f.code for f in flag_repo.list_active()}
        assert codes == {"a"}


class TestFeatureFlagRuleRepository:
    def _saved_flag(self, conn, flag_repo) -> FeatureFlag:
        flag = FeatureFlag.create(code="delivery_auto_asign", name="Auto-asignación")
        flag_repo.save(flag)
        conn.commit()
        return flag

    def test_save_get_roundtrip(self, conn, flag_repo, rule_repo):
        flag = self._saved_flag(conn, flag_repo)
        rule = FeatureFlagRule.create(
            flag_id=flag.id, scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None, enabled=True,
            rollout_percentage=50,
        )
        rule_repo.save(rule)
        conn.commit()

        fetched = rule_repo.get(rule.id)
        assert fetched.rollout_percentage == 50
        assert fetched.scope_type is FeatureFlagScopeType.GLOBAL

    def test_list_for_flag(self, conn, flag_repo, rule_repo):
        flag = self._saved_flag(conn, flag_repo)
        branch_id = new_uuid()
        global_rule = FeatureFlagRule.create(
            flag_id=flag.id, scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None, enabled=True,
        )
        branch_rule = FeatureFlagRule.create(
            flag_id=flag.id, scope_type=FeatureFlagScopeType.BRANCH, scope_id=branch_id, enabled=False,
        )
        rule_repo.save(global_rule)
        rule_repo.save(branch_rule)
        conn.commit()

        assert {r.id for r in rule_repo.list_for_flag(flag.id)} == {global_rule.id, branch_rule.id}

    def test_unique_index_blocks_two_active_rules_for_same_scope(self, conn, flag_repo, rule_repo):
        flag = self._saved_flag(conn, flag_repo)
        first = FeatureFlagRule.create(
            flag_id=flag.id, scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None, enabled=True,
        )
        second = FeatureFlagRule.create(
            flag_id=flag.id, scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None, enabled=False,
        )
        rule_repo.save(first)
        conn.commit()

        with pytest.raises(sqlite3.IntegrityError):
            rule_repo.save(second)
            conn.commit()
        conn.rollback()

    def test_composes_with_evaluation_policy_end_to_end(self, conn, flag_repo, rule_repo):
        flag = self._saved_flag(conn, flag_repo)
        branch_id = new_uuid()
        global_rule = FeatureFlagRule.create(
            flag_id=flag.id, scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None, enabled=True,
        )
        branch_rule = FeatureFlagRule.create(
            flag_id=flag.id, scope_type=FeatureFlagScopeType.BRANCH, scope_id=branch_id, enabled=False,
        )
        rule_repo.save(global_rule)
        rule_repo.save(branch_rule)
        conn.commit()

        fetched_flag = flag_repo.get(flag.id)
        fetched_rules = rule_repo.list_for_flag(flag.id)
        assert resolve_flag_value(fetched_flag, fetched_rules, branch_id=branch_id) is False
        assert resolve_flag_value(fetched_flag, fetched_rules, branch_id=new_uuid()) is True


class TestFeatureFlagChangeRequestRepository:
    def test_save_get_and_apply_end_to_end(self, conn, flag_repo, rule_repo, request_repo):
        flag = FeatureFlag.create(code="delivery_auto_asign", name="Auto-asignación")
        flag_repo.save(flag)
        conn.commit()

        request = FeatureFlagChangeRequest.create(
            flag_id=flag.id, scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None, proposed_enabled=True,
            requested_by_user_id="admin-1",
        )
        request_repo.save(request)
        conn.commit()

        assert_can_approve(request, approver_user_id="admin-2")
        request.approve(approved_by_user_id="admin-2")
        request_repo.save(request)
        conn.commit()

        fetched = request_repo.get(request.id)
        assert fetched.status is FeatureFlagChangeStatus.APPROVED
        assert fetched.approved_by_user_id == "admin-2"

        new_rule = fetched.apply()
        rule_repo.save(new_rule)
        request_repo.save(fetched)
        conn.commit()

        assert rule_repo.get(new_rule.id).enabled is True
        assert request_repo.get(request.id).status is FeatureFlagChangeStatus.APPLIED

    def test_list_pending(self, conn, flag_repo, request_repo):
        flag = FeatureFlag.create(code="a", name="A")
        flag_repo.save(flag)
        conn.commit()

        pending = FeatureFlagChangeRequest.create(
            flag_id=flag.id, scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None, proposed_enabled=True,
            requested_by_user_id="admin-1",
        )
        approved = FeatureFlagChangeRequest.create(
            flag_id=flag.id, scope_type=FeatureFlagScopeType.GLOBAL, scope_id=None, proposed_enabled=True,
            requested_by_user_id="admin-1",
        )
        approved.approve(approved_by_user_id="admin-2")
        request_repo.save(pending)
        request_repo.save(approved)
        conn.commit()

        assert [r.id for r in request_repo.list_pending()] == [pending.id]
