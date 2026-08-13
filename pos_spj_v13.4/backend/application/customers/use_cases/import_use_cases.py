"""Customer import use cases: import, approve, reject (§47, §73).

ImportCustomersUseCase implements §47's flow (minus the file→mapeo→preview
steps, which are CustomerImportPreviewQuery's job — see
queries/customer_import_preview_query.py): for each row, create a new
customer (reusing CustomerDuplicatePolicy so an import can't silently
create duplicates any more than CreateCustomerUseCase can) or, when the
row carries a ``customer_id``, update the matching existing customer's
core fields. Every row is tallied into exactly one outcome bucket
(created/updated/rejected/duplicate/error) — a bad row never aborts the
whole batch.

Sensitive batches (``is_sensitive=True``) don't write anything on submit:
first real consumer of
``CustomerSegregationOfDutiesPolicy.enforce_sensitive_import_approver_
distinct()`` (§73: "quien importa no aprueba una importación sensible"),
unconsumed since CRM-2. ApproveCustomerImportUseCase is the second,
distinct-user step that actually processes the rows.
"""

from __future__ import annotations

import json

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.result import CustomerResult
from backend.domain.customers.entities.customer import Customer
from backend.domain.customers.entities.customer_import_batch import CustomerImportBatch
from backend.domain.customers.enums import CustomerType
from backend.domain.customers.events import CustomerEvents, build_event_payload
from backend.domain.customers.exceptions import CustomerDomainError, CustomerSegregationOfDutiesError
from backend.domain.customers.policies.duplicate_policy import CustomerDuplicatePolicy
from backend.domain.customers.policies.segregation_of_duties_policy import (
    CustomerSegregationOfDutiesPolicy,
)
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork


class _BaseUseCase:
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or CustomerAuthorizationPolicy()
        self._duplicates = CustomerDuplicatePolicy()

    def _emit(self, uow, event_name: str, customer_id: str, operation_id: str,
              actor_user_id: str, **extra) -> None:
        payload = build_event_payload(event_name, operation_id=operation_id,
                                      customer_id=customer_id, user_id=actor_user_id, **extra)
        uow.outbox.enqueue(payload["event_id"], event_name, json.dumps(payload), operation_id)

    def _process_rows(
        self, uow, batch: CustomerImportBatch, rows: list[dict], actor_user_id: str,
        allow_duplicates: bool, operation_id: str,
    ) -> None:
        existing_rows = uow.customers.find_duplicate_rows()
        for index, row in enumerate(rows):
            row_operation_id = f"{operation_id}:row{index}"
            customer_id = row.get("customer_id")
            if customer_id:
                customer = uow.customers.get(customer_id)
                if customer is None:
                    batch.record_row("ERROR")
                    continue
                if row.get("display_name"):
                    customer.display_name = row["display_name"].strip()
                if row.get("legal_name") is not None:
                    customer.legal_name = row["legal_name"].strip()
                customer.record_edit()
                uow.customers.update(customer)
                batch.record_row("UPDATED")
                self._emit(uow, CustomerEvents.UPDATED, customer.id, row_operation_id,
                          actor_user_id, source="import")
                continue

            display_name = (row.get("display_name") or "").strip()
            if not display_name:
                batch.record_row("ERROR")
                continue

            if not allow_duplicates:
                matches = self._duplicates.find_matches(
                    {"tax_identifier": row.get("tax_identifier"), "display_name": display_name,
                     "legal_name": row.get("legal_name"), "phone_e164": row.get("phone_e164"),
                     "email": row.get("email")},
                    existing_rows)
                if matches:
                    batch.record_row("DUPLICATE")
                    continue

            try:
                customer = Customer.create(
                    uow.customers.next_code(), display_name,
                    CustomerType(row.get("customer_type", CustomerType.INDIVIDUAL.value)),
                    legal_name=row.get("legal_name", ""), source="import",
                    created_by_user_id=actor_user_id, operation_id=row_operation_id)
            except (CustomerDomainError, ValueError):
                batch.record_row("ERROR")
                continue
            uow.customers.save(customer, operation_id=row_operation_id)
            batch.record_row("CREATED")
            existing_rows.append({
                "id": customer.id, "display_name": display_name,
                "legal_name": row.get("legal_name", ""),
                "tax_identifier": row.get("tax_identifier"), "phone_e164": row.get("phone_e164"),
                "email": row.get("email"),
            })
            self._emit(uow, CustomerEvents.CREATED, customer.id, row_operation_id,
                      actor_user_id, source="import")

        batch.finalize()


