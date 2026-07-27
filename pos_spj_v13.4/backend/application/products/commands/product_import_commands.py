"""Commands del contexto de importación de productos (CSV/XLSX)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CreateImportBatchCommand:
    operation_id: str
    filename: str
    data: bytes
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "filename") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")
        if not self.data:
            raise ValueError("El archivo está vacío")


@dataclass(frozen=True)
class ImportBatchActionCommand:
    operation_id: str
    job_id: str
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "job_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")
