"""Commands del catálogo de clasificación cárnica (PROD-3: especies, regiones
anatómicas, cortes)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CreateSpeciesCommand:
    operation_id: str
    code: str
    name: str
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "code", "name")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class SetSpeciesActiveCommand:
    operation_id: str
    species_id: str
    active: bool
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "species_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class CreateAnatomicalRegionCommand:
    operation_id: str
    species_id: str
    code: str
    name: str
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "species_id", "code", "name")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class SetAnatomicalRegionActiveCommand:
    operation_id: str
    region_id: str
    active: bool
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "region_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class CreateCutClassificationCommand:
    operation_id: str
    species_id: str
    anatomical_region_id: str
    code: str
    name: str
    cut_level: str
    user_id: str | None = None
    bone_status: str = "NOT_APPLICABLE"
    fat_class: str = "NOT_APPLICABLE"
    quality_grade: str | None = None
    parent_cut_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "species_id", "anatomical_region_id",
                               "code", "name", "cut_level")
                   if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")


@dataclass(frozen=True)
class SetCutClassificationActiveCommand:
    operation_id: str
    cut_id: str
    active: bool
    user_id: str | None = None

    def validate(self) -> None:
        missing = [f for f in ("operation_id", "cut_id") if not getattr(self, f)]
        if missing:
            raise ValueError(f"Faltan campos requeridos: {', '.join(missing)}")