class ImportCustomersUseCase(_BaseUseCase):
    def execute(
        self, connection, *, actor_user_id: str, rows: list[dict], operation_id: str,
        is_sensitive: bool = False, allow_duplicates: bool = False,
    ) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.IMPORT)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        if not rows:
            return CustomerResult.fail("El lote de importación no tiene filas", "VALIDATION",
                                       operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            try:
                batch = CustomerImportBatch.start(
                    actor_user_id, len(rows), is_sensitive=is_sensitive,
                    operation_id=operation_id)
            except CustomerDomainError as exc:
                return CustomerResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.import_batches.save(batch, operation_id=operation_id)

            if is_sensitive:
                uow.import_batches.save_pending_rows(batch.id, json.dumps(rows))
                uow.audit.record(action=CustomerEvents.IMPORT_BATCH_SUBMITTED,
                                 actor_user_id=actor_user_id, customer_id=None,
                                 operation_id=operation_id,
                                 after_json=json.dumps({"batch_id": batch.id,
                                                        "total_rows": batch.total_rows}))
                self._emit(uow, CustomerEvents.IMPORT_BATCH_SUBMITTED, "", operation_id,
                          actor_user_id, batch_id=batch.id)
                return CustomerResult.ok(
                    "Lote de importación sensible enviado a aprobación", entity_id=batch.id,
                    operation_id=operation_id)

            self._process_rows(uow, batch, rows, actor_user_id, allow_duplicates, operation_id)
            uow.import_batches.update(batch)
            uow.audit.record(action=CustomerEvents.IMPORT_BATCH_COMPLETED,
                             actor_user_id=actor_user_id, customer_id=None,
                             operation_id=operation_id,
                             after_json=json.dumps({"batch_id": batch.id,
                                                    "created": batch.created_count,
                                                    "updated": batch.updated_count,
                                                    "rejected": batch.rejected_count,
                                                    "duplicate": batch.duplicate_count,
                                                    "error": batch.error_count}))
            self._emit(uow, CustomerEvents.IMPORT_BATCH_COMPLETED, "", operation_id,
                      actor_user_id, batch_id=batch.id)
        return CustomerResult.ok(
            f"Importación {batch.status.value.lower()}: {batch.created_count} creados,"
            f" {batch.updated_count} actualizados, {batch.duplicate_count} duplicados,"
            f" {batch.error_count} errores",
            entity_id=batch.id, operation_id=operation_id, status=batch.status.value,
            created=batch.created_count, updated=batch.updated_count,
            duplicate=batch.duplicate_count, error=batch.error_count)


class ApproveCustomerImportUseCase(_BaseUseCase):
    def __init__(self, authorization: CustomerAuthorizationPolicy | None = None) -> None:
        super().__init__(authorization)
        self._sod = CustomerSegregationOfDutiesPolicy()

    def execute(self, connection, *, actor_user_id: str, batch_id: str, operation_id: str,
                allow_duplicates: bool = False) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.IMPORT_APPROVE)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            batch = uow.import_batches.get(batch_id)
            if batch is None:
                return CustomerResult.fail("El lote de importación no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            try:
                self._sod.enforce_sensitive_import_approver_distinct(
                    batch.submitted_by_user_id, actor_user_id, is_sensitive=batch.is_sensitive)
            except CustomerSegregationOfDutiesError as exc:
                return CustomerResult.fail(str(exc), "SOD_VIOLATION", operation_id=operation_id)
            try:
                batch.approve(actor_user_id)
            except CustomerDomainError as exc:
                return CustomerResult.fail(str(exc), "VALIDATION", operation_id=operation_id)

            rows_json = uow.import_batches.get_pending_rows(batch.id)
            rows: list[dict] = json.loads(rows_json) if rows_json else []
            self._process_rows(uow, batch, rows, actor_user_id, allow_duplicates, operation_id)
            uow.import_batches.update(batch)
            uow.import_batches.clear_pending_rows(batch.id)

            uow.audit.record(action=CustomerEvents.IMPORT_BATCH_APPROVED,
                             actor_user_id=actor_user_id, customer_id=None,
                             operation_id=operation_id,
                             after_json=json.dumps({"batch_id": batch.id,
                                                    "created": batch.created_count,
                                                    "updated": batch.updated_count}))
            self._emit(uow, CustomerEvents.IMPORT_BATCH_APPROVED, "", operation_id,
                      actor_user_id, batch_id=batch.id)
        return CustomerResult.ok(
            f"Importación aprobada y {batch.status.value.lower()}", entity_id=batch.id,
            operation_id=operation_id, status=batch.status.value,
            created=batch.created_count, updated=batch.updated_count)


class RejectCustomerImportUseCase(_BaseUseCase):
    def execute(self, connection, *, actor_user_id: str, batch_id: str,
                operation_id: str) -> CustomerResult:
        try:
            self._auth.require(actor_user_id, CustomerPermissions.IMPORT_APPROVE)
        except CustomerDomainError as exc:
            return CustomerResult.fail(str(exc), "PERMISSION_DENIED", operation_id=operation_id)
        with CustomerUnitOfWork(connection) as uow:
            batch = uow.import_batches.get(batch_id)
            if batch is None:
                return CustomerResult.fail("El lote de importación no existe", "NOT_FOUND",
                                           operation_id=operation_id)
            try:
                batch.reject()
            except CustomerDomainError as exc:
                return CustomerResult.fail(str(exc), "VALIDATION", operation_id=operation_id)
            uow.import_batches.update(batch)
            uow.import_batches.clear_pending_rows(batch.id)
        return CustomerResult.ok("Lote de importación rechazado", entity_id=batch.id,
                                 operation_id=operation_id)
