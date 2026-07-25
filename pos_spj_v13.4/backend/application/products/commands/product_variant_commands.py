"""Commands del contexto de variantes de producto (P1-03)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class GenerateVariantsCommand:
    operation_id: str
    parent_product_id: str
    # Ejes: {attribute_id: [option_id, …]}. El producto cartesiano define las
    # variantes; cada combinación aún inexistente crea un producto hijo en DRAFT.
    axes: dict[str, list[str]] = field(default_factory=dict)
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "parent_product_id")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")
        if not self.axes:
            raise ValueError("Se requiere al menos un eje de variación")
