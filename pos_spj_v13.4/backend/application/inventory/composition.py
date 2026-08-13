"""Inventory composition root — the central productive use-case factory (§5.2).

`InventoryUseCaseFactory` is the single place that builds sensitive inventory use
cases with their authorization wired. It **requires** a real ``PermissionChecker``
(fail closed: no checker → ``InventoryConfigurationError``), so production code
never instantiates a sensitive use case with an empty constructor (which would fall
back to the permissive test default). The UI and integration handlers obtain their
use cases from this factory instead of ``UseCase()``.

Build it in production with ``from_session(container.session, ...)``; isolated tests
may use ``for_tests()`` which wires the explicit AllowAll test checker.
"""

from __future__ import annotations

from backend.application.inventory.authorization import (
    AllowAllInventoryPermissionCheckerForTests,
    InventoryAuthorizationPolicy,
    PermissionChecker,
)
from backend.application.inventory.session_authorization import (
    InventorySessionPermissionChecker,
)
from backend.application.inventory.use_cases import (
    AllocateReservationUseCase,
    ApproveAdjustmentUseCase,
    ApproveCountUseCase,
    ConfirmCountUseCase,
    CreateAdjustmentFromCountUseCase,
    CreateAdjustmentUseCase,
    CreateCountUseCase,
    CreateLocationUseCase,
    CreateReservationUseCase,
    CreateWarehouseUseCase,
    CreateZoneUseCase,
    DeactivateLocationUseCase,
    DeactivateWarehouseUseCase,
    DisposeQuarantineUseCase,
    ExpireInventoryUseCase,
    GenerateExpiryAlertsUseCase,
    GenerateReplenishmentSuggestionsUseCase,
    InspectReceiptUseCase,
    PostAdjustmentUseCase,
    PostInventoryMovementUseCase,
    ProvisionDefaultWarehouseUseCase,
    QuarantineStockUseCase,
    RecordCatchWeightUseCase,
    RecordCountUseCase,
    RecordTemperatureReadingUseCase,
    RegisterInventoryLotUseCase,
    ReleaseQuarantineUseCase,
    ReleaseReservationUseCase,
    ResolveTemperatureExcursionUseCase,
    ReverseAdjustmentUseCase,
    ReverseInventoryMovementUseCase,
    SetLocationStatusUseCase,
    SetLotQualityStatusUseCase,
    SetWarehouseStatusUseCase,
    UpdateLocationUseCase,
    UpdateLotUseCase,
    UpdateWarehouseUseCase,
)
from backend.domain.inventory.exceptions import InventoryConfigurationError


