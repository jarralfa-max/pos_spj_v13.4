"""ProcessingMasterDataRequirementPolicy — qué definición productiva exige cada
proceso antes de poder liberarse.

Antes una orden se liberaba aunque Productos no tuviera ninguna definición
para ella, y la falta se descubría al ejecutar (o nunca). Esta política se
evalúa al congelar la definición: si falta algo obligatorio, la orden no pasa
a RELEASED.

Nunca se asume que todo proceso es un despiece ni que todo usa receta: el
requisito sale de la FAMILIA del proceso, y cualquier proceso concreto puede
sobrescribirse por configuración (`overrides`) sin tocar código.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.meat_processing.entities.processing_recipe_snapshot import (
    MasterDataKind,
    ProcessFamily,
    ProcessingRecipeSnapshot,
    process_family,
)
from backend.domain.meat_processing.enums import ProcessType

#: Lo mínimo que cada familia necesita para poder ejecutarse. El perfil de
#: rendimiento es opcional por defecto: cuando existe, afina lo esperado.
DEFAULT_FAMILY_REQUIREMENTS: dict[ProcessFamily, frozenset[MasterDataKind]] = {
    ProcessFamily.DISASSEMBLY: frozenset({MasterDataKind.CUTTING_SCHEME}),
    ProcessFamily.FORMULATION: frozenset({MasterDataKind.RECIPE}),
    ProcessFamily.PACKAGING: frozenset({MasterDataKind.PACKAGING_SPEC}),
    ProcessFamily.CONDITIONING: frozenset(),
}

_LABELS_ES = {
    MasterDataKind.RECIPE: "receta / BOM",
    MasterDataKind.CUTTING_SCHEME: "esquema de corte",
    MasterDataKind.YIELD_PROFILE: "perfil de rendimiento",
    MasterDataKind.PACKAGING_SPEC: "especificación de empaque (presentación)",
}


@dataclass(frozen=True)
class MasterDataCheck:
    process_type: ProcessType
    required: frozenset[MasterDataKind]
    missing: frozenset[MasterDataKind]
    problems: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.missing and not self.problems

    def message(self) -> str:
        partes = []
        if self.missing:
            faltan = ", ".join(_LABELS_ES[k] for k in sorted(self.missing, key=lambda k: k.value))
            partes.append(f"Productos no tiene la definición que exige el proceso: {faltan}.")
        partes.extend(self.problems)
        return " ".join(partes)


@dataclass(frozen=True)
class ProcessingMasterDataRequirementPolicy:
    #: Proceso → requisitos, por encima de los de su familia (configuración).
    overrides: dict[ProcessType, frozenset[MasterDataKind]] = field(default_factory=dict)

    def required_for(self, process_type: ProcessType) -> frozenset[MasterDataKind] | None:
        tipo = ProcessType(process_type)
        if tipo in self.overrides:
            return frozenset(self.overrides[tipo])
        familia = process_family(tipo)
        if familia is None:
            return None
        return DEFAULT_FAMILY_REQUIREMENTS[familia]

    def check(self, process_type: ProcessType,
              snapshot: ProcessingRecipeSnapshot | None) -> MasterDataCheck:
        tipo = ProcessType(process_type)
        requeridos = self.required_for(tipo)
        if requeridos is None:
            return MasterDataCheck(
                tipo, frozenset(), frozenset(),
                (f"El proceso {tipo.value} todavía no tiene comportamiento productivo "
                 "definido; no se puede liberar.",))
        presentes = snapshot.present_master_data if snapshot is not None else frozenset()
        faltan = frozenset(requeridos - presentes)
        problemas = []
        if snapshot is not None and not faltan:
            if not snapshot.inputs:
                problemas.append("La definición no tiene ninguna entrada que consumir.")
            if not any(o.goes_to_stock for o in snapshot.outputs):
                problemas.append("La definición no tiene ninguna salida que entre a existencia.")
        elif snapshot is None and not requeridos:
            problemas.append("No se pudo resolver la definición del producto objetivo.")
        return MasterDataCheck(tipo, requeridos, faltan, tuple(problemas))
