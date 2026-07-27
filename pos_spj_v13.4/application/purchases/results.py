"""
application/purchases/results.py
──────────────────────────────────
Tipos de resultado para el módulo de Compras.

PurchaseResult es el tipo canónico de retorno de TraditionalPurchaseUC.
Incluye todos los campos de ResultadoCompraDTO más metadatos de document_type.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from application.purchases.states import DocumentType


@dataclass
class PurchaseResult:
    """
    Resultado de una operación de compra.

    ok=True  → operación exitosa, folio disponible
    ok=False → error, campo error describe el problema
    """
    ok:      bool
    folio:   str = ""
    error:   str = ""

    # Metadatos de trazabilidad
    document_type:      DocumentType    = DocumentType.DIRECT
    recetas_procesadas: list[str]       = field(default_factory=list)
    warnings:           list[str]       = field(default_factory=list)

    # Snapshot de auditoría
    audit_before: dict = field(default_factory=dict)
    audit_after:  dict = field(default_factory=dict)

    @classmethod
    def from_resultado_dto(cls, dto, document_type: DocumentType = DocumentType.DIRECT) -> "PurchaseResult":
        """Adapta ResultadoCompraDTO al tipo canónico."""
        return cls(
            ok=dto.ok,
            folio=dto.folio,
            error=dto.error,
            document_type=document_type,
            recetas_procesadas=dto.recetas_procesadas,
            warnings=dto.warnings,
            audit_before=dto.audit_before,
            audit_after=dto.audit_after,
        )

    @classmethod
    def error_result(cls, message: str) -> "PurchaseResult":
        return cls(ok=False, error=message)
