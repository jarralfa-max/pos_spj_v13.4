"""WeightCaptureService — orchestrate a validated weight capture (§18).

Reads through a ScaleGateway (never the driver) and validates with
CatchWeightPolicy: an auto capture must be stable and in range; a manual capture
outside range requires the WEIGHT_MANUAL_OVERRIDE permission (checked here via the
injected authorization policy) plus an explicit authorizer.

Returns a ``WeightReading`` — the caller (receipt/count use case) applies it to a
movement. No DB access.
"""

from __future__ import annotations

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.permissions import InventoryPermissions
from backend.domain.inventory.policies.catch_weight_policy import CatchWeightPolicy
from backend.domain.inventory.value_objects.catch_weight import WeightReading


class WeightCaptureService:
    def __init__(self, authorization: InventoryAuthorizationPolicy | None = None) -> None:
        self._auth = authorization or InventoryAuthorizationPolicy()
        self._policy = CatchWeightPolicy()

    def capture_from_scale(self, gateway, *, actor_user_id: str,
                           min_weight=None, max_weight=None,
                           require_stable: bool = True) -> WeightReading:
        self._auth.require(actor_user_id, InventoryPermissions.WEIGHT_CAPTURE)
        reading = gateway.read()
        if require_stable:
            self._policy.enforce_stable_for_auto(reading)
        self._policy.enforce_in_range(reading.net, min_weight=min_weight,
                                      max_weight=max_weight)
        return reading

    def capture_manual(self, *, gross, tare=0, unit: str = "KG",
                       actor_user_id: str, authorizer_user_id: str | None = None,
                       min_weight=None, max_weight=None,
                       device_id: str | None = None) -> WeightReading:
        from backend.infrastructure.hardware.scale_gateway import ManualScaleGateway

        reading = ManualScaleGateway(gross=gross, tare=tare, unit=unit,
                                     device_id=device_id).read()
        in_range = self._policy.is_in_range(
            reading.net, min_weight=min_weight, max_weight=max_weight)
        if in_range:
            self._auth.require(actor_user_id, InventoryPermissions.WEIGHT_CAPTURE)
            return reading
        # out of range → needs the override permission held by a distinct authorizer
        authorizer = authorizer_user_id or ""
        self._auth.authorize_exception(
            authorizer_user_id=authorizer, requested_by=actor_user_id,
            permission_code=InventoryPermissions.WEIGHT_MANUAL_OVERRIDE,
            operation_id=reading.captured_at,
            reason="captura manual de peso fuera de tolerancia",
            weight=reading.net, device_id=device_id)
        return reading
