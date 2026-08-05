"""LOSS-7 production context, yield analysis and loss classification."""
from dataclasses import dataclass
from decimal import Decimal

from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.permissions import LossPermissions
from backend.domain.losses.entities import LossCase, LossLine
from backend.domain.losses.enums import LossClassificationCode, LossOrigin, LossStatus
from backend.domain.losses.events import LossEvents, build_loss_event
from backend.domain.losses.exceptions import LossInvariantError
from backend.domain.products.recipe_enums import OutputType
from backend.domain.products.entities.cutting_output import MeasureKind
from backend.shared.ids import new_uuid, validate_uuidv7


def _decimal(value, name):
    if isinstance(value, (bool, float)):
        raise TypeError(f"{name} debe usar Decimal, nunca float")
    result = value if isinstance(value, Decimal) else Decimal(str(value))
    if result < 0:
        raise LossInvariantError(f"{name} no puede ser negativo")
    return result


@dataclass(frozen=True)
class ProductionOutputInput:
    product_id: str
    weight: Decimal
    lot_id: str | None = None
    output_type: OutputType = OutputType.MAIN_PRODUCT
    quantity: Decimal = Decimal("0")
    species_id: str | None = None
    cut_classification_id: str | None = None
    measure_kind: MeasureKind = MeasureKind.BY_WEIGHT

    def __post_init__(self):
        validate_uuidv7(self.product_id)
        if self.lot_id: validate_uuidv7(self.lot_id)
        if self.species_id: validate_uuidv7(self.species_id)
        if self.cut_classification_id: validate_uuidv7(self.cut_classification_id)
        if not isinstance(self.output_type, OutputType):
            object.__setattr__(self, "output_type", OutputType(str(self.output_type)))
        object.__setattr__(self, "weight", _decimal(self.weight, "output.weight"))
        object.__setattr__(self, "quantity", _decimal(self.quantity, "output.quantity"))
        if not isinstance(self.measure_kind, MeasureKind):
            object.__setattr__(self, "measure_kind", MeasureKind(str(self.measure_kind)))
        if self.weight == 0 and self.quantity == 0:
            raise LossInvariantError("La salida requiere piezas o peso")


@dataclass(frozen=True)
class AnalyzeProductionLossCommand:
    operation_id: str
    production_id: str
    recipe_version_id: str
    yield_profile_version_id: str
    input_product_id: str
    input_weight: Decimal
    outputs: tuple[ProductionOutputInput, ...]
    context: LossExecutionContext
    warehouse_id: str
    cutting_scheme_version_id: str | None = None

    def __post_init__(self):
        for value in (self.operation_id, self.production_id, self.recipe_version_id,
                      self.yield_profile_version_id, self.input_product_id,
                      self.warehouse_id):
            validate_uuidv7(value)
        if self.cutting_scheme_version_id:
            validate_uuidv7(self.cutting_scheme_version_id)
        object.__setattr__(self, "input_weight", _decimal(self.input_weight, "input_weight"))
        if self.input_weight <= 0:
            raise LossInvariantError("El peso de entrada debe ser mayor que cero")
        if not self.outputs:
            raise LossInvariantError("La producción requiere salidas reales")


@dataclass(frozen=True)
class ProductionYieldAnalysis:
    expected_output_weight: Decimal
    actual_output_weight: Decimal
    expected_yield_pct: Decimal
    actual_yield_pct: Decimal
    variance_weight: Decimal
    variance_pct: Decimal
    normal_loss_weight: Decimal
    abnormal_loss_weight: Decimal
    is_abnormal: bool
    lower_tolerance_pct: Decimal
    upper_tolerance_pct: Decimal
    severity: str


@dataclass(frozen=True)
class YieldAlert:
    id: str
    severity: str
    message: str


@dataclass(frozen=True)
class ProductionLossResult:
    normal_case_id: str | None
    abnormal_case_id: str | None
    normal_loss_weight: Decimal
    abnormal_loss_weight: Decimal
    actual_yield_pct: Decimal
    alert_id: str | None = None
    replayed: bool = False