class InventoryUseCaseFactory:
    """Builds inventory use cases wired with a real authorization policy (§5.2)."""

    def __init__(
        self,
        *,
        permission_checker: PermissionChecker,
        session_context=None,
        connection_provider=None,
        event_dispatcher=None,
        clock=None,
        uuid_generator=None,
    ) -> None:
        if permission_checker is None:
            # Fail closed (§5.1/§5.2): the composition root must never build a
            # sensitive use case on an unconfigured authorization gate.
            raise InventoryConfigurationError(
                "InventoryUseCaseFactory requiere un PermissionChecker real")
        self._checker = permission_checker
        self._session = session_context
        self._connection_provider = connection_provider
        self._event_dispatcher = event_dispatcher
        self._clock = clock
        self._uuid_generator = uuid_generator
        self._policy = InventoryAuthorizationPolicy(permission_checker)

    # ── construction helpers ─────────────────────────────────────────────────
    @classmethod
    def from_session(cls, session, **kwargs) -> "InventoryUseCaseFactory":
        """Productive factory over the live session (real RBAC via tiene_permiso)."""
        return cls(
            permission_checker=InventorySessionPermissionChecker(session),
            session_context=session,
            **kwargs,
        )

    @classmethod
    def for_tests(cls, **kwargs) -> "InventoryUseCaseFactory":
        """Isolated-test factory with the explicit AllowAll checker (never in prod)."""
        return cls(
            permission_checker=AllowAllInventoryPermissionCheckerForTests(),
            **kwargs,
        )

    @property
    def authorization_policy(self) -> InventoryAuthorizationPolicy:
        return self._policy

    @property
    def session_context(self):
        return self._session

    def execution_context(self, *, require_branch: bool = True):
        """Resolve the trusted actor/scope context from the live session (§5.3).

        Fails closed when there is no authenticated session/branch — the context is
        never fabricated from UI-supplied ids.
        """
        from backend.application.inventory.execution_context import (
            resolve_inventory_execution_context,
        )
        return resolve_inventory_execution_context(
            self._session, require_branch=require_branch)

    def build(self, use_case_cls, **kwargs):
        """Generic builder: constructs any inventory use case with the wired policy.

        Every sensitive inventory use case accepts ``authorization`` as its policy
        seam, so the factory injects the real, checker-backed policy here.
        """
        return use_case_cls(authorization=self._policy, **kwargs)

    # ── named builders (the sensitive command use cases) ─────────────────────
    def post_movement(self, **kw):
        return self.build(PostInventoryMovementUseCase, **kw)

    def reverse_movement(self, **kw):
        return self.build(ReverseInventoryMovementUseCase, **kw)

    def create_adjustment(self, **kw):
        return self.build(CreateAdjustmentUseCase, **kw)

    def approve_adjustment(self, **kw):
        return self.build(ApproveAdjustmentUseCase, **kw)

    def post_adjustment(self, **kw):
        return self.build(PostAdjustmentUseCase, **kw)

    def reverse_adjustment(self, **kw):
        return self.build(ReverseAdjustmentUseCase, **kw)

    def create_count(self, **kw):
        return self.build(CreateCountUseCase, **kw)

    def record_count(self, **kw):
        return self.build(RecordCountUseCase, **kw)

    def confirm_count(self, **kw):
        return self.build(ConfirmCountUseCase, **kw)

    def approve_count(self, **kw):
        return self.build(ApproveCountUseCase, **kw)

    def create_adjustment_from_count(self, **kw):
        return self.build(CreateAdjustmentFromCountUseCase, **kw)

    def create_reservation(self, **kw):
        return self.build(CreateReservationUseCase, **kw)

    def allocate_reservation(self, **kw):
        return self.build(AllocateReservationUseCase, **kw)

    def release_reservation(self, **kw):
        return self.build(ReleaseReservationUseCase, **kw)

    def quarantine_stock(self, **kw):
        return self.build(QuarantineStockUseCase, **kw)

    def release_quarantine(self, **kw):
        return self.build(ReleaseQuarantineUseCase, **kw)

    def dispose_quarantine(self, **kw):
        return self.build(DisposeQuarantineUseCase, **kw)

    def record_temperature_reading(self, **kw):
        return self.build(RecordTemperatureReadingUseCase, **kw)

    def resolve_temperature_excursion(self, **kw):
        return self.build(ResolveTemperatureExcursionUseCase, **kw)

    def create_warehouse(self, **kw):
        return self.build(CreateWarehouseUseCase, **kw)

    def update_warehouse(self, **kw):
        return self.build(UpdateWarehouseUseCase, **kw)

    def set_warehouse_status(self, **kw):
        return self.build(SetWarehouseStatusUseCase, **kw)

    def deactivate_warehouse(self, **kw):
        return self.build(DeactivateWarehouseUseCase, **kw)

    def create_zone(self, **kw):
        return self.build(CreateZoneUseCase, **kw)

    def create_location(self, **kw):
        return self.build(CreateLocationUseCase, **kw)

    def update_location(self, **kw):
        return self.build(UpdateLocationUseCase, **kw)

    def set_location_status(self, **kw):
        return self.build(SetLocationStatusUseCase, **kw)

    def deactivate_location(self, **kw):
        return self.build(DeactivateLocationUseCase, **kw)

    def provision_default_warehouse(self, **kw):
        return self.build(ProvisionDefaultWarehouseUseCase, **kw)

    def inspect_receipt(self, **kw):
        return self.build(InspectReceiptUseCase, **kw)
    def register_lot(self, **kw):
        return self.build(RegisterInventoryLotUseCase, **kw)

    def update_lot(self, **kw):
        return self.build(UpdateLotUseCase, **kw)

    def set_lot_quality_status(self, **kw):
        return self.build(SetLotQualityStatusUseCase, **kw)

    def generate_expiry_alerts(self, **kw):
        return self.build(GenerateExpiryAlertsUseCase, **kw)

    def expire_inventory(self, **kw):
        return self.build(ExpireInventoryUseCase, **kw)

    def record_catch_weight(self, **kw):
        return self.build(RecordCatchWeightUseCase, **kw)

    def generate_replenishment_suggestions(self, **kw):
        return self.build(GenerateReplenishmentSuggestionsUseCase, **kw)
