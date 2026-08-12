"""CRM-6 — Activities/Tasks/Notes/Reminders domain unit tests: entity
lifecycle, effective_status() OVERDUE derivation. Pure domain — no DB.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.domain.crm.entities.crm_activity import CRMActivity
from backend.domain.crm.entities.crm_note import CRMNote
from backend.domain.crm.entities.crm_reminder import CRMReminder
from backend.domain.crm.entities.crm_task import CRMTask
from backend.domain.crm.enums import (
    CRMActivityType,
    CRMRelatedEntityType,
    CRMWorkItemStatus,
    ReminderChannel,
)
from backend.domain.crm.exceptions import (
    InvalidCRMActivityStateError,
    InvalidCRMNoteError,
    InvalidCRMReminderError,
    InvalidCRMTaskStateError,
)


def _iso(delta_days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=delta_days)).isoformat(
        timespec="seconds")


def _activity(**kwargs) -> CRMActivity:
    return CRMActivity.create(
        kwargs.pop("activity_type", CRMActivityType.CALL),
        kwargs.pop("related_entity_type", CRMRelatedEntityType.LEAD),
        kwargs.pop("related_entity_id", "lead-1"),
        kwargs.pop("subject", "Llamar para seguimiento"), **kwargs)


def _task(**kwargs) -> CRMTask:
    return CRMTask.create(
        kwargs.pop("related_entity_type", CRMRelatedEntityType.OPPORTUNITY),
        kwargs.pop("related_entity_id", "opp-1"), kwargs.pop("title", "Enviar cotización"),
        kwargs.pop("due_at", _iso(5)), **kwargs)


class TestCRMActivityLifecycle:
    def test_create_defaults_to_planned(self):
        activity = _activity()
        assert activity.status is CRMWorkItemStatus.PLANNED

    def test_create_requires_subject(self):
        with pytest.raises(InvalidCRMActivityStateError):
            _activity(subject="   ")

    def test_create_requires_related_entity_id(self):
        with pytest.raises(InvalidCRMActivityStateError):
            CRMActivity.create(CRMActivityType.CALL, CRMRelatedEntityType.LEAD, "", "Llamar")

    def test_start_then_complete(self):
        activity = _activity()
        activity.start()
        assert activity.status is CRMWorkItemStatus.IN_PROGRESS
        activity.complete()
        assert activity.status is CRMWorkItemStatus.COMPLETED
        assert activity.completed_at is not None

    def test_complete_directly_from_planned_allowed(self):
        activity = _activity()
        activity.complete()
        assert activity.status is CRMWorkItemStatus.COMPLETED

    def test_cancel_requires_reason(self):
        activity = _activity()
        with pytest.raises(InvalidCRMActivityStateError):
            activity.cancel("")
        activity.cancel("ya no aplica")
        assert activity.status is CRMWorkItemStatus.CANCELLED

    def test_terminal_activity_rejects_further_transitions(self):
        activity = _activity()
        activity.complete()
        with pytest.raises(InvalidCRMActivityStateError):
            activity.start()
        with pytest.raises(InvalidCRMActivityStateError):
            activity.cancel("motivo")

    def test_reschedule_updates_scheduled_at(self):
        activity = _activity(scheduled_at=_iso(1))
        activity.reschedule(_iso(10))
        assert activity.scheduled_at == _iso(10)

    def test_reassign_updates_assignee(self):
        activity = _activity()
        activity.reassign("u2")
        assert activity.assigned_user_id == "u2"

    def test_reassign_requires_user_id(self):
        with pytest.raises(InvalidCRMActivityStateError):
            _activity().reassign("")

    def test_effective_status_overdue_when_past_scheduled_at(self):
        activity = _activity(scheduled_at=_iso(-1))
        assert activity.effective_status() is CRMWorkItemStatus.OVERDUE

    def test_effective_status_not_overdue_when_future(self):
        activity = _activity(scheduled_at=_iso(5))
        assert activity.effective_status() is CRMWorkItemStatus.PLANNED

    def test_effective_status_completed_never_overdue(self):
        activity = _activity(scheduled_at=_iso(-5))
        activity.complete()
        assert activity.effective_status() is CRMWorkItemStatus.COMPLETED

    def test_effective_status_no_scheduled_at_never_overdue(self):
        activity = _activity()
        assert activity.effective_status() is CRMWorkItemStatus.PLANNED


class TestCRMTaskLifecycle:
    def test_create_requires_due_at(self):
        with pytest.raises(InvalidCRMTaskStateError):
            CRMTask.create(CRMRelatedEntityType.OPPORTUNITY, "opp-1", "Título", "")

    def test_create_requires_title(self):
        with pytest.raises(InvalidCRMTaskStateError):
            _task(title="   ")

    def test_complete_from_planned(self):
        task = _task()
        task.complete()
        assert task.status is CRMWorkItemStatus.COMPLETED
        assert task.completed_at is not None

    def test_cancel_requires_reason(self):
        task = _task()
        with pytest.raises(InvalidCRMTaskStateError):
            task.cancel("")
        task.cancel("ya no aplica")
        assert task.status is CRMWorkItemStatus.CANCELLED

    def test_terminal_task_rejects_further_transitions(self):
        task = _task()
        task.complete()
        with pytest.raises(InvalidCRMTaskStateError):
            task.reschedule(_iso(20))
        with pytest.raises(InvalidCRMTaskStateError):
            task.assign("u2")

    def test_reschedule_updates_due_at(self):
        task = _task(due_at=_iso(1))
        task.reschedule(_iso(20))
        assert task.due_at == _iso(20)

    def test_assign_requires_user_id(self):
        with pytest.raises(InvalidCRMTaskStateError):
            _task().assign("")

    def test_effective_status_overdue_when_past_due(self):
        task = _task(due_at=_iso(-1))
        assert task.effective_status() is CRMWorkItemStatus.OVERDUE

    def test_effective_status_not_overdue_when_future(self):
        task = _task(due_at=_iso(5))
        assert task.effective_status() is CRMWorkItemStatus.PLANNED

    def test_effective_status_completed_never_overdue(self):
        task = _task(due_at=_iso(-5))
        task.complete()
        assert task.effective_status() is CRMWorkItemStatus.COMPLETED


class TestCRMNote:
    def test_create_requires_body(self):
        with pytest.raises(InvalidCRMNoteError):
            CRMNote.create(CRMRelatedEntityType.CUSTOMER, "cust-1", "   ", "u1")

    def test_create_requires_author(self):
        with pytest.raises(InvalidCRMNoteError):
            CRMNote.create(CRMRelatedEntityType.CUSTOMER, "cust-1", "texto", "")

    def test_defaults_to_not_private(self):
        note = CRMNote.create(CRMRelatedEntityType.CUSTOMER, "cust-1", "texto", "u1")
        assert note.is_private is False

    def test_edit_updates_body(self):
        note = CRMNote.create(CRMRelatedEntityType.CUSTOMER, "cust-1", "original", "u1")
        note.edit("actualizado")
        assert note.body == "actualizado"

    def test_edit_requires_body(self):
        note = CRMNote.create(CRMRelatedEntityType.CUSTOMER, "cust-1", "original", "u1")
        with pytest.raises(InvalidCRMNoteError):
            note.edit("")

    def test_is_authored_by(self):
        note = CRMNote.create(CRMRelatedEntityType.CUSTOMER, "cust-1", "texto", "u1")
        assert note.is_authored_by("u1")
        assert not note.is_authored_by("u2")


class TestCRMReminder:
    def test_requires_task_or_activity(self):
        with pytest.raises(InvalidCRMReminderError):
            CRMReminder.create(ReminderChannel.IN_APP, _iso(1), "u1")

    def test_rejects_both_task_and_activity(self):
        with pytest.raises(InvalidCRMReminderError):
            CRMReminder.create(ReminderChannel.IN_APP, _iso(1), "u1", task_id="t1",
                               activity_id="a1")

    def test_create_with_task_id(self):
        reminder = CRMReminder.create(ReminderChannel.EMAIL, _iso(1), "u1", task_id="t1")
        assert reminder.task_id == "t1"
        assert reminder.activity_id is None

    def test_requires_remind_at(self):
        with pytest.raises(InvalidCRMReminderError):
            CRMReminder.create(ReminderChannel.IN_APP, "", "u1", task_id="t1")

    def test_requires_recipient(self):
        with pytest.raises(InvalidCRMReminderError):
            CRMReminder.create(ReminderChannel.IN_APP, _iso(1), "", task_id="t1")
