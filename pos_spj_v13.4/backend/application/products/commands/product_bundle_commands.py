"""Commands del contexto de combos/kits (§28) — capa de aplicación.

Los componentes viajan como dicts desde la UI; los use cases los convierten en
entidades ``BundleComponent`` (que validan cantidad Decimal, unidad).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CreateBundleCommand:
    operation_id: str
    product_id: str
    bundle_type: str
    name: str
    components: list[dict] = field(default_factory=list)
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "product_id", "bundle_type", "name")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class UpdateBundleVersionCommand:
    operation_id: str
    version_id: str
    components: list[dict] = field(default_factory=list)
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "version_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class BundleVersionTransitionCommand:
    operation_id: str
    version_id: str
    user_id: str | None = None
    reason: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "version_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")
