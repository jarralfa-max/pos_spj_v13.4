from backend.domain.transfers.enums import ColdChainStatus, ReceiptQualityStatus


def test_cold_chain_and_receipt_quality_catalogs_are_closed():
    assert {item.value for item in ColdChainStatus} == {
        "COMPLIANT", "WARNING", "OUT_OF_RANGE", "PENDING_QUALITY", "BLOCKED",
    }
    assert {item.value for item in ReceiptQualityStatus} == {
        "AVAILABLE", "PENDING_INSPECTION", "QUARANTINED", "QUALITY_BLOCKED", "REJECTED",
    }
