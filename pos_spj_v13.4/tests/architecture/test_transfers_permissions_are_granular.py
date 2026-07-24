from backend.application.transfers.permissions import ALL_TRANSFER_PERMISSIONS


def test_transfer_permissions_are_granular_and_no_legacy_general_code_exists():
    assert "TRANSFERENCIAS" not in ALL_TRANSFER_PERMISSIONS
    assert {"TRANSFERS_REQUEST_CREATE", "TRANSFERS_APPROVE", "TRANSFERS_DISPATCH", "TRANSFERS_RECEIVE", "TRANSFERS_DIFFERENCE_RESOLVE"} <= ALL_TRANSFER_PERMISSIONS
