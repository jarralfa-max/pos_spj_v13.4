# migrations/standalone/214_document_output_schema.py
"""SET-11 — Document Output schema (Templates, Versiones, PrintJobs).

Creates `document_templates`, `document_template_versions`, and
`print_jobs` (§24-27). Renderers (`DocumentRendererPort`) and the print
worker's queue-selection policy are pure domain/infrastructure-port
concepts with no schema of their own — see
`backend/domain/document_output/rendering_ports.py` and
`policies/print_job_queue_policy.py`.

Depends on migrations 211 (devices) and 212 (print_routes) — this
migration's FKs (`print_jobs.printer_device_id`, `print_jobs.print_route_id`)
reference tables created there.

DDL lives in backend/infrastructure/db/schema/document_output_schema.py;
only this migration may call create_document_output_schema.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.document_output_schema import create_document_output_schema

logger = logging.getLogger("spj.migrations.214")


def run(conn) -> None:
    create_document_output_schema(conn)
    conn.commit()
    logger.info("214: document_templates/document_template_versions/print_jobs schema created.")


up = run
