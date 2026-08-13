"""CustomerImportPreviewQuery (§47) — read-only dry run of an import batch:
per-row outcome (WOULD_CREATE/WOULD_UPDATE/DUPLICATE/ERROR) without writing
anything. Lets the UI show file→mapeo→preview→validación→duplicados before
the user confirms and ``ImportCustomersUseCase`` actually runs.

Gated by IMPORT (the same permission that gates actually running the
import) — previewing a batch is part of the same submit flow, not a
separate viewing capability.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.permissions import CustomerPermissions
from backend.domain.customers.policies.duplicate_policy import CustomerDuplicatePolicy
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork


@dataclass(frozen=True)
class CustomerImportRowPreview:
    row_number: int
    outcome: str
    reasons: tuple[str, ...] = ()


class CustomerImportPreviewQuery:
    def __init__(self, connection,
                authorization: CustomerAuthorizationPolicy | None = None) -> None:
        self._uow = CustomerUnitOfWork(connection)
        self._auth = authorization or CustomerAuthorizationPolicy()
        self._duplicates = CustomerDuplicatePolicy()

    def preview(self, rows: list[dict], *,
               actor_user_id: str) -> list[CustomerImportRowPreview]:
        self._auth.require(actor_user_id, CustomerPermissions.IMPORT)
        existing_rows = self._uow.customers.find_duplicate_rows()
        previews: list[CustomerImportRowPreview] = []
        for index, row in enumerate(rows):
            if row.get("customer_id"):
                exists = self._uow.customers.get(row["customer_id"]) is not None
                previews.append(CustomerImportRowPreview(
                    index, "WOULD_UPDATE" if exists else "ERROR"))
                continue
            display_name = (row.get("display_name") or "").strip()
            if not display_name:
                previews.append(CustomerImportRowPreview(index, "ERROR", ("display_name vacío",)))
                continue
            matches = self._duplicates.find_matches(
                {"tax_identifier": row.get("tax_identifier"), "display_name": display_name,
                 "legal_name": row.get("legal_name"), "phone_e164": row.get("phone_e164"),
                 "email": row.get("email")},
                existing_rows)
            if matches:
                reasons = tuple(sorted({r for m in matches for r in m.reasons}))
                previews.append(CustomerImportRowPreview(index, "DUPLICATE", reasons))
            else:
                previews.append(CustomerImportRowPreview(index, "WOULD_CREATE"))
        return previews
