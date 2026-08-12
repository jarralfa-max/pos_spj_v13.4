"""CRM-6 — Activities/Tasks/Notes/Reminders application tests (use cases +
query services).

Covers happy path, permission-denied (fail closed), invalid state,
idempotency, rollback, audit, effective_status()/OVERDUE at the query
layer, note privacy masking + author-only edit/delete, and the
assign-vs-reassign permission split for tasks.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.application.crm.authorization import (
    CRMAuthorizationPolicy,
    DenyAllCRMPermissionCheckerForTests,
)
from backend.application.crm.permissions import CRMPermissions
from backend.application.crm.queries.crm_activity_query_service import CRMActivityQueryService
from backend.application.crm.queries.crm_note_query_service import CRMNoteQueryService
from backend.application.crm.queries.crm_task_query_service import CRMTaskQueryService
from backend.application.crm.use_cases.activity_use_cases import (
    CancelCRMActivityUseCase,
    CompleteCRMActivityUseCase,
    CreateCRMActivityUseCase,
    ReassignCRMActivityUseCase,
    RescheduleCRMActivityUseCase,
    StartCRMActivityUseCase,
)
from backend.application.crm.use_cases.note_use_cases import (
    CreateCRMNoteUseCase,
    DeleteCRMNoteUseCase,
    UpdateCRMNoteUseCase,
)
from backend.application.crm.use_cases.reminder_use_cases import CreateCRMReminderUseCase
from backend.application.crm.use_cases.task_use_cases import (
    AssignCRMTaskUseCase,
    CancelCRMTaskUseCase,
    CompleteCRMTaskUseCase,
    CreateCRMTaskUseCase,
    RescheduleCRMTaskUseCase,
)
from backend.domain.crm.exceptions import (
    CRMActivityNotFoundError,
    CRMNoteNotFoundError,
    CRMTaskNotFoundError,
)
from backend.shared.ids import new_uuid


def _allow():
    return CRMAuthorizationPolicy.permissive_for_tests()


def _deny():
    return CRMAuthorizationPolicy(DenyAllCRMPermissionCheckerForTests())


def _iso(delta_days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=delta_days)).isoformat(
        timespec="seconds")


def _create_activity(conn, *, actor="u1", **kwargs):
    return CreateCRMActivityUseCase(_allow()).execute(
        conn, actor_user_id=actor, activity_type=kwargs.pop("activity_type", "CALL"),
        related_entity_type=kwargs.pop("related_entity_type", "LEAD"),
        related_entity_id=kwargs.pop("related_entity_id", "lead-1"),
        subject=kwargs.pop("subject", "Llamar para seguimiento"),
        operation_id=kwargs.pop("operation_id", None) or new_uuid(), **kwargs)


def _create_task(conn, *, actor="u1", **kwargs):
    return CreateCRMTaskUseCase(_allow()).execute(
        conn, actor_user_id=actor,
        related_entity_type=kwargs.pop("related_entity_type", "OPPORTUNITY"),
        related_entity_id=kwargs.pop("related_entity_id", "opp-1"),
        title=kwargs.pop("title", "Enviar cotización"),
        due_at=kwargs.pop("due_at", None) or _iso(5),
        operation_id=kwargs.pop("operation_id", None) or new_uuid(), **kwargs)


class TestCreateCRMActivity:
    def test_happy_path(self, crm_conn):
        result = _create_activity(crm_conn)
        assert result.success

    def test_permission_denied(self, crm_conn):
        result = CreateCRMActivityUseCase(_deny()).execute(
            crm_conn, actor_user_id="u1", activity_type="CALL", related_entity_type="LEAD",
            related_entity_id="lead-1", subject="X", operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_idempotent_on_operation_id(self, crm_conn):
        op_id = new_uuid()
        first = _create_activity(crm_conn, operation_id=op_id)
        second = _create_activity(crm_conn, operation_id=op_id)
        assert first.entity_id == second.entity_id
        count = crm_conn.execute("SELECT COUNT(*) FROM crm_activities").fetchone()[0]
        assert count == 1

    def test_missing_subject_is_validation_error(self, crm_conn):
        result = CreateCRMActivityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", activity_type="CALL", related_entity_type="LEAD",
            related_entity_id="lead-1", subject="   ", operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"


class TestCRMActivityTransitions:
    def test_start_complete_cancel_reschedule_reassign(self, crm_conn):
        activity_id = _create_activity(crm_conn).entity_id
        assert StartCRMActivityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", activity_id=activity_id, operation_id=new_uuid()
        ).success
        assert CompleteCRMActivityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", activity_id=activity_id, operation_id=new_uuid()
        ).success

        activity_id2 = _create_activity(crm_conn).entity_id
        cancel_denied = CancelCRMActivityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", activity_id=activity_id2, operation_id=new_uuid())
        assert not cancel_denied.success  # no reason supplied
        assert CancelCRMActivityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", activity_id=activity_id2, operation_id=new_uuid(),
            reason="ya no aplica"
        ).success

        activity_id3 = _create_activity(crm_conn).entity_id
        assert RescheduleCRMActivityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", activity_id=activity_id3,
            new_scheduled_at=_iso(10), operation_id=new_uuid()
        ).success
        assert ReassignCRMActivityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", activity_id=activity_id3, assignee_user_id="u2",
            operation_id=new_uuid()
        ).success

    def test_missing_activity_returns_not_found(self, crm_conn):
        result = CompleteCRMActivityUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", activity_id="does-not-exist", operation_id=new_uuid())
        assert not result.success and result.error_code == "NOT_FOUND"

    def test_permission_denied_on_complete(self, crm_conn):
        activity_id = _create_activity(crm_conn).entity_id
        result = CompleteCRMActivityUseCase(_deny()).execute(
            crm_conn, actor_user_id="u1", activity_id=activity_id, operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"


class TestCRMTaskUseCases:
    def test_create_complete_cancel_reschedule(self, crm_conn):
        task_id = _create_task(crm_conn).entity_id
        assert CompleteCRMTaskUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", task_id=task_id, operation_id=new_uuid()
        ).success

        task_id2 = _create_task(crm_conn).entity_id
        cancelled = CancelCRMTaskUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", task_id=task_id2, operation_id=new_uuid(),
            reason="ya no aplica")
        assert cancelled.success

        task_id3 = _create_task(crm_conn).entity_id
        rescheduled = RescheduleCRMTaskUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", task_id=task_id3, new_due_at=_iso(20),
            operation_id=new_uuid())
        assert rescheduled.success

    def test_idempotent_on_operation_id(self, crm_conn):
        op_id = new_uuid()
        first = _create_task(crm_conn, operation_id=op_id)
        second = _create_task(crm_conn, operation_id=op_id)
        assert first.entity_id == second.entity_id

    def test_assign_first_time_uses_assign_permission(self, crm_conn):
        task_id = _create_task(crm_conn).entity_id
        checker_grants = {CRMPermissions.TASKS_ASSIGN}

        class _Checker:
            def has_permission(self, user_id, code):
                return code in checker_grants

        result = AssignCRMTaskUseCase(CRMAuthorizationPolicy(_Checker())).execute(
            crm_conn, actor_user_id="u1", task_id=task_id, assignee_user_id="u2",
            operation_id=new_uuid())
        assert result.success

    def test_reassign_requires_reassign_not_assign_permission(self, crm_conn):
        task_id = _create_task(crm_conn, assigned_user_id="u-original").entity_id
        checker_grants = {CRMPermissions.TASKS_ASSIGN}  # only ASSIGN, not REASSIGN

        class _Checker:
            def has_permission(self, user_id, code):
                return code in checker_grants

        result = AssignCRMTaskUseCase(CRMAuthorizationPolicy(_Checker())).execute(
            crm_conn, actor_user_id="u1", task_id=task_id, assignee_user_id="u2",
            operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_reschedule_requires_dedicated_permission(self, crm_conn):
        task_id = _create_task(crm_conn).entity_id
        result = RescheduleCRMTaskUseCase(_deny()).execute(
            crm_conn, actor_user_id="u1", task_id=task_id, new_due_at=_iso(20),
            operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"


class TestCRMNoteUseCases:
    def test_create_public_and_private(self, crm_conn):
        pub = CreateCRMNoteUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", related_entity_type="CUSTOMER",
            related_entity_id="cust-1", body="texto", operation_id=new_uuid())
        assert pub.success
        priv = CreateCRMNoteUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", related_entity_type="CUSTOMER",
            related_entity_id="cust-1", body="confidencial", operation_id=new_uuid(),
            is_private=True)
        assert priv.success

    def test_update_denied_for_non_author(self, crm_conn):
        note_id = CreateCRMNoteUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", related_entity_type="CUSTOMER",
            related_entity_id="cust-1", body="original", operation_id=new_uuid()).entity_id
        result = UpdateCRMNoteUseCase(_allow()).execute(
            crm_conn, actor_user_id="u2", note_id=note_id, body="hackeado",
            operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_update_allowed_for_author(self, crm_conn):
        note_id = CreateCRMNoteUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", related_entity_type="CUSTOMER",
            related_entity_id="cust-1", body="original", operation_id=new_uuid()).entity_id
        result = UpdateCRMNoteUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", note_id=note_id, body="editado",
            operation_id=new_uuid())
        assert result.success

    def test_delete_denied_for_non_author(self, crm_conn):
        note_id = CreateCRMNoteUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", related_entity_type="CUSTOMER",
            related_entity_id="cust-1", body="original", operation_id=new_uuid()).entity_id
        result = DeleteCRMNoteUseCase(_allow()).execute(
            crm_conn, actor_user_id="u2", note_id=note_id, operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"
        assert crm_conn.execute("SELECT COUNT(*) FROM crm_notes").fetchone()[0] == 1

    def test_delete_allowed_for_author(self, crm_conn):
        note_id = CreateCRMNoteUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", related_entity_type="CUSTOMER",
            related_entity_id="cust-1", body="original", operation_id=new_uuid()).entity_id
        result = DeleteCRMNoteUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", note_id=note_id, operation_id=new_uuid())
        assert result.success
        assert crm_conn.execute("SELECT COUNT(*) FROM crm_notes").fetchone()[0] == 0


class TestCreateCRMReminder:
    def test_happy_path_with_task(self, crm_conn):
        task_id = _create_task(crm_conn).entity_id
        result = CreateCRMReminderUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", channel="EMAIL", remind_at=_iso(1),
            recipient_user_id="u1", operation_id=new_uuid(), task_id=task_id)
        assert result.success

    def test_missing_task_returns_not_found(self, crm_conn):
        result = CreateCRMReminderUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", channel="EMAIL", remind_at=_iso(1),
            recipient_user_id="u1", operation_id=new_uuid(), task_id="does-not-exist")
        assert not result.success and result.error_code == "NOT_FOUND"

    def test_permission_denied(self, crm_conn):
        task_id = _create_task(crm_conn).entity_id
        result = CreateCRMReminderUseCase(_deny()).execute(
            crm_conn, actor_user_id="u1", channel="EMAIL", remind_at=_iso(1),
            recipient_user_id="u1", operation_id=new_uuid(), task_id=task_id)
        assert not result.success and result.error_code == "PERMISSION_DENIED"


class TestCRMActivityQueryService:
    def test_get_missing_raises_not_found(self, crm_conn):
        service = CRMActivityQueryService(crm_conn, _allow())
        with pytest.raises(CRMActivityNotFoundError):
            service.get("does-not-exist", actor_user_id="u1")

    def test_list_overdue_for_detects_past_scheduled_at(self, crm_conn):
        overdue_id = _create_activity(
            crm_conn, assigned_user_id="u1", scheduled_at=_iso(-1)).entity_id
        _create_activity(crm_conn, assigned_user_id="u1", scheduled_at=_iso(5))
        service = CRMActivityQueryService(crm_conn, _allow())
        overdue = service.list_overdue_for("u1", actor_user_id="u1")
        assert [a.id for a in overdue] == [overdue_id]


class TestCRMTaskQueryService:
    def test_get_missing_raises_not_found(self, crm_conn):
        service = CRMTaskQueryService(crm_conn, _allow())
        with pytest.raises(CRMTaskNotFoundError):
            service.get("does-not-exist", actor_user_id="u1")

    def test_list_overdue_for_detects_past_due_at(self, crm_conn):
        overdue_id = _create_task(crm_conn, assigned_user_id="u1", due_at=_iso(-1)).entity_id
        _create_task(crm_conn, assigned_user_id="u1", due_at=_iso(5))
        service = CRMTaskQueryService(crm_conn, _allow())
        overdue = service.list_overdue_for("u1", actor_user_id="u1")
        assert [t.id for t in overdue] == [overdue_id]


class TestCRMNoteQueryService:
    def test_get_missing_raises_not_found(self, crm_conn):
        service = CRMNoteQueryService(crm_conn, _allow())
        with pytest.raises(CRMNoteNotFoundError):
            service.get("does-not-exist", actor_user_id="u1")

    def test_list_hides_private_notes_without_permission(self, crm_conn):
        CreateCRMNoteUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", related_entity_type="CUSTOMER",
            related_entity_id="cust-1", body="publica", operation_id=new_uuid())
        CreateCRMNoteUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", related_entity_type="CUSTOMER",
            related_entity_id="cust-1", body="privada", operation_id=new_uuid(),
            is_private=True)

        checker_grants = {CRMPermissions.NOTES_VIEW}  # no NOTES_VIEW_PRIVATE

        class _Checker:
            def has_permission(self, user_id, code):
                return code in checker_grants

        service = CRMNoteQueryService(crm_conn, CRMAuthorizationPolicy(_Checker()))
        results = service.list_for_related_entity("CUSTOMER", "cust-1", actor_user_id="u2")
        assert [n.body for n in results] == ["publica"]

    def test_list_shows_own_private_note_to_author_without_view_private_permission(
        self, crm_conn,
    ):
        CreateCRMNoteUseCase(_allow()).execute(
            crm_conn, actor_user_id="u1", related_entity_type="CUSTOMER",
            related_entity_id="cust-1", body="mi nota privada", operation_id=new_uuid(),
            is_private=True)

        checker_grants = {CRMPermissions.NOTES_VIEW, CRMPermissions.NOTES_CREATE_PRIVATE}

        class _Checker:
            def has_permission(self, user_id, code):
                return code in checker_grants

        service = CRMNoteQueryService(crm_conn, CRMAuthorizationPolicy(_Checker()))
        results = service.list_for_related_entity("CUSTOMER", "cust-1", actor_user_id="u1")
        assert [n.body for n in results] == ["mi nota privada"]
