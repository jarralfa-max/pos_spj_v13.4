"""Transfers composition root (INV-12 vertical slice).

Mirrors ``backend/application/inventory/composition.py``'s
``InventoryUseCaseFactory``: the single place that builds Transfers command
use cases with their authorization wired. Fails closed — no permission
checker, no factory. Only ``create_transfer_request`` is wired so far; later
INV-12.x phases add the rest of the workflow (submit/approve/reject, reserve,
pick, dispatch, receive, differences, return) the same way.

Build it in production with ``from_session(container.session)``; isolated
tests use ``for_tests()``.
"""

from __future__ import annotations

from backend.application.transfers.authorization import (
    AllowAllTransferPermissionCheckerForTests,
    TransferAuthorizationPolicy,
    TransferPermissionChecker,
)
from backend.application.transfers.session_authorization import (
    TransferSessionPermissionChecker,
)
from backend.application.transfers.session_scope_checker import (
    TransferSessionScopeChecker,
)
from backend.application.transfers.use_cases.transfer_request_use_cases import (
    CreateTransferRequestUseCase,
)
from backend.domain.transfers.exceptions import TransferConfigurationError
from backend.infrastructure.db.repositories.transfers.transfer_number_sequence import (
    SqlTransferRequestNumberGenerator,
)
from backend.infrastructure.db.repositories.transfers.transfer_write_repository import (
    TransferWriteRepository,
)


class TransferUseCaseFactory:
    """Builds Transfers use cases wired with a real authorization policy."""

    def __init__(self, *, connection, permission_checker: TransferPermissionChecker,
                 session_context=None, scope_checker=None) -> None:
        if permission_checker is None:
            raise TransferConfigurationError(
                "TransferUseCaseFactory requiere un TransferPermissionChecker real")
        self._connection = connection
        self._session = session_context
        # `scopes` se pasa de verdad: construir la política con un solo
        # argumento dejaba `_scopes=None`, y entonces el `require()` de los
        # casos de uso NO evaluaba la sucursal — el alcance por sucursal de
        # Transferencias no se comprobaba en producción.
        self._policy = TransferAuthorizationPolicy(permission_checker, scope_checker)
        self._repository = TransferWriteRepository(connection)
        self._number_generator = SqlTransferRequestNumberGenerator(connection)

    @classmethod
    def from_session(cls, session, *, connection) -> "TransferUseCaseFactory":
        """Productive factory over the live session (real RBAC via tiene_permiso).

        A diferencia de `for_tests`, aquí SÍ se inyecta alcance por sucursal:
        es la ruta productiva y es donde tiene que doler. `for_tests` se queda
        deliberadamente sin él porque sus casos usan sucursales inventadas y
        una base mínima; darle alcance real convertiría cada prueba aislada en
        una prueba de permisos.
        """
        return cls(
            connection=connection,
            permission_checker=TransferSessionPermissionChecker(session),
            session_context=session,
            scope_checker=TransferSessionScopeChecker(connection),
        )

    @classmethod
    def for_tests(cls, *, connection) -> "TransferUseCaseFactory":
        """Isolated-test factory with the explicit AllowAll checker (never in prod)."""
        return cls(
            connection=connection,
            permission_checker=AllowAllTransferPermissionCheckerForTests(),
        )

    @property
    def authorization_policy(self) -> TransferAuthorizationPolicy:
        return self._policy

    def create_transfer_request(self) -> CreateTransferRequestUseCase:
        return CreateTransferRequestUseCase(
            repository=self._repository, authorization=self._policy,
            number_generator=self._number_generator)

    # ── ciclo completo (integración Logística 32cfbf) ─────────────────────────
    # Antes sólo se cableaba la creación: aprobar, preparar, despachar y recibir
    # existían como casos de uso sin infraestructura ni pantalla.
    def _gateway(self):
        from backend.infrastructure.integrations.transfers_inventory_gateway import (
            build_transfer_inventory_gateway,
        )
        return build_transfer_inventory_gateway(self._connection)

    def _shipments(self):
        from backend.infrastructure.db.repositories.transfers.transfer_shipment_repository import (
            TransferShipmentRepository,
        )
        return TransferShipmentRepository(self._connection)

    def submit_transfer_request(self):
        from backend.application.transfers.use_cases.transfer_request_use_cases import (
            SubmitTransferRequestUseCase,
        )
        return SubmitTransferRequestUseCase(self._repository, self._policy)

    def approve_transfer_request(self):
        from backend.application.transfers.use_cases.transfer_request_use_cases import (
            ApproveTransferRequestUseCase,
        )
        return ApproveTransferRequestUseCase(self._repository, self._policy)

    def reject_transfer_request(self):
        from backend.application.transfers.use_cases.transfer_request_use_cases import (
            RejectTransferRequestUseCase,
        )
        return RejectTransferRequestUseCase(self._repository, self._policy)

    def reserve_transfer_inventory(self):
        from backend.application.transfers.use_cases.transfer_reservation_use_cases import (
            ReserveTransferInventoryUseCase,
        )
        return ReserveTransferInventoryUseCase(self._repository, self._gateway(), self._policy)

    def start_transfer_picking(self):
        from backend.application.transfers.use_cases.transfer_picking_use_cases import (
            StartTransferPickingUseCase,
        )
        return StartTransferPickingUseCase(self._repository, self._policy)

    def confirm_transfer_picking(self):
        from backend.application.transfers.use_cases.transfer_picking_use_cases import (
            ConfirmTransferPickingUseCase,
        )
        return ConfirmTransferPickingUseCase(self._repository, self._policy)

    def mark_ready_to_dispatch(self):
        from backend.application.transfers.use_cases.transfer_picking_use_cases import (
            MarkTransferReadyToDispatchUseCase,
        )
        return MarkTransferReadyToDispatchUseCase(self._repository, self._policy)

    def dispatch_transfer(self):
        from backend.application.transfers.use_cases.transfer_dispatch_use_cases import (
            DispatchTransferShipmentUseCase,
        )
        return DispatchTransferShipmentUseCase(self._repository, self._shipments(),
                                               self._gateway(), self._policy)

    def receive_transfer(self):
        from backend.application.transfers.use_cases.transfer_receipt_use_cases import (
            ConfirmTransferReceiptUseCase,
        )
        from backend.infrastructure.db.repositories.transfers.transfer_shipment_repository import (
            TransferReceiptRepository,
        )
        return ConfirmTransferReceiptUseCase(
            self._repository, self._shipments(), TransferReceiptRepository(self._connection),
            self._gateway(), self._policy)

    def shipment_repository(self):
        return self._shipments()
