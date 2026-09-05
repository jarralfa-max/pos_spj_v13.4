"""Commands para transicionar la etapa interna de un producto (PROD-6, §13)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SetInternalStageCommand:
    operation_id: str
    product_id: str
    stage: str
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "product_id", "stage")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")
