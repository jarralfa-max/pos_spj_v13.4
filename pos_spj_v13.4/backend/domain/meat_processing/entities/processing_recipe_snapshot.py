"""ProcessingRecipeSnapshot — la definición productiva congelada de una orden.

POR QUÉ EXISTE
--------------
`ReleaseProcessingOrderUseCase` guardaba sólo tres ids de versión (receta,
esquema de corte, perfil de rendimiento) y la ejecución volvía a leer
`CuttingSchemeRepository` para saber qué producir. Una orden liberada dependía
así de la definición MUTABLE de Productos. Este objeto es la foto completa que
se congela al preparar/liberar la orden y que la ejecución lee en exclusiva:
Productos puede activar nuevas versiones sin tocar órdenes ya liberadas.

MODELO GENÉRICO, NO POR ESPECIE
-------------------------------
Nada aquí nombra especies, cortes ni productos: todo son datos. Lo único que
cambia el comportamiento es la FAMILIA de proceso (`ProcessFamily`):

- DISASSEMBLY: una entrada → varias salidas (despiece, deshuese, recorte,
  porcionado). La entrada es `target_product_id`; las salidas y sus factores
  salen del esquema de corte (kg de salida por kg de entrada).
- FORMULATION: varias entradas → una o pocas salidas (molido, mezcla, marinado,
  formulación). `target_product_id` es la SALIDA; los componentes salen de la
  receta.
- PACKAGING: el mismo producto cambia de presentación (empaque, reempaque,
  etiquetado).
- CONDITIONING: el mismo producto cambia de estado (congelado, descongelado,
  enfriado).

Todos los números son `Decimal`; todas las identidades, UUIDv7.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from backend.domain.meat_processing.entities._validation import (
    decimal_value,
    optional_decimal_value,
    optional_uuid,
    required_uuid,
)
from backend.domain.meat_processing.enums import OutputType, ProcessType
from backend.domain.meat_processing.exceptions import MeatProcessingInvariantError
from backend.shared.ids import new_uuid


class ProcessFamily(str, Enum):
    DISASSEMBLY = "DISASSEMBLY"
    FORMULATION = "FORMULATION"
    PACKAGING = "PACKAGING"
    CONDITIONING = "CONDITIONING"


#: Comportamiento por proceso. Los procesos `*_FUTURE` no tienen familia: no se
#: pueden liberar hasta que exista su definición productiva.
PROCESS_FAMILIES: dict[ProcessType, ProcessFamily] = {
    ProcessType.CUTTING: ProcessFamily.DISASSEMBLY,
    ProcessType.DISASSEMBLY: ProcessFamily.DISASSEMBLY,
    ProcessType.DEBONING: ProcessFamily.DISASSEMBLY,
    ProcessType.TRIMMING: ProcessFamily.DISASSEMBLY,
    ProcessType.PORTIONING: ProcessFamily.DISASSEMBLY,
    ProcessType.GRINDING: ProcessFamily.FORMULATION,
    ProcessType.MIXING: ProcessFamily.FORMULATION,
    ProcessType.MARINATION: ProcessFamily.FORMULATION,
    ProcessType.FORMULATION: ProcessFamily.FORMULATION,
    ProcessType.PACKAGING: ProcessFamily.PACKAGING,
    ProcessType.REPACKAGING: ProcessFamily.PACKAGING,
    ProcessType.LABELING: ProcessFamily.PACKAGING,
    ProcessType.FREEZING: ProcessFamily.CONDITIONING,
    ProcessType.THAWING: ProcessFamily.CONDITIONING,
    ProcessType.CHILLING: ProcessFamily.CONDITIONING,
}


def process_family(process_type: ProcessType) -> ProcessFamily | None:
    return PROCESS_FAMILIES.get(ProcessType(process_type))


class MasterDataKind(str, Enum):
    RECIPE = "RECIPE"
    CUTTING_SCHEME = "CUTTING_SCHEME"
    YIELD_PROFILE = "YIELD_PROFILE"
    PACKAGING_SPEC = "PACKAGING_SPEC"


class InputRole(str, Enum):
    #: La entrada ES el producto objetivo (despiece, empaque, acondicionado).
    SOURCE = "SOURCE"
    #: Componente de una receta/BOM (formulación).
    COMPONENT = "COMPONENT"


def _positive_int(value, name: str) -> int:
    if isinstance(value, bool):
        raise MeatProcessingInvariantError(f"{name} debe ser entero")
    return int(value or 0)


@dataclass(frozen=True)
class SnapshotInput:
    """Material que la orden consume, con cuánto por unidad de base.

    `quantity_per_basis`: para SOURCE es 1 (cada kg planeado de la entrada);
    para COMPONENT, la cantidad del componente en la receta, relativa a
    `ProcessingRecipeSnapshot.batch_output_basis`.
    """

    product_id: str
    role: InputRole
    quantity_per_basis: Decimal
    unit_id: str | None = None
    scrap_pct: Decimal = Decimal("0")
    sequence: int = 0
    lot_controlled: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "product_id", required_uuid(self.product_id, "input.product_id"))
        object.__setattr__(self, "role", InputRole(self.role))
        object.__setattr__(self, "quantity_per_basis",
                           decimal_value(self.quantity_per_basis, "input.quantity_per_basis"))
        object.__setattr__(self, "scrap_pct", decimal_value(self.scrap_pct, "input.scrap_pct"))
        object.__setattr__(self, "sequence", _positive_int(self.sequence, "input.sequence"))
        if self.quantity_per_basis <= 0:
            raise MeatProcessingInvariantError("La cantidad de la entrada debe ser positiva")
        if self.scrap_pct < 0 or self.scrap_pct >= 100:
            raise MeatProcessingInvariantError("El desperdicio de la entrada debe estar en [0, 100)")


@dataclass(frozen=True)
class SnapshotOutput:
    """Salida esperada: producto, tipo y cuánto se espera por kg de entrada.

    `expected_factor` es la unidad común de todas las familias: salida esperada
    por unidad de entrada total consumida. El rendimiento real se calcula con
    las salidas reales; nunca se asume que entrada = salida + merma.
    """

    product_id: str
    output_type: OutputType
    expected_factor: Decimal
    measure_kind: str = "BY_WEIGHT"
    expected_yield_pct: Decimal | None = None
    minimum_yield_pct: Decimal | None = None
    maximum_yield_pct: Decimal | None = None
    unit_id: str | None = None
    sequence: int = 0
    lot_controlled: bool = False
    quality_gate: bool = False
    source: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "product_id", required_uuid(self.product_id, "output.product_id"))
        object.__setattr__(self, "output_type", OutputType(self.output_type))
        object.__setattr__(self, "expected_factor",
                           decimal_value(self.expected_factor, "output.expected_factor"))
        for name in ("expected_yield_pct", "minimum_yield_pct", "maximum_yield_pct"):
            object.__setattr__(self, name, optional_decimal_value(getattr(self, name), name))
        object.__setattr__(self, "sequence", _positive_int(self.sequence, "output.sequence"))
        if self.expected_factor < 0:
            raise MeatProcessingInvariantError("El factor esperado no puede ser negativo")
        if self.measure_kind not in ("BY_WEIGHT", "BY_PIECE"):
            raise MeatProcessingInvariantError(f"Medida de salida desconocida: {self.measure_kind}")

    @property
    def goes_to_stock(self) -> bool:
        """Desperdicio y pérdida no entran a existencia."""
        return self.output_type not in (OutputType.WASTE, OutputType.LOSS)


@dataclass(frozen=True)
class ProcessingRecipeSnapshot:
    """La foto congelada. Sin `id` es una resolución de Productos todavía no
    congelada; `frozen_for()` la sella para una orden concreta."""

    process_type: ProcessType
    target_product_id: str
    inputs: tuple[SnapshotInput, ...] = ()
    outputs: tuple[SnapshotOutput, ...] = ()
    recipe_version_id: str | None = None
    cutting_scheme_version_id: str | None = None
    yield_profile_version_id: str | None = None
    packaging_spec: dict = field(default_factory=dict)
    #: Base de la receta: cantidad de salida a la que se refieren los componentes.
    batch_output_basis: Decimal = Decimal("1")
    tolerance_pct: Decimal | None = None
    technical_parameters: dict = field(default_factory=dict)
    quality_constraints: dict = field(default_factory=dict)
    substitutions: tuple[str, ...] = ()
    effective_version: str = ""
    # ── sello (sólo al congelar) ────────────────────────────────────────
    id: str | None = None
    processing_order_id: str | None = None
    operation_id: str | None = None
    captured_by_user_id: str | None = None
    captured_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "process_type", ProcessType(self.process_type))
        object.__setattr__(self, "target_product_id",
                           required_uuid(self.target_product_id, "target_product_id"))
        for name in ("recipe_version_id", "cutting_scheme_version_id",
                     "yield_profile_version_id", "id", "processing_order_id",
                     "operation_id", "captured_by_user_id"):
            object.__setattr__(self, name, optional_uuid(getattr(self, name), name))
        object.__setattr__(self, "inputs", tuple(self.inputs))
        object.__setattr__(self, "outputs", tuple(self.outputs))
        object.__setattr__(self, "substitutions",
                           tuple(required_uuid(s, "substitution") for s in self.substitutions))
        object.__setattr__(self, "batch_output_basis",
                           decimal_value(self.batch_output_basis, "batch_output_basis"))
        object.__setattr__(self, "tolerance_pct",
                           optional_decimal_value(self.tolerance_pct, "tolerance_pct"))
        if self.batch_output_basis <= 0:
            raise MeatProcessingInvariantError("La base de la receta debe ser positiva")
        if self.tolerance_pct is not None and self.tolerance_pct < 0:
            raise MeatProcessingInvariantError("La tolerancia no puede ser negativa")
        productos = [o.product_id for o in self.outputs]
        if len(productos) != len(set(productos)):
            raise MeatProcessingInvariantError("Una salida aparece dos veces en la definición")
        if self.id is not None and self.id == self.operation_id:
            raise MeatProcessingInvariantError("entity_id y operation_id deben ser distintos")

    # ── lectura ─────────────────────────────────────────────────────────
    @property
    def family(self) -> ProcessFamily | None:
        return process_family(self.process_type)

    @property
    def is_frozen(self) -> bool:
        return self.id is not None and self.processing_order_id is not None

    @property
    def present_master_data(self) -> frozenset[MasterDataKind]:
        presentes = set()
        if self.recipe_version_id:
            presentes.add(MasterDataKind.RECIPE)
        if self.cutting_scheme_version_id:
            presentes.add(MasterDataKind.CUTTING_SCHEME)
        if self.yield_profile_version_id:
            presentes.add(MasterDataKind.YIELD_PROFILE)
        if self.packaging_spec:
            presentes.add(MasterDataKind.PACKAGING_SPEC)
        return frozenset(presentes)

    def output_for(self, product_id: str) -> SnapshotOutput | None:
        return next((o for o in self.outputs if o.product_id == product_id), None)

    def input_for(self, product_id: str) -> SnapshotInput | None:
        return next((i for i in self.inputs if i.product_id == product_id), None)

    def required_input_weight(self, planned_weight: Decimal) -> dict[str, Decimal]:
        """Cuánto de cada entrada pide un peso planeado, sin inventar unidades:
        SOURCE es el peso planeado de la propia entrada; COMPONENT escala la
        receta a la base y suma su desperdicio."""
        planeado = decimal_value(planned_weight, "planned_weight")
        requerido: dict[str, Decimal] = {}
        for entrada in self.inputs:
            if entrada.role is InputRole.SOURCE:
                cantidad = planeado * entrada.quantity_per_basis
            else:
                cantidad = (planeado * entrada.quantity_per_basis / self.batch_output_basis
                            * (Decimal("100") / (Decimal("100") - entrada.scrap_pct)))
            requerido[entrada.product_id] = cantidad
        return requerido

    # ── sello ───────────────────────────────────────────────────────────
    def frozen_for(self, *, processing_order_id: str, captured_by_user_id: str,
                   operation_id: str, captured_at: datetime | None = None
                   ) -> "ProcessingRecipeSnapshot":
        if self.is_frozen:
            raise MeatProcessingInvariantError("La definición ya está congelada para una orden")
        return replace(
            self, id=new_uuid(), processing_order_id=processing_order_id,
            operation_id=operation_id, captured_by_user_id=captured_by_user_id,
            captured_at=captured_at or datetime.now(timezone.utc))
