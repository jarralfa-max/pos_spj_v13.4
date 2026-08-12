"""CRM-6 — CRMActivity/CRMTask/CRMNote/CRMReminder repository round-trips."""

from __future__ import annotations

from backend.domain.crm.entities.crm_activity import CRMActivity
from backend.domain.crm.entities.crm_note import CRMNote
from backend.domain.crm.entities.crm_reminder import CRMReminder
from backend.domain.crm.entities.crm_task import CRMTask
from backend.domain.crm.enums import CRMActivityType, CRMRelatedEntityType, ReminderChannel
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork


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
        kwargs.pop("due_at", "2026-09-01T00:00:00+00:00"), **kwargs)


class TestCRMActivityRepository:
    def test_save_and_get(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            activity = _activity(operation_id="op-1")
            uow.activities.save(activity, operation_id="op-1")
        with CRMUnitOfWork(crm_conn) as uow2:
            fetched = uow2.activities.get(activity.id)
            assert fetched.subject == "Llamar para seguimiento"
            assert fetched.status.value == "PLANNED"

    def test_get_by_operation_id_is_idempotency_lookup(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            activity = _activity(operation_id="op-dup")
            uow.activities.save(activity, operation_id="op-dup")
        with CRMUnitOfWork(crm_conn) as uow2:
            found = uow2.activities.get_by_operation_id("op-dup")
            assert found is not None and found.id == activity.id

    def test_update_persists_status(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            activity = _activity(operation_id="op-1")
            uow.activities.save(activity, operation_id="op-1")
        with CRMUnitOfWork(crm_conn) as uow2:
            activity = uow2.activities.get(activity.id)
            activity.complete()
            uow2.activities.update(activity)
        with CRMUnitOfWork(crm_conn) as uow3:
            reloaded = uow3.activities.get(activity.id)
            assert reloaded.status.value == "COMPLETED"
            assert reloaded.completed_at is not None

    def test_list_for_related_entity(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            a1 = _activity(related_entity_id="lead-1", operation_id="op-1")
            uow.activities.save(a1, operation_id="op-1")
            a2 = _activity(related_entity_id="lead-2", operation_id="op-2")
            uow.activities.save(a2, operation_id="op-2")
        with CRMUnitOfWork(crm_conn) as uow2:
            results = uow2.activities.list_for_related_entity("LEAD", "lead-1")
            assert [a.id for a in results] == [a1.id]

    def test_list_assigned_to(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            mine = _activity(assigned_user_id="u1", operation_id="op-1")
            uow.activities.save(mine, operation_id="op-1")
            other = _activity(assigned_user_id="u2", operation_id="op-2")
            uow.activities.save(other, operation_id="op-2")
        with CRMUnitOfWork(crm_conn) as uow2:
            results = uow2.activities.list_assigned_to("u1")
            assert [a.id for a in results] == [mine.id]

    def test_rollback_on_exception_discards_all_writes(self, crm_conn):
        try:
            with CRMUnitOfWork(crm_conn) as uow:
                uow.activities.save(_activity(operation_id="op-1"), operation_id="op-1")
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        count = crm_conn.execute("SELECT COUNT(*) FROM crm_activities").fetchone()[0]
        assert count == 0


class TestCRMTaskRepository:
    def test_save_and_get(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            task = _task(operation_id="op-1")
            uow.tasks.save(task, operation_id="op-1")
        with CRMUnitOfWork(crm_conn) as uow2:
            fetched = uow2.tasks.get(task.id)
            assert fetched.title == "Enviar cotización"
            assert fetched.due_at == "2026-09-01T00:00:00+00:00"

    def test_update_persists_assignment(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            task = _task(operation_id="op-1")
            uow.tasks.save(task, operation_id="op-1")
        with CRMUnitOfWork(crm_conn) as uow2:
            task = uow2.tasks.get(task.id)
            task.assign("u1")
            uow2.tasks.update(task)
        with CRMUnitOfWork(crm_conn) as uow3:
            reloaded = uow3.tasks.get(task.id)
            assert reloaded.assigned_user_id == "u1"

    def test_list_for_related_entity_ordered_by_due_at(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            later = _task(due_at="2026-12-01T00:00:00+00:00", operation_id="op-1")
            uow.tasks.save(later, operation_id="op-1")
            sooner = _task(due_at="2026-09-01T00:00:00+00:00", operation_id="op-2")
            uow.tasks.save(sooner, operation_id="op-2")
        with CRMUnitOfWork(crm_conn) as uow2:
            results = uow2.tasks.list_for_related_entity("OPPORTUNITY", "opp-1")
            assert [t.id for t in results] == [sooner.id, later.id]

    def test_list_open_excludes_completed_and_cancelled(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            open_task = _task(operation_id="op-1")
            uow.tasks.save(open_task, operation_id="op-1")
            done_task = _task(operation_id="op-2")
            uow.tasks.save(done_task, operation_id="op-2")
            done_task.complete()
            uow.tasks.update(done_task)
        with CRMUnitOfWork(crm_conn) as uow2:
            results = uow2.tasks.list_open()
            assert [t.id for t in results] == [open_task.id]


class TestCRMNoteRepository:
    def test_save_and_get(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            note = CRMNote.create(CRMRelatedEntityType.CUSTOMER, "cust-1", "texto", "u1")
            uow.notes.save(note)
        with CRMUnitOfWork(crm_conn) as uow2:
            fetched = uow2.notes.get(note.id)
            assert fetched.body == "texto"
            assert fetched.is_private is False

    def test_private_flag_round_trips(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            note = CRMNote.create(CRMRelatedEntityType.CUSTOMER, "cust-1", "confidencial", "u1",
                                  is_private=True)
            uow.notes.save(note)
        with CRMUnitOfWork(crm_conn) as uow2:
            fetched = uow2.notes.get(note.id)
            assert fetched.is_private is True

    def test_update_persists_body(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            note = CRMNote.create(CRMRelatedEntityType.CUSTOMER, "cust-1", "original", "u1")
            uow.notes.save(note)
        with CRMUnitOfWork(crm_conn) as uow2:
            note = uow2.notes.get(note.id)
            note.edit("editado")
            uow2.notes.update(note)
        with CRMUnitOfWork(crm_conn) as uow3:
            assert uow3.notes.get(note.id).body == "editado"

    def test_delete_removes_row(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            note = CRMNote.create(CRMRelatedEntityType.CUSTOMER, "cust-1", "texto", "u1")
            uow.notes.save(note)
        with CRMUnitOfWork(crm_conn) as uow2:
            uow2.notes.delete(note.id)
        with CRMUnitOfWork(crm_conn) as uow3:
            assert uow3.notes.get(note.id) is None

    def test_list_for_related_entity(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            n1 = CRMNote.create(CRMRelatedEntityType.CUSTOMER, "cust-1", "a", "u1")
            uow.notes.save(n1)
            n2 = CRMNote.create(CRMRelatedEntityType.CUSTOMER, "cust-2", "b", "u1")
            uow.notes.save(n2)
        with CRMUnitOfWork(crm_conn) as uow2:
            results = uow2.notes.list_for_related_entity("CUSTOMER", "cust-1")
            assert [n.id for n in results] == [n1.id]


class TestCRMReminderRepository:
    def test_save_and_list_for_task(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            task = _task(operation_id="op-1")
            uow.tasks.save(task, operation_id="op-1")
            reminder = CRMReminder.create(ReminderChannel.EMAIL, "2026-08-31T00:00:00+00:00",
                                          "u1", task_id=task.id)
            uow.reminders.save(reminder)
        with CRMUnitOfWork(crm_conn) as uow2:
            results = uow2.reminders.list_for_task(task.id)
            assert len(results) == 1
            assert results[0].channel.value == "EMAIL"

    def test_save_and_list_for_activity(self, crm_conn):
        with CRMUnitOfWork(crm_conn) as uow:
            activity = _activity(operation_id="op-1")
            uow.activities.save(activity, operation_id="op-1")
            reminder = CRMReminder.create(ReminderChannel.IN_APP, "2026-08-31T00:00:00+00:00",
                                          "u1", activity_id=activity.id)
            uow.reminders.save(reminder)
        with CRMUnitOfWork(crm_conn) as uow2:
            results = uow2.reminders.list_for_activity(activity.id)
            assert len(results) == 1
