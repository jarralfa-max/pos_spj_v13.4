"""External-catalog enums for the products bounded context (§15).

PROD-15. Products can search/import from external catalogs (Open Food Facts,
supplier catalogs, CSV). Every external record is stored with its provenance and a
data-quality score, and (per policy) reviewed before it becomes a canonical product.
"""

from __future__ import annotations

from enum import Enum


class ExternalProviderType(str, Enum):
    OPEN_FOOD_FACTS = "OPEN_FOOD_FACTS"
    SUPPLIER = "SUPPLIER"
    CSV = "CSV"
    MANUAL = "MANUAL"


class ExternalRecordStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    MATCHED = "MATCHED"                 # matched to an existing product
    APPROVED = "APPROVED"              # review passed, ready to import
    IMPORTED = "IMPORTED"
    REJECTED = "REJECTED"


class ImportBatchStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
