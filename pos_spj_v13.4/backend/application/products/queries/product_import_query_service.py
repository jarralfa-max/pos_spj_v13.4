"""ProductImportQueryService — read side de la importación (jobs + preview). Read-only."""

from __future__ import annotations

import json


class ProductImportQueryService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def list_jobs(self, *, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, filename, source_format, status, total_rows, valid_rows, "
            "invalid_rows, created_rows, created_by, approved_by, created_at "
            "FROM product_import_jobs ORDER BY created_at DESC LIMIT ?",
            (int(limit),)).fetchall()
        return [dict(r) for r in rows]

    def get_job(self, job_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM product_import_jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row is not None else None

    def preview_rows(self, job_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT row_number, payload, status, error, product_id "
            "FROM product_import_rows WHERE job_id=? ORDER BY row_number",
            (job_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["payload"] = json.loads(d["payload"])
            out.append(d)
        return out
