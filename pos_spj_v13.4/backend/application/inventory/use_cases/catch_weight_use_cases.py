"""RecordCatchWeightUseCase (INV-8, §28/§29) — capture a validated weight
reading and post it as a stock correction.

There is no dedicated "weight" movement type: a standalone quantity/weight
correction not tied to a receipt/sale/etc. is exactly what the adjustment
mechanism (§29) already models — ``AdjustmentReason.WEIGHT_VARIANCE`` exists
specifically for this. So "Capturar peso", "Corregir lectura" and
"Reconciliar piezas/peso" are one flow: validate a reading (scale or an
authorized manual entry, via ``WeightCaptureService`` — stability/range/hot
authorization all enforced there) → post it as one adjustment line
(``weight_delta`` = the reading's net weight, ``quantity_delta`` = the piece
count reconciled alongside it) through ``CreateAdjustmentUseCase`` — reusing
its existing audit trail, limit evaluation and segregation of duties instead
of building a second, parallel posting path.

A capture that gets applied therefore needs both the capture permission
(``WEIGHT_CAPTURE``/``WEIGHT_MANUAL_OVERRIDE``, enforced inside
``WeightCaptureService``) and ``ADJUSTMENT_CREATE`` (enforced inside
``CreateAdjustmentUseCase``) — capturing a number and committing a stock
correction are different authorizations, the same separation the rest of
this module already applies between capture/view and mutate/approve.
"""

from __future__ import annotations

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.result import InventoryResult
from backend.application.inventory.services.weight_capture_service import (
    WeightCaptureService,
)
from backend.application.inventory.use_cases.adjustment_use_cases import (
    CreateAdjustmentUseCase,
)
from backend.domain.inventory.enums import AdjustmentReason
from backend.domain.inventory.exceptions import (
    InventoryDomainError,
    InventoryPermissionDeniedError,
    SegregationOfDutiesError,
)


class RecordCatchWeightUseCase:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy.permissive_for_tests()
        self._capture = WeightCaptureService(self._auth)
        self._adjust = CreateAdjustmentUseCase(self._auth)

    def execute(self, connection, *, product_id: str, branch_id: str, warehouse_id: str,
                operation_id: str, actor_user_id: str, location_id: str | None = None,
                pieces_delta=0, gateway=None, gross=None, tare=0, unit: str = "KG",
                min_weight=None, max_weight=None, require_stable: bool = True,
                authorizer_user_id: str | None = None,
                reason_note: str = "") -> InventoryResult:
        try:
            if gateway is not None:
                reading = self._capture.capture_from_scale(
                    gateway, actor_user_id=actor_user_id, min_weight=min_weight,
                    max_weight=max_weight, require_stable=require_stable)
            else:
                if gross is None:
                    return InventoryResult.fail(
                        "Captura manual requiere el peso bruto", "WEIGHT_REQUIRED",
                        operation_id=operation_id)
                reading = self._capture.capture_manual(
                    gross=gross, tare=tare, unit=unit, actor_user_id=actor_user_id,
                    authorizer_user_id=authorizer_user_id, min_weight=min_weight,
                    max_weight=max_weight)
        except InventoryPermissionDeniedError as exc:
            return InventoryResult.fail(str(exc), "PERMISSION_DENIED",
                                        operation_id=operation_id)
        except SegregationOfDutiesError as exc:
            return InventoryResult.fail(str(exc), "SEGREGATION_OF_DUTIES",
                                        operation_id=operation_id)
        except InventoryDomainError as exc:
            return InventoryResult.fail(str(exc), "INVALID_WEIGHT_READING",
                                        operation_id=operation_id)

        folio = f"PESO-{operation_id[:8].upper()}"
        result = self._adjust.execute(
            connection, folio=folio, branch_id=branch_id, warehouse_id=warehouse_id,
            reason=AdjustmentReason.WEIGHT_VARIANCE, reason_note=reason_note,
            lines=[{"product_id": product_id, "quantity_delta": pieces_delta,
                   "weight_delta": reading.net, "location_id": location_id}],
            operation_id=operation_id, actor_user_id=actor_user_id)
        result.data["weight_reading"] = {
            "gross": str(reading.gross), "tare": str(reading.tare),
            "net": str(reading.net), "unit": reading.unit, "stable": reading.stable,
            "source": reading.source.value,
        }
        return result