class ProductionYieldCalculator:
    def calculate(self, *, input_weight, actual_output_weight,
                  expected_yield_pct, tolerance_pct,
                  minimum_yield_pct=None, maximum_yield_pct=None) -> ProductionYieldAnalysis:
        source = _decimal(input_weight, "input_weight")
        actual = _decimal(actual_output_weight, "actual_output_weight")
        expected_pct = _decimal(expected_yield_pct, "expected_yield_pct")
        tolerance = _decimal(tolerance_pct, "tolerance_pct")
        if source <= 0 or expected_pct > 100 or tolerance > 100:
            raise LossInvariantError("Perfil de rendimiento inválido")
        expected_output = source * expected_pct / Decimal("100")
        actual_pct = actual * Decimal("100") / source
        lower = (_decimal(minimum_yield_pct, "minimum_yield_pct")
                 if minimum_yield_pct is not None else max(Decimal("0"), expected_pct - tolerance))
        upper = (_decimal(maximum_yield_pct, "maximum_yield_pct")
                 if maximum_yield_pct is not None else min(Decimal("100"), expected_pct + tolerance))
        if lower > expected_pct or upper < expected_pct or lower > upper:
            raise LossInvariantError("Banda de tolerancia inválida")
        expected_loss = max(Decimal("0"), source - expected_output)
        actual_loss = max(Decimal("0"), source - actual)
        abnormal = actual_pct < lower
        severity = ("CRITICAL" if actual_pct == 0 and expected_pct > 0 else
                    "OUT_OF_TOLERANCE" if abnormal else
                    "WARNING" if actual_pct > upper else "NORMAL")
        normal_loss = min(actual_loss, expected_loss) if abnormal else actual_loss
        abnormal_loss = max(Decimal("0"), actual_loss - normal_loss)
        return ProductionYieldAnalysis(
            expected_output, actual, expected_pct, actual_pct.quantize(Decimal("0.01")),
            actual - expected_output, (actual_pct - expected_pct).quantize(Decimal("0.01")),
            normal_loss, abnormal_loss, abnormal, lower, upper, severity)


