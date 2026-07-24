from backend.domain.transfers.enums import DifferenceResolutionType, DifferenceType


def test_transfer_difference_and_resolution_catalogs_are_closed_and_complete():
    assert {item.value for item in DifferenceType} == {
        "SHORT_QUANTITY", "OVER_QUANTITY", "WEIGHT_VARIANCE", "WRONG_PRODUCT",
        "WRONG_LOT", "DAMAGED", "TEMPERATURE_VARIANCE", "EXPIRED",
        "QUALITY_FAILURE", "PACKAGE_MISSING", "SEAL_BROKEN", "LOST_IN_TRANSIT",
        "DOCUMENT_MISMATCH",
    }
    assert {item.value for item in DifferenceResolutionType} == {
        "ACCEPT_SHORTAGE", "ACCEPT_OVERAGE", "RETURN_TO_ORIGIN", "SEND_REPLACEMENT",
        "QUALITY_QUARANTINE", "CREATE_LOSS_CASE", "CREATE_CARRIER_CLAIM",
        "CREATE_SUPPLIER_CLAIM", "ADJUST_DOCUMENT", "RECOUNT", "REWEIGH",
        "OTHER_AUTHORIZED",
    }
