"""PROC-24: slaughter preparation stub — feature flag stays off, contracts
validate their required fields and reject float."""

import pytest

from backend.domain.meat_processing.exceptions import (
    MeatProcessingConfigurationError,
    MeatProcessingInvariantError,
)
from backend.domain.meat_processing.slaughter.contracts import (
    AnimalLotContract,
    AnteMortemRecordContract,
    CarcassClassificationContract,
    ChillingRecordContract,
    CondemnationRecordContract,
    PostMortemRecordContract,
    SlaughterOrderContract,
)
from backend.domain.meat_processing.slaughter.enums import (
    AnimalLotStatus,
    AnteMortemDisposition,
    PostMortemDisposition,
    SlaughterOrderStatus,
)
from backend.domain.meat_processing.slaughter.feature_flag import (
    SLAUGHTER_ENABLED,
    ensure_slaughter_enabled,
)
from backend.shared.ids import new_uuid


def test_slaughter_is_disabled_by_default():
    assert SLAUGHTER_ENABLED is False


def test_ensure_slaughter_enabled_raises_while_disabled():
    with pytest.raises(MeatProcessingConfigurationError):
        ensure_slaughter_enabled()


class TestAnimalLotContract:
    def test_requires_ids_and_species(self):
        with pytest.raises(MeatProcessingInvariantError):
            AnimalLotContract(
                lot_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
                species="", supplier_reference="S-1")

    def test_rejects_float_head_count(self):
        with pytest.raises(MeatProcessingInvariantError):
            AnimalLotContract(
                lot_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
                species="bovino", supplier_reference="S-1", head_count=1.5)

    def test_defaults_to_received(self):
        lot = AnimalLotContract(
            lot_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
            species="bovino", supplier_reference="S-1")
        assert lot.status is AnimalLotStatus.RECEIVED


class TestSlaughterOrderContract:
    def test_requires_animal_lot_and_creator(self):
        with pytest.raises(MeatProcessingInvariantError):
            SlaughterOrderContract(
                order_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
                animal_lot_id="", created_by_user_id=new_uuid())

    def test_defaults_to_draft(self):
        order = SlaughterOrderContract(
            order_id=new_uuid(), branch_id=new_uuid(), warehouse_id=new_uuid(),
            animal_lot_id=new_uuid(), created_by_user_id=new_uuid())
        assert order.status is SlaughterOrderStatus.DRAFT


class TestInspectionContracts:
    def test_ante_mortem_requires_canonical_disposition(self):
        with pytest.raises(MeatProcessingInvariantError):
            AnteMortemRecordContract(
                record_id=new_uuid(), animal_lot_id=new_uuid(),
                inspector_user_id=new_uuid(), disposition="APPROVED")

    def test_ante_mortem_accepts_canonical_disposition(self):
        record = AnteMortemRecordContract(
            record_id=new_uuid(), animal_lot_id=new_uuid(), inspector_user_id=new_uuid(),
            disposition=AnteMortemDisposition.CONDITIONAL)
        assert record.disposition is AnteMortemDisposition.CONDITIONAL

    def test_post_mortem_requires_carcass_reference(self):
        with pytest.raises(MeatProcessingInvariantError):
            PostMortemRecordContract(
                record_id=new_uuid(), carcass_reference_id="", inspector_user_id=new_uuid(),
                disposition=PostMortemDisposition.APPROVED)


class TestCarcassAndCondemnation:
    def test_classification_requires_grade(self):
        with pytest.raises(MeatProcessingInvariantError):
            CarcassClassificationContract(
                carcass_reference_id=new_uuid(), grade="  ",
                classified_by_user_id=new_uuid())

    def test_condemnation_requires_reason_and_type(self):
        with pytest.raises(MeatProcessingInvariantError):
            CondemnationRecordContract(
                record_id=new_uuid(), source_reference_id=new_uuid(), source_type="",
                reason="", recorded_by_user_id=new_uuid())

    def test_condemnation_rejects_float_weight(self):
        with pytest.raises(MeatProcessingInvariantError):
            CondemnationRecordContract(
                record_id=new_uuid(), source_reference_id=new_uuid(),
                source_type="Carcass", reason="Lesión visible",
                recorded_by_user_id=new_uuid(), weight=2.5)


class TestChillingRecordContract:
    def test_requires_chamber(self):
        with pytest.raises(MeatProcessingInvariantError):
            ChillingRecordContract(
                record_id=new_uuid(), carcass_reference_id=new_uuid(), chamber_id="",
                target_temperature_c="4")

    def test_actual_temperature_optional(self):
        record = ChillingRecordContract(
            record_id=new_uuid(), carcass_reference_id=new_uuid(), chamber_id="C1",
            target_temperature_c="4")
        assert record.actual_temperature_c is None
