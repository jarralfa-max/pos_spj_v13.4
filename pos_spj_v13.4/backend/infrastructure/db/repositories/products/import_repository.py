"""ProductImportRepository — staging de importación (jobs + filas).

Escritura parametrizada, sin commit (el caso de uso es dueño de la transacción).
"""

from __future__ import annotations

import json


class ProductImportRepository:
    def __init__(self, connection) -> None:
        self._conn = connection

    # ── jobs ────────────────────────────────────────────────────────────────
    def create_job(self, *, job_id: str, filename: str, source_format: str,
                   total: int, valid: int, invalid: int, created_by: str | None
                   ) -> None:
        self._conn.execute(
            "INSERT INTO product_import_jobs "
            "(id, filename, source_format, status, total_rows, valid_rows, "
            "invalid_rows, created_by) VALUES (?,?,?,'PREVIEWED',?,?,?,?)",
            (job_id, filename, source_format, total, valid, invalid, created_by))

    def get_job(self, job_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM product_import_jobs WHERE id=?", (job_id,)).fetchone()
        return dict(row) if row is not None else None

    def set_status(self, job_id: str, status: str, *,
                   approved_by: str | None = None) -> None:
        if approved_by is not None:
            self._conn.execute(
                "UPDATE product_import_jobs SET status=?, approved_by=?, "
                "updated_at=datetime('now') WHERE id=?",
                (status, approved_by, job_id))
        else:
            self._conn.execute(
                "UPDATE product_import_jobs SET status=?, updated_at=datetime('now') "
                "WHERE id=?", (status, job_id))

    def set_created_count(self, job_id: str, created: int) -> None:
        self._conn.execute(
            "UPDATE product_import_jobs SET created_rows=?, "
            "updated_at=datetime('now') WHERE id=?", (created, job_id))

    # ── rows ──────────────────────────────────────────────────────────────
    def add_row(self, *, row_id: str, job_id: str, row_number: int, payload: dict,
                status: str, error: str | None) -> None:
        self._conn.execute(
            "INSERT INTO product_import_rows "
            "(id, job_id, row_number, payload, status, error) VALUES (?,?,?,?,?,?)",
            (row_id, job_id, row_number, json.dumps(payload), status, error))

    def list_rows(self, job_id: str, *, status: str | None = None) -> list[dict]:
        sql = ("SELECT id, row_number, payload, status, error, product_id "
               "FROM product_import_rows WHERE job_id=?")
        params: list = [job_id]
        if status:
            sql += " AND status=?"
            params.append(status)
        sql += " ORDER BY row_number"
        out = []
        for r in self._conn.execute(sql, params).fetchall():
            d = dict(r)
            d["payload"] = json.loads(d["payload"])
            out.append(d)
        return out

    def mark_created(self, row_id: str, product_id: str) -> None:
        self._conn.execute(
            "UPDATE product_import_rows SET status='CREATED', product_id=? WHERE id=?",
            (product_id, row_id))
