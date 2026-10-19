"""Desktop composition root for the canonical Transfers workspace."""
from backend.application.transfers.composition import TransferUseCaseFactory
from frontend.desktop.modules.transfers.transfers_presenter import TransfersPresenter
from frontend.desktop.modules.transfers.transfers_view import TransfersView
from backend.infrastructure.db.repositories.transfers import TransferWorkspaceQueryRepository


def _build_transfers_presenter_and_permission(connection, session_context=None):
    """Explicit-dependency composition for the Transfers workspace — never
    receives a container, only what it needs, already unwrapped. Lives here
    (not under `frontend/desktop/modules/transfers/`) because that UI
    directory is guarded against importing repositories directly
    (`tests/architecture/test_transfers_ui_uses_design_system.py`); this is
    the composition root, not UI code, so it belongs beside the container-
    consuming `TransfersModuleHost` below, which now delegates to it."""
    has_permission = (
        session_context.tiene_permiso
        if session_context is not None and hasattr(session_context, "tiene_permiso")
        else lambda _code: False
    )
    query = TransferWorkspaceQueryRepository(connection)
    factory = (TransferUseCaseFactory.from_session(session_context, connection=connection)
               if session_context is not None
               else TransferUseCaseFactory.for_tests(connection=connection))
    from backend.application.transfers.queries.transfer_detail_query_service import (
        TransferDetailQueryService,
    )
    from backend.infrastructure.integrations.transfers_inventory_gateway import (
        reserved_pick_lines,
    )
    from backend.security.authentication.verify_authorizer_credentials_use_case import (
        build_authorizer_credentials_verifier,
    )
    # Ciclo completo (integración Logística 32cfbf): antes sólo se cableaba crear.
    cycle = {
        "submit": factory.submit_transfer_request(),
        "approve": factory.approve_transfer_request(),
        "reject": factory.reject_transfer_request(),
        "reserve": factory.reserve_transfer_inventory(),
        "start_picking": factory.start_transfer_picking(),
        "confirm_picking": factory.confirm_transfer_picking(),
        "ready_to_dispatch": factory.mark_ready_to_dispatch(),
        "dispatch": factory.dispatch_transfer(),
        "receive": factory.receive_transfer(),
    }
    from backend.application.transfers.cycle_service import TransferCycleService
    ciclo = TransferCycleService(
        connection, use_cases=cycle, detail_query=TransferDetailQueryService(connection).detail,
        pick_lines=lambda tid: reserved_pick_lines(connection, factory._repository.get(tid)))
    presenter = TransfersPresenter(
        query, connection=connection,
        create_transfer_request_uc=factory.create_transfer_request(),
        session_context=session_context, cycle_service=ciclo,
        credentials_verifier=build_authorizer_credentials_verifier(connection).execute)
    return presenter, has_permission


def create_transfers_view(connection, session_context=None, *, parent=None) -> TransfersView:
    """Explicit-dependency equivalent of `TransfersModuleHost` — never
    receives a container, only what it needs, already unwrapped."""
    presenter, has_permission = _build_transfers_presenter_and_permission(connection, session_context)
    return TransfersView(presenter, has_permission=has_permission, parent=parent)


class TransfersModuleHost(TransfersView):
    def __init__(self, container, parent=None) -> None:
        session = getattr(container, "session", None)
        presenter, has_permission = _build_transfers_presenter_and_permission(container.db, session)
        super().__init__(presenter, has_permission=has_permission, parent=parent)
