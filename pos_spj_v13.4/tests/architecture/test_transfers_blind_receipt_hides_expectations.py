from dataclasses import fields

from backend.application.transfers.dto.blind_receipt_dto import (
    BlindReceiptCountDTO,
    BlindReceiptObservedLineDTO,
)


def test_unconfirmed_blind_receipt_dto_cannot_expose_expected_values():
    field_names = {field.name for field in fields(BlindReceiptCountDTO)}

    assert field_names == {"count_id", "transfer_id", "shipment_id", "status", "lines"}
    assert not any("expected" in field_name for field_name in field_names)
    observed_fields = {field.name for field in fields(BlindReceiptObservedLineDTO)}
    assert observed_fields == {
        "transfer_line_id", "observed_quantity", "observed_weight", "observed_pieces",
        "temperature", "expires_on",
    }
