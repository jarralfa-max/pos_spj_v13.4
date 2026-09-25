"""ProcessingExecutionStrategy — qué cambia al ejecutar según la FAMILIA del proceso.

Una sola ejecución productiva para todos los procesos. Lo que difiere entre un
despiece, una formulación, un empaque o un acondicionamiento se resuelve aquí,
por familia de proceso, a partir de la definición congelada — nunca por
especie ni por producto. La especie y el producto son datos; el proceso es
comportamiento.

Regla común a todas las familias: lo esperado de cada salida es
`factor × entrada total consumida`, con el factor que congeló la definición.
El rendimiento real sale de las salidas reales; no se asume que
entrada = salida + merma.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.meat_processing.entities.processing_recipe_snapshot import (
    InputRole,
    ProcessFamily,
    ProcessingRecipeSnapshot,
)

_Q = Decimal("0.001")
_PCT = Decimal("0.01")
_HUNDRED = Decimal("100")


@dataclass(frozen=True)
class ExpectedOutput:
    product_id: str
    output_type: str
    goes_to_stock: bool
    expected_weight: Decimal
    expected_yield_pct: Decimal
    quality_gate: bool


@dataclass(frozen=True)
class OutputResult:
    product_id: str
    output_type: str
    expected_weight: Decimal
    actual_weight: Decimal
    difference_weight: Decimal
    expected_yield_pct: Decimal
    yield_pct: Decimal
    variance_pct: Decimal | None


class ProcessingExecutionStrategy:
    family: ProcessFamily

    def expected_outputs(self, snapshot: ProcessingRecipeSnapshot,
                         total_input: Decimal) -> list[ExpectedOutput]:
        esperado = []
        for o in snapshot.outputs:
            pct = (o.expected_yield_pct if o.expected_yield_pct is not None
                   else o.expected_factor * _HUNDRED)
            esperado.append(ExpectedOutput(
                product_id=o.product_id, output_type=o.output_type.value,
                goes_to_stock=o.goes_to_stock,
                expected_weight=(o.expected_factor * total_input).quantize(_Q),
                expected_yield_pct=Decimal(str(pct)).quantize(_PCT),
                quality_gate=o.quality_gate))
        return esperado

    def results(self, snapshot: ProcessingRecipeSnapshot, total_input: Decimal,
                actual: dict[str, Decimal]) -> list[OutputResult]:
        filas = []
        for e in self.expected_outputs(snapshot, total_input):
            real = actual.get(e.product_id, Decimal("0")).quantize(_Q)
            variacion = (((real - e.expected_weight) / e.expected_weight) * _HUNDRED).quantize(
                _PCT) if e.expected_weight > 0 else None
            filas.append(OutputResult(
                product_id=e.product_id, output_type=e.output_type,
                expected_weight=e.expected_weight, actual_weight=real,
                difference_weight=real - e.expected_weight,
                expected_yield_pct=e.expected_yield_pct,
                yield_pct=((real / total_input) * _HUNDRED).quantize(_PCT)
                if total_input > 0 else Decimal("0"),
                variance_pct=variacion))
        return filas

    def validate(self, snapshot: ProcessingRecipeSnapshot, consumed: dict[str, Decimal],
                 actual: dict[str, Decimal]) -> list[str]:
        problemas = []
        planeadas = {o.product_id for o in snapshot.outputs}
        ajenas = sorted(set(actual) - planeadas)
        if ajenas:
            problemas.append("Salidas que no están en la definición congelada: "
                             + ", ".join(ajenas))
        if any(v < 0 for v in actual.values()) or any(v < 0 for v in consumed.values()):
            problemas.append("Los pesos no pueden ser negativos.")
        if sum(consumed.values(), Decimal("0")) <= 0:
            problemas.append("Captura el peso real consumido.")
        if not any(actual.get(o.product_id, Decimal("0")) > 0
                   for o in snapshot.outputs if o.goes_to_stock):
            problemas.append("Captura el peso de al menos una salida que entre a existencia.")
        return problemas + self._family_problems(snapshot, consumed, actual)

    def _family_problems(self, snapshot, consumed, actual) -> list[str]:
        return []


class DisassemblyStrategy(ProcessingExecutionStrategy):
    """Una entrada, varias salidas."""

    family = ProcessFamily.DISASSEMBLY

    def _family_problems(self, snapshot, consumed, actual):
        fuentes = [i for i in snapshot.inputs if i.role is InputRole.SOURCE]
        if len(fuentes) != 1:
            return ["Un despiece consume exactamente una entrada."]
        return []


class FormulationStrategy(ProcessingExecutionStrategy):
    """Varias entradas (receta/BOM), una o pocas salidas."""

    family = ProcessFamily.FORMULATION

    def _family_problems(self, snapshot, consumed, actual):
        faltan = [i.product_id for i in snapshot.inputs
                  if i.role is InputRole.COMPONENT and consumed.get(i.product_id, 0) <= 0
                  and not snapshot.substitutions]
        return (["Componentes de la receta sin consumo: " + ", ".join(faltan)]
                if faltan else [])


class IdentityTransformationStrategy(ProcessingExecutionStrategy):
    """Empaque y acondicionamiento: el mismo producto entra y sale."""

    def _family_problems(self, snapshot, consumed, actual):
        entrada = {i.product_id for i in snapshot.inputs}
        salidas = {o.product_id for o in snapshot.outputs if o.goes_to_stock}
        if not salidas <= entrada:
            return ["En este proceso el producto que sale debe ser el mismo que entra."]
        return []


class PackagingStrategy(IdentityTransformationStrategy):
    family = ProcessFamily.PACKAGING


class ConditioningStrategy(IdentityTransformationStrategy):
    family = ProcessFamily.CONDITIONING


STRATEGIES: dict[ProcessFamily, ProcessingExecutionStrategy] = {
    ProcessFamily.DISASSEMBLY: DisassemblyStrategy(),
    ProcessFamily.FORMULATION: FormulationStrategy(),
    ProcessFamily.PACKAGING: PackagingStrategy(),
    ProcessFamily.CONDITIONING: ConditioningStrategy(),
}


def strategy_for(snapshot: ProcessingRecipeSnapshot) -> ProcessingExecutionStrategy | None:
    return STRATEGIES.get(snapshot.family) if snapshot.family else None
