from backend.application.transfers.permissions import (
    ALL_TRANSFER_PERMISSIONS,
    TransferPermissions as P,
)


def test_transfer_permissions_are_granular_and_no_legacy_general_code_exists():
    # Auditoría de permisos 968e0bc (PER-04): `TRANSFERENCIAS.<accion>`; ninguna
    # acción es el módulo pelado ni un código plano `TRANSFERS_*`.
    assert "TRANSFERENCIAS" not in ALL_TRANSFER_PERMISSIONS
    assert not any(code.startswith("TRANSFERS_") for code in ALL_TRANSFER_PERMISSIONS)
    assert {P.REQUEST_CREATE, P.APPROVE, P.DISPATCH, P.RECEIVE,
            P.DIFFERENCE_RESOLVE} <= ALL_TRANSFER_PERMISSIONS
    assert P.APPROVE == "TRANSFERENCIAS.aprobar"
