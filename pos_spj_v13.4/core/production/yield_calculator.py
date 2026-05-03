
# core/production/yield_calculator.py
# ── YieldCalculator — Cálculos de Rendimiento Cárnico ────────────────────────
#
# Responsabilidad única: cálculos matemáticos de rendimiento, merma y costeo.
# Sin I/O de DB — solo números.

from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

TOLERANCE_PCT = Decimal("0.5")      # 0.5% tolerancia por merma en báscula
MERMA_ALERT_THRESHOLD = Decimal("2.0")  # si merma real > esperada + 2%, generar alerta


@dataclass
class OutputSpec:
    """Especificación de un subproducto antes del cierre."""
    product_id: int
    nombre: str
    expected_pct: float   # % del peso fuente esperado
    real_weight: float    # kg reales capturados
    is_waste: bool = False


@dataclass
class YieldResult:
    """Resultado del análisis de rendimiento de un lote."""
    source_weight: float
    total_output_weight: float
    waste_weight: float
    usable_weight: float
    waste_pct: float
    usable_pct: float
    expected_usable_pct: float
    variance_pct: float
    efficiency_pct: float
    within_tolerance: bool
    alerta_merma: bool
    outputs: List["OutputYield"] = field(default_factory=list)


@dataclass
class OutputYield:
    product_id: int
    nombre: str
    expected_pct: float
    real_weight: float
    expected_weight: float
    real_pct: float
    variance_pct: float
    cost_allocated: float
    is_waste: bool


@dataclass
class CostAllocation:
    product_id: int
    nombre: str
    weight: float
    pct_utilizable: float
    cost_total: float
    cost_per_kg: float


class YieldCalculator:
    """
    Calculadora de rendimiento y distribución de costos para producción cárnica.

    Fórmulas:
        usable_weight   = SUM(output.weight for output if not is_waste)
        waste_weight    = SUM(output.weight for output if is_waste)
        real_yield_pct  = usable_weight / source_weight * 100
        tolerance_ok    = (usable + waste) <= source * (1 + TOLERANCE_PCT/100)
        cost_product    = (weight / usable_weight) * cost_total
    """

    @staticmethod
    def calculate(
        source_weight: float,
        outputs: List[OutputSpec],
        source_cost_total: float,
        expected_usable_pct: float = 0.0,
        expected_waste_pct: float = 0.0,
    ) -> YieldResult:
        """
        Calcula rendimiento completo de un lote.

        source_weight:       kg totales de materia prima ingresados
        outputs:             subproductos capturados (con is_waste flag)
        source_cost_total:   costo total de la materia prima ($)
        expected_usable_pct: % de rendimiento esperado (de receta)
        expected_waste_pct:  % de merma esperada (de receta)
        """
        sw = Decimal(str(source_weight))
        total_cost = Decimal(str(source_cost_total))

        # Calcular pesos
        usable_weight  = Decimal("0")
        waste_weight   = Decimal("0")
        for o in outputs:
            w = Decimal(str(o.real_weight))
            if o.is_waste:
                waste_weight += w
            else:
                usable_weight += w

        total_output = usable_weight + waste_weight

        # Tolerancia matemática: outputs no puede > fuente + 0.5%
        max_allowed = sw * (1 + TOLERANCE_PCT / 100)
        within_tolerance = total_output <= max_allowed

        # Porcentajes reales
        waste_pct   = float(waste_weight   / sw * 100) if sw else 0.0
        usable_pct  = float(usable_weight  / sw * 100) if sw else 0.0
        variance    = usable_pct - expected_usable_pct
        efficiency  = float(usable_pct / expected_usable_pct * 100) if expected_usable_pct else 0.0

        # Alerta de merma
        expected_w_pct = Decimal(str(expected_waste_pct))
        alerta_merma = (
            Decimal(str(waste_pct)) > expected_w_pct + MERMA_ALERT_THRESHOLD
        )

        # Distribución de costos (solo sobre peso utilizable)
        output_yields = []
        for o in outputs:
            ow = Decimal(str(o.real_weight))
            exp_w = Decimal(str(expected_usable_pct)) / 100 * sw * Decimal(str(o.expected_pct)) / 100 \
                    if expected_usable_pct and o.expected_pct else Decimal("0")

            # Costo asignado proporcionalmente sobre peso utilizable
            if usable_weight > 0 and not o.is_waste:
                cost_alloc = float(ow / usable_weight * total_cost)
            elif o.is_waste:
                cost_alloc = 0.0
            else:
                cost_alloc = 0.0

            real_pct = float(ow / sw * 100) if sw else 0.0
            var_pct  = real_pct - o.expected_pct

            output_yields.append(OutputYield(
                product_id=o.product_id,
                nombre=o.nombre,
                expected_pct=o.expected_pct,
                real_weight=float(ow),
                expected_weight=float(exp_w),
                real_pct=real_pct,
                variance_pct=var_pct,
                cost_allocated=cost_alloc,
                is_waste=o.is_waste,
            ))

        return YieldResult(
            source_weight=float(sw),
            total_output_weight=float(total_output),
            waste_weight=float(waste_weight),
            usable_weight=float(usable_weight),
            waste_pct=round(waste_pct, 4),
            usable_pct=round(usable_pct, 4),
            expected_usable_pct=expected_usable_pct,
            variance_pct=round(variance, 4),
            efficiency_pct=round(efficiency, 4),
            within_tolerance=within_tolerance,
            alerta_merma=alerta_merma,
            outputs=output_yields,
        )

    @staticmethod
    def allocate_costs(
        outputs: List[OutputYield],
        source_cost_total: float,
    ) -> List[CostAllocation]:
        """
        Distribuye costo total entre subproductos NO-merma
        proporcionalmente al peso real de cada uno.

        costo_producto = (peso_producto / peso_total_utilizable) * costo_total
        """
        total_cost = Decimal(str(source_cost_total))
        usable = [o for o in outputs if not o.is_waste]
        usable_weight = Decimal(str(sum(o.real_weight for o in usable)))

        allocations = []
        for o in usable:
            ow = Decimal(str(o.real_weight))
            pct = float(ow / usable_weight * 100) if usable_weight else 0.0
            cost_total_val = float(ow / usable_weight * total_cost) if usable_weight else 0.0
            cost_per_kg = cost_total_val / float(ow) if float(ow) > 0 else 0.0
            allocations.append(CostAllocation(
                product_id=o.product_id,
                nombre=o.nombre,
                weight=float(ow),
                pct_utilizable=round(pct, 4),
                cost_total=round(cost_total_val, 4),
                cost_per_kg=round(cost_per_kg, 4),
            ))
        return allocations

    @staticmethod
    def validate_weight_balance(
        source_weight: float,
        outputs: List[OutputSpec],
    ) -> tuple[bool, str]:
        """
        Valida que sum(outputs) <= source_weight + tolerancia 0.5%.
        Retorna (valid: bool, mensaje: str).
        """
        sw = Decimal(str(source_weight))
        total_out = Decimal(str(sum(o.real_weight for o in outputs)))
        max_allowed = sw * (1 + TOLERANCE_PCT / 100)

        if total_out > max_allowed:
            exceso = float(total_out - sw)
            return False, (
                f"BALANCE_EXCEDIDO: outputs={float(total_out):.4f} kg > "
                f"fuente={float(sw):.4f} kg (exceso={exceso:+.4f} kg, "
                f"tolerancia={float(TOLERANCE_PCT)}%)"
            )

        if sw > 0 and total_out < sw * Decimal("0.01"):
            return False, f"OUTPUTS_VACIOS: ningún subproducto capturado con peso > 0"

        return True, "OK"
