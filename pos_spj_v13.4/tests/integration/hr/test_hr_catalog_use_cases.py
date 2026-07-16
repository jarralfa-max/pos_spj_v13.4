from __future__ import annotations

import sqlite3

from backend.application.commands.hr_commands import (
    CreateContractTypeCommand,
    CreateDepartmentCommand,
    CreatePaymentFrequencyCommand,
    CreatePositionCommand,
)
from backend.application.queries.hr_catalog_query_service import HRCatalogQueryService
from backend.application.use_cases.hr import (
    CreateContractTypeUseCase,
    CreateDepartmentUseCase,
    CreatePaymentFrequencyUseCase,
    CreatePositionUseCase,
)
from backend.application.use_cases.hr.audit import HRAuditRecord
from backend.infrastructure.db.repositories.department_repository import SQLiteDepartmentRepository
from backend.infrastructure.db.repositories.hr_catalog_repository import SQLiteContractTypeRepository, SQLitePaymentFrequencyRepository
from backend.infrastructure.db.repositories.position_repository import SQLitePositionRepository
from backend.infrastructure.db.schema.hr_schema import create_hr_schema
from backend.shared.events import InMemoryEventBus
from backend.shared.events.event_names import EventName


class _AuditSink:
    def __init__(self) -> None:
        self.records: list[HRAuditRecord] = []

    def record(self, audit_record: HRAuditRecord) -> None:
        self.records.append(audit_record)


def test_hr_catalog_use_cases_create_configurable_catalogs_and_publish_events() -> None:
    conn = sqlite3.connect(":memory:")
    create_hr_schema(conn)
    bus = InMemoryEventBus()
    audit = _AuditSink()
    published: list[EventName] = []
    bus.subscribe(EventName.HR_CATALOG_UPDATED, lambda event: published.append(event.event_name))
    checker = lambda _user_id, permission: permission == "hr.settings.manage"
    branch_id = "01900000-0000-7000-8000-000000000001"
    user_id = "01900000-0000-7000-8000-00000000a001"

    dept_result = CreateDepartmentUseCase(
        SQLiteDepartmentRepository(conn), event_bus=bus, permission_checker=checker, audit_sink=audit
    ).execute(CreateDepartmentCommand(operation_id="01900000-0000-7000-8000-00000000d001", branch_id=branch_id, user_id=user_id, name="Administración"))
    assert dept_result.success

    position_result = CreatePositionUseCase(
        SQLitePositionRepository(conn), event_bus=bus, permission_checker=checker, audit_sink=audit
    ).execute(CreatePositionCommand(operation_id="01900000-0000-7000-8000-00000000d002", branch_id=branch_id, user_id=user_id, name="Auxiliar", department_id=dept_result.entity_id or ""))
    assert position_result.success

    contract_result = CreateContractTypeUseCase(
        SQLiteContractTypeRepository(conn), event_bus=bus, permission_checker=checker, audit_sink=audit
    ).execute(CreateContractTypeCommand(operation_id="01900000-0000-7000-8000-00000000d003", branch_id=branch_id, user_id=user_id, code="full_time", name="Tiempo completo"))
    assert contract_result.success

    frequency_result = CreatePaymentFrequencyUseCase(
        SQLitePaymentFrequencyRepository(conn), event_bus=bus, permission_checker=checker, audit_sink=audit
    ).execute(CreatePaymentFrequencyCommand(operation_id="01900000-0000-7000-8000-00000000d004", branch_id=branch_id, user_id=user_id, code="weekly", name="Semanal"))
    assert frequency_result.success

    catalogs = HRCatalogQueryService(conn)
    assert [item.code for item in catalogs.list_contract_types()] == ["FULL_TIME"]
    assert [item.code for item in catalogs.list_payment_frequencies()] == ["WEEKLY"]
    assert published == [EventName.HR_CATALOG_UPDATED] * 4
    assert [record.action for record in audit.records] == ["HR_CATALOG_UPDATED"] * 4
    assert [record.metadata["catalog"] for record in audit.records] == [
        "departments",
        "positions",
        "contract_types",
        "payment_frequencies",
    ]
