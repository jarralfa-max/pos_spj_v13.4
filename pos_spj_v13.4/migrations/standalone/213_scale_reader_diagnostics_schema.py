# migrations/standalone/213_scale_reader_diagnostics_schema.py
"""SET-9 — Scale/Reader Diagnostics schema (Básculas y lectores: puertos,
protocolos, estabilidad, diagnóstico).

Creates `device_test_results` (§21 — generalized append-only diagnostic
log, shared by scales and readers going forward; printers keep the
already-shipped `printer_test_results` from migration 212, see
`backend/domain/device_management/entities/device_test_result.py`'s
docstring for why). Ports/protocols/stability
(`SerialPortProfile`/`ScaleProtocol`/`WeightReading`/`StabilityPolicy`)
are pure domain concepts with no new schema of their own.

DDL lives in backend/infrastructure/db/schema/device_management_schema.py;
only this migration may call create_scale_reader_diagnostics_schema.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.device_management_schema import (
    create_scale_reader_diagnostics_schema,
)

logger = logging.getLogger("spj.migrations.213")


def run(conn) -> None:
    create_scale_reader_diagnostics_schema(conn)
    conn.commit()
    logger.info("213: device_test_results schema created.")


up = run
