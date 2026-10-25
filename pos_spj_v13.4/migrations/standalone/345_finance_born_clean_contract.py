"""345 — Contrato born-clean del esquema financiero (FIN-ERP, 2026-10-21).

No convierte ni rescata nada (prompt maestro de Finanzas §1): verifica que la
base tenga EXACTAMENTE el contrato de ``finance_schema.py`` que creó la
migración 117. Una base de desarrollo nacida con un esquema financiero
anterior no se adapta: la migración falla con la instrucción de regenerarla y
la aplicación no arranca a medias.
"""

from __future__ import annotations

import logging

from backend.infrastructure.db.schema.finance_schema import assert_finance_schema_contract

logger = logging.getLogger("spj.migrations.345")


def run(conn) -> None:
    assert_finance_schema_contract(conn)
    logger.info("345: esquema financiero conforme al contrato born-clean.")


up = run
