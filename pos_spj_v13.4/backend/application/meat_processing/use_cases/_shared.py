"""Shared helpers for Meat Processing use cases — error mapping, scope
enforcement and output summarization, factored out of the use case modules
that first needed them (PROC-6, PROC-11) so later ones don't duplicate them."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from backend.application.meat_processing.execution_context import (
    MeatProcessingExecutionContext,
)
from backend.application.meat_processing.result import MeatProcessingResult
from backend.domain.meat_processing.entities.process_output import ProcessOutput
from backend.domain.meat_processing.enums import OutputQualityStatus, OutputType
from backend.domain.meat_processing.exceptions import (
    MeatProcessingConfigurationError,
    MeatProcessingPermissionDeniedError,
    MeatProcessingScopeError,
    MeatProcessingSegregationOfDutiesError,
)

#: §22/§28: quality states that mean "not available for stock or further use".
#: Shared by PostProcessOutputUseCase (PROC-10), ChainOutputAsConsumptionUseCase
#: (PROC-12) and RecordQualityDecisionUseCase (PROC-16) so the definition of
#: "blocked" never drifts between them.
BLOCKED_QUALITY_STATUSES = (
    OutputQualityStatus.QUARANTINED, OutputQualityStatus.REJECTED,
    OutputQualityStatus.CONDEMNED, OutputQualityStatus.REWORK_REQUIRED,
)


def fail(exc: Exception, operation_id: str | None) -> MeatProcessingResult:
    if isinstance(exc, MeatProcessingSegregationOfDutiesError):
        code = "SEGREGATION_OF_DUTIES"
    elif isinstance(exc, MeatProcessingScopeError):
        code = "SCOPE_DENIED"
    elif isinstance(exc, MeatProcessingPermissionDeniedError):
        code = "PERMISSION_DENIED"
    elif isinstance(exc, MeatProcessingConfigurationError):
        code = "CONFIGURATION_ERROR"
    else:
        code = "MEAT_PROCESSING_RULE_VIOLATION"
    return MeatProcessingResult.fail(str(exc), code, operation_id=operation_id)


def scope_fail(context: MeatProcessingExecutionContext | None, branch_id: str,
                warehouse_id: str, operation_id: str) -> MeatProcessingResult | None:
    """§49: validates the branch/warehouse against the actor's scope. Returns a
    failed MeatProcessingResult (SCOPE_DENIED) or None when the scope is valid
    / there is no context to enforce."""
    if context is None:
        return None
    try:
        context.enforce_branch(branch_id)
        context.enforce_warehouse(warehouse_id)
    except MeatProcessingScopeError as exc:
        return fail(exc, operation_id)
    return None


def summarize_outputs_by_type(outputs: Iterable[ProcessOutput]) -> dict[str, Decimal]:
    """§26: the four dimensions a YieldReconciliation tracks, derived from
    already-captured ProcessOutput rows — shared by RecordProcessOutputsUseCase
    (PROC-11, sums outputs it just captured) and ReconcileYieldUseCase
    (PROC-14, sums outputs captured earlier/incrementally)."""
    actual_quantity = Decimal("0")
    actual_weight = Decimal("0")
    co_product_weight = Decimal("0")
    by_product_weight = Decimal("0")
    waste_weight = Decimal("0")
    for output in outputs:
        if output.output_type is OutputType.MAIN_PRODUCT:
            actual_quantity += output.quantity
            actual_weight += output.weight
        elif output.output_type is OutputType.CO_PRODUCT:
            co_product_weight += output.weight
        elif output.output_type is OutputType.BY_PRODUCT:
            by_product_weight += output.weight
        elif output.output_type in (OutputType.WASTE, OutputType.LOSS):
            waste_weight += output.weight
    return {
        "actual_quantity": actual_quantity, "actual_weight": actual_weight,
        "co_product_weight": co_product_weight, "by_product_weight": by_product_weight,
        "waste_weight": waste_weight,
    }
