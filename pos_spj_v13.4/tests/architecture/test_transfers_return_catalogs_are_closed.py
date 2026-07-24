from backend.domain.transfers.enums import TransferReturnReason, TransferReturnStatus


def test_transfer_return_reason_and_status_catalogs_are_closed():
    assert {item.value for item in TransferReturnReason} == {
        "DESTINATION_REJECTION", "QUALITY_REJECTION", "WRONG_PRODUCT", "OVER_SHIPMENT",
        "DAMAGED", "TEMPERATURE_FAILURE", "BUSINESS_CANCELLATION",
    }
    assert {item.value for item in TransferReturnStatus} == {
        "REQUESTED", "APPROVED", "DISPATCHED", "IN_TRANSIT", "RECEIVED", "COMPLETED", "REJECTED",
    }
