"""ProductImportBatch — one run of importing external records (§15).

Groups the records fetched in a single search/import from a source, with counts and
status. Approval of the batch (§38 IMPORT_APPROVE) is a separate authorized step.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.exceptions import InvalidExternalRecordError
from backend.domain.products.external_enums import ImportBatchStatus
from backend.shared.ids import new_uuid


@dataclass
class ProductImportBatch:
    source_id: str
    id: str = field(default_factory=new_uuid)
    status: ImportBatchStatus = ImportBatchStatus.PENDING
    total_records: int = 0
    matched_records: int = 0
    imported_records: int = 0
    failed_records: int = 0
    created_by: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id:
            raise InvalidExternalRecordError("El lote de importación requiere fuente")
        if not isinstance(self.status, ImportBatchStatus):
            self.status = ImportBatchStatus(str(self.status))

    def finalize(self) -> None:
        if self.failed_records and self.imported_records:
            self.status = ImportBatchStatus.PARTIAL
        elif self.failed_records and not self.imported_records:
            self.status = ImportBatchStatus.FAILED
        else:
            self.status = ImportBatchStatus.COMPLETED