class ProductionLossAnalysisService:
    def __init__(self, repository, authorization,
                 calculator: ProductionYieldCalculator | None = None):
        self._repository = repository; self._authorization = authorization
        self._calculator = calculator or ProductionYieldCalculator()

    def execute(self, command: AnalyzeProductionLossCommand) -> ProductionLossResult:
        replay = self._repository.find_processed(command.operation_id)
        if replay:
            return ProductionLossResult(*replay, replayed=True)
        actor = command.context.actor_user_id
        self._authorization.require(actor, LossPermissions.REPORT)
        self._authorization.require(actor, LossPermissions.SUBMIT)
        command.context.enforce_branch(command.context.active_branch_id)
        command.context.enforce_warehouse(command.warehouse_id)
        config = self._repository.load_context(
            input_product_id=command.input_product_id,
            recipe_version_id=command.recipe_version_id,
            yield_profile_version_id=command.yield_profile_version_id,
            cutting_scheme_version_id=command.cutting_scheme_version_id)
        if not config:
            raise LossInvariantError("Receta o perfil de rendimiento activo no encontrado")
        configured_outputs = config.get("output_product_ids")
        if configured_outputs is not None:
            unexpected = {item.product_id for item in command.outputs} - set(configured_outputs)
            if unexpected:
                raise LossInvariantError("La salida real no pertenece al perfil de rendimiento")
        meat_config = config.get("meat_output_config")
        if meat_config is not None:
            self._validate_meat_outputs(command.outputs, meat_config)
        actual_output = sum((item.weight for item in command.outputs
                             if item.output_type not in {OutputType.WASTE, OutputType.LOSS}),
                            Decimal("0"))
        analysis = self._calculator.calculate(
            input_weight=command.input_weight, actual_output_weight=actual_output,
            expected_yield_pct=config["expected_yield_pct"],
            tolerance_pct=config["tolerance_pct"],
            minimum_yield_pct=config.get("minimum_yield_pct"),
            maximum_yield_pct=config.get("maximum_yield_pct"))
        normal = self._case(command, config, LossClassificationCode.PROCESS_LOSS,
                            config["normal_reason_id"], analysis.normal_loss_weight)
        abnormal = self._case(command, config, LossClassificationCode.YIELD_VARIANCE,
                              config["abnormal_reason_id"], analysis.abnormal_loss_weight)
        events = []
        for case, event_name in ((normal, LossEvents.LOSS_CASE_SUBMITTED),
                                 (abnormal, LossEvents.YIELD_VARIANCE_DETECTED)):
            if case:
                events.append(build_loss_event(
                    event_name, operation_id=command.operation_id, entity_id=case.id,
                    branch_id=case.branch_id, warehouse_id=case.warehouse_id,
                    user_id=actor, production_id=command.production_id,
                    recipe_version_id=command.recipe_version_id,
                    yield_profile_version_id=command.yield_profile_version_id,
                    loss_weight=case.lines[0].weight))
        alert = None
        if analysis.severity != "NORMAL":
            alert = YieldAlert(
                new_uuid(), analysis.severity,
                f"Rendimiento {analysis.actual_yield_pct}% fuera de banda "
                f"[{analysis.lower_tolerance_pct}%, {analysis.upper_tolerance_pct}%]")
            events.append(build_loss_event(
                LossEvents.YIELD_ALERT_RAISED, operation_id=command.operation_id,
                entity_id=alert.id, branch_id=command.context.active_branch_id,
                warehouse_id=command.warehouse_id, user_id=actor,
                production_id=command.production_id, severity=alert.severity,
                expected_yield_pct=analysis.expected_yield_pct,
                actual_yield_pct=analysis.actual_yield_pct,
                variance_pct=analysis.variance_pct))
        self._repository.save_analysis(
            operation_id=command.operation_id, production_id=command.production_id,
            recipe_version_id=command.recipe_version_id,
            yield_profile_version_id=command.yield_profile_version_id,
            cutting_scheme_version_id=command.cutting_scheme_version_id,
            primary_output_product_id=config["primary_output_product_id"],
            normal_case=normal, abnormal_case=abnormal, analysis=analysis,
            alert=alert, outputs=command.outputs, events=tuple(events))
        return ProductionLossResult(
            normal.id if normal else None, abnormal.id if abnormal else None,
            analysis.normal_loss_weight, analysis.abnormal_loss_weight,
            analysis.actual_yield_pct, alert.id if alert else None)

    @staticmethod
    def _validate_meat_outputs(outputs, configured):
        for output in outputs:
            expected = configured.get(output.product_id)
            if expected is None:
                raise LossInvariantError("Producto no configurado en el esquema de despiece")
            if not output.species_id or output.species_id != expected["species_id"]:
                raise LossInvariantError("La especie de la salida no coincide con el despiece")
            if output.cut_classification_id != expected["cut_classification_id"]:
                raise LossInvariantError("El corte de la salida no coincide con el despiece")
            if output.output_type.value != expected["output_type"]:
                raise LossInvariantError("El rol de coproducto/subproducto no coincide")
            if output.measure_kind.value != expected["measure_kind"]:
                raise LossInvariantError("La medida de piezas/peso no coincide con el despiece")

    @staticmethod
    def _case(command, config, classification, reason_id, weight):
        if weight <= 0: return None
        case = LossCase(
            id=new_uuid(), operation_id=new_uuid(),
            branch_id=command.context.active_branch_id, warehouse_id=command.warehouse_id,
            reported_by_user_id=command.context.actor_user_id, classification=classification,
            origin=LossOrigin.PRODUCTION, reason_id=reason_id,
            source_document_id=command.production_id,
            notes=f"Generada desde producción; receta {command.recipe_version_id}")
        case.add_line(LossLine(id=new_uuid(), product_id=command.input_product_id,
                               weight=weight, unit="kg"))
        case.submit(actor_user_id=command.context.actor_user_id)
        return case
