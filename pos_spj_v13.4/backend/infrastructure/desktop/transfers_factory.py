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
    presenter = TransfersPresenter(
        query, connection=connection,
        create_transfer_request_uc=factory.create_transfer_request(),
        session_context=session_context)
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
