from pathlib import Path


def test_transfer_request_use_cases_do_not_import_database_or_inventory_gateways():
    request_source = Path("pos_spj_v13.4/backend/application/transfers/use_cases/transfer_request_use_cases.py").read_text()
    reservation_source = Path("pos_spj_v13.4/backend/application/transfers/use_cases/transfer_reservation_use_cases.py").read_text()
    picking_source = Path("pos_spj_v13.4/backend/application/transfers/use_cases/transfer_picking_use_cases.py").read_text()
    packaging_source = Path("pos_spj_v13.4/backend/application/transfers/use_cases/transfer_packaging_use_cases.py").read_text()
    dispatch_source = Path("pos_spj_v13.4/backend/application/transfers/use_cases/transfer_dispatch_use_cases.py").read_text()
    receipt_source = Path("pos_spj_v13.4/backend/application/transfers/use_cases/transfer_receipt_use_cases.py").read_text()
    blind_receipt_source = Path("pos_spj_v13.4/backend/application/transfers/use_cases/blind_receipt_use_cases.py").read_text()
    difference_source = Path("pos_spj_v13.4/backend/application/transfers/use_cases/transfer_difference_use_cases.py").read_text()
    return_source = Path("pos_spj_v13.4/backend/application/transfers/use_cases/transfer_return_use_cases.py").read_text()
    suggestion_source = Path("pos_spj_v13.4/backend/application/transfers/use_cases/transfer_suggestion_use_cases.py").read_text()
    source = request_source + reservation_source + picking_source + packaging_source + dispatch_source + receipt_source + blind_receipt_source + difference_source + return_source + suggestion_source

    assert "sqlite3" not in source
    assert "InventoryEngine" not in source
    assert "TRANSFER_REQUEST_CREATED" not in source
    assert "TransferEvents.REQUEST_CREATED" in request_source
    assert "InventoryTransferGateway" in reservation_source
    assert "InventoryTransferGateway" not in picking_source
    assert "InventoryTransferGateway" not in packaging_source
    assert "InventoryTransferGateway" in dispatch_source
    assert "InventoryTransferGateway" in receipt_source
    assert ".receive(" in receipt_source
    assert "ProductTransferProfileQueryService" in receipt_source
    assert "TransferQualityGateway" in receipt_source
    assert "productos" not in receipt_source
    assert "ConfirmTransferReceiptUseCase" in blind_receipt_source
    assert "InventoryTransferGateway" not in blind_receipt_source
    assert "InventoryTransferGateway" not in difference_source
    assert "TransferEvents.DIFFERENCE_DETECTED" in difference_source
    assert "TransferEvents.DIFFERENCE_RESOLVED" in difference_source
    assert "InventoryTransferGateway" in return_source
    assert ".dispatch_return(" in return_source
    assert ".receive_return(" in return_source
    assert "TransferEvents.RETURN_CREATED" in return_source
    assert "TransferEvents.RETURN_COMPLETED" in return_source
    assert "InventoryTransferGateway" not in suggestion_source
    assert "TransferSuggestionService" in suggestion_source
    assert ".reserve(" in reservation_source


def test_transfer_request_use_cases_validate_granular_request_permissions():
    source = (
        Path("pos_spj_v13.4/backend/application/transfers/use_cases/transfer_request_use_cases.py").read_text()
        + Path("pos_spj_v13.4/backend/application/transfers/use_cases/transfer_reservation_use_cases.py").read_text()
        + Path("pos_spj_v13.4/backend/application/transfers/use_cases/transfer_picking_use_cases.py").read_text()
        + Path("pos_spj_v13.4/backend/application/transfers/use_cases/transfer_packaging_use_cases.py").read_text()
        + Path("pos_spj_v13.4/backend/application/transfers/use_cases/transfer_dispatch_use_cases.py").read_text()
        + Path("pos_spj_v13.4/backend/application/transfers/use_cases/transfer_receipt_use_cases.py").read_text()
        + Path("pos_spj_v13.4/backend/application/transfers/use_cases/blind_receipt_use_cases.py").read_text()
        + Path("pos_spj_v13.4/backend/application/transfers/use_cases/transfer_difference_use_cases.py").read_text()
        + Path("pos_spj_v13.4/backend/application/transfers/use_cases/transfer_return_use_cases.py").read_text()
        + Path("pos_spj_v13.4/backend/application/transfers/use_cases/transfer_suggestion_use_cases.py").read_text()
    )

    assert "TransferPermissions.REQUEST_CREATE" in source
    assert "TransferPermissions.REQUEST_EDIT" in source
    assert "TransferPermissions.REQUEST_SUBMIT" in source
    assert "TransferPermissions.APPROVE" in source
    assert "TransferPermissions.PARTIAL_APPROVE" in source
    assert "TransferPermissions.REJECT" in source
    assert "TransferPermissions.RESERVE" in source
    assert "TransferPermissions.PICK" in source
    assert "TransferPermissions.PICK_CONFIRM" in source
    assert "TransferPermissions.DISPATCH" in source
    assert "TransferPermissions.PARTIAL_DISPATCH" in source
    assert "TransferPermissions.RECEIVE" in source
    assert "TransferPermissions.PARTIAL_RECEIVE" in source
    assert "TransferPermissions.BLIND_RECEIVE" in source
    assert "TransferPermissions.DIFFERENCE_REVIEW" in source
    assert "TransferPermissions.DIFFERENCE_RESOLVE" in source
    assert "TransferPermissions.DIFFERENCE_ACCEPT" in source
    assert "TransferPermissions.RETURN_CREATE" in source
    assert "TransferPermissions.RETURN_APPROVE" in source
    assert "TransferPermissions.RETURN_DISPATCH" in source
