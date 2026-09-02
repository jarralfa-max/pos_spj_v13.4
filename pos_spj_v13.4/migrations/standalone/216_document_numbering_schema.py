# migrations/standalone/216_document_numbering_schema.py
"""SET-16 — Document Numbering schema (Numeración: Sequences, Reservas,
Reset, Idempotencia).

Creates `document_number_sequences` (one row per prefix — the counter
itself) and `document_number_reservations` (one row per successful
reservation, keyed UNIQUE(sequence_id, operation_id) — the idempotency
ledger a caller's repeated request with the same operation_id resolves
against instead of advancing the counter again).

DDL lives in backend/infrastructure/db/schema/document_output_schema.py;
only this migration may call create_document_numbering_schema.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.document_output_schema import create_document_numbering_schema

logger = logging.getLogger("spj.migrations.216")


def run(conn) -> None:
    create_document_numbering_schema(conn)
    conn.commit()
    logger.info("216: document_number_sequences/document_number_reservations schema created.")


up = run
