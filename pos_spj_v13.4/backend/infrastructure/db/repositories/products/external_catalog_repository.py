"""ExternalCatalogRepository — persistence for external sources / records / batches (PROD-15).

Stores provenance, data-quality score and matching. Provides the lookup callables
the matching service needs (barcode → product_id, normalized name → product_id).
Never commits (the caller owns the transaction).
"""

from __future__ import annotations

from backend.domain.products.entities.external_catalog_source import (
    ExternalCatalogSource,
)
from backend.domain.products.entities.external_product_record import (
    ExternalProductRecord,
)
from backend.domain.products.entities.product_import_batch import ProductImportBatch
from backend.domain.products.external_enums import (
    ExternalProviderType,
    ExternalRecordStatus,
    ImportBatchStatus,
)
from backend.domain.products.value_objects.data_quality_score import DataQualityScore


class ExternalCatalogRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    # ── sources ───────────────────────────────────────────────────────────
    def save_source(self, s: ExternalCatalogSource) -> None:
        self._conn.execute(
            """INSERT INTO external_catalog_sources
               (id, code, name, provider_type, endpoint, active)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                 endpoint=excluded.endpoint, active=excluded.active""",
            (s.id, s.code, s.name, s.provider_type.value, s.endpoint, int(s.active)))

    def get_source(self, source_id: str) -> ExternalCatalogSource | None:
        row = self._conn.execute(
            "SELECT * FROM external_catalog_sources WHERE id=?", (source_id,)).fetchone()
        if row is None:
            return None
        return ExternalCatalogSource(
            id=row["id"], code=row["code"], name=row["name"],
            provider_type=ExternalProviderType(row["provider_type"]),
            endpoint=row["endpoint"], active=bool(row["active"]))

    # ── records ───────────────────────────────────────────────────────────
    def save_record(self, r: ExternalProductRecord, *, batch_id: str | None = None) -> None:
        score = r.data_quality_score.value if r.data_quality_score else 0
        self._conn.execute(
            """INSERT INTO external_product_records
               (id, source_id, external_id, name, barcode, brand, category,
                net_weight, unit, raw_payload, status, matched_product_id,
                data_quality_score, batch_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(source_id, external_id) DO UPDATE SET
                 name=excluded.name, barcode=excluded.barcode, status=excluded.status,
                 matched_product_id=excluded.matched_product_id,
                 data_quality_score=excluded.data_quality_score""",
            (r.id, r.source_id, r.external_id, r.name, r.barcode, r.brand, r.category,
             r.net_weight, r.unit, r.raw_payload, r.status.value, r.matched_product_id,
             score, batch_id))

    def get_record(self, record_id: str) -> ExternalProductRecord | None:
        row = self._conn.execute(
            "SELECT * FROM external_product_records WHERE id=?", (record_id,)).fetchone()
        if row is None:
            return None
        return ExternalProductRecord(
            id=row["id"], source_id=row["source_id"], external_id=row["external_id"],
            name=row["name"], barcode=row["barcode"], brand=row["brand"],
            category=row["category"], net_weight=row["net_weight"], unit=row["unit"],
            raw_payload=row["raw_payload"],
            status=ExternalRecordStatus(row["status"]),
            matched_product_id=row["matched_product_id"],
            data_quality_score=DataQualityScore(int(row["data_quality_score"])))

    def records_for_source(self, source_id: str, *, status: ExternalRecordStatus | None = None):
        if status is not None:
            rows = self._conn.execute(
                "SELECT id FROM external_product_records WHERE source_id=? AND status=?",
                (source_id, status.value)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id FROM external_product_records WHERE source_id=?",
                (source_id,)).fetchall()
        return [self.get_record(r["id"]) for r in rows]

    # ── matching lookups ──────────────────────────────────────────────────
    def barcode_lookup(self):
        def lookup(barcode: str) -> str | None:
            row = self._conn.execute(
                "SELECT product_id FROM product_barcodes WHERE barcode_value=? AND active=1",
                (barcode,)).fetchone()
            return row["product_id"] if row else None
        return lookup

    def name_lookup(self):
        def lookup(normalized: str) -> str | None:
            row = self._conn.execute(
                "SELECT id FROM products WHERE name_normalized=? LIMIT 1",
                (normalized,)).fetchone()
            return row["id"] if row else None
        return lookup

    # ── batches ───────────────────────────────────────────────────────────
    def save_batch(self, b: ProductImportBatch) -> None:
        self._conn.execute(
            """INSERT INTO product_import_batches
               (id, source_id, status, total_records, matched_records,
                imported_records, failed_records, created_by)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET status=excluded.status,
                 total_records=excluded.total_records,
                 matched_records=excluded.matched_records,
                 imported_records=excluded.imported_records,
                 failed_records=excluded.failed_records""",
            (b.id, b.source_id, b.status.value, b.total_records, b.matched_records,
             b.imported_records, b.failed_records, b.created_by))

    def get_batch(self, batch_id: str) -> ProductImportBatch | None:
        row = self._conn.execute(
            "SELECT * FROM product_import_batches WHERE id=?", (batch_id,)).fetchone()
        if row is None:
            return None
        return ProductImportBatch(
            id=row["id"], source_id=row["source_id"],
            status=ImportBatchStatus(row["status"]), total_records=row["total_records"],
            matched_records=row["matched_records"], imported_records=row["imported_records"],
            failed_records=row["failed_records"], created_by=row["created_by"])
