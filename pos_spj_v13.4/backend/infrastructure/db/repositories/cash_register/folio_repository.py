"""Folios consecutivos de los documentos de Caja (Corte X, Corte Z) por sucursal.

Se reservan dentro de la transacción del `CashRegisterUnitOfWork`: si el corte
no se confirma, el consecutivo no avanza.
"""
from __future__ import annotations

from backend.infrastructure.db.repositories.document_output.branch_document_folio import (
    next_branch_folio,
)


class CashDocumentFolioRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def next(self, kind: str, branch_id: str) -> str | None:
        return next_branch_folio(self._connection, kind, branch_id)
