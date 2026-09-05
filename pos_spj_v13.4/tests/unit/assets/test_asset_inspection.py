"""ASSET-7 — InspectionChecklistTemplate/Item and AssetInspection."""

import pytest

from backend.domain.assets.entities.asset_inspection import AssetInspection
from backend.domain.assets.entities.inspection_checklist_template import (
    InspectionChecklistTemplate,
)
from backend.domain.assets.enums import (
    InspectionResponseType,
    InspectionResultStatus,
    InspectionType,
)
from backend.domain.assets.exceptions import AssetDomainError, InspectionStateInvalidError


class TestInspectionChecklistTemplate:
    def test_create_and_add_items(self):
        tpl = InspectionChecklistTemplate.create("Checklist de seguridad", InspectionType.SAFETY)
        item = tpl.add_item("¿Extintor vigente?", InspectionResponseType.BOOLEAN)
        assert item.order == 1
        assert len(tpl.items) == 1

    def test_choice_item_requires_choices(self):
        tpl = InspectionChecklistTemplate.create("Checklist", InspectionType.QUALITY)
        with pytest.raises(AssetDomainError):
            tpl.add_item("Estado", InspectionResponseType.CHOICE)

    def test_deactivate_reactivate(self):
        tpl = InspectionChecklistTemplate.create("Checklist", InspectionType.QUALITY)
        tpl.deactivate()
        assert tpl.active is False
        tpl.reactivate()
        assert tpl.active is True


class TestAssetInspection:
    def _inspection(self) -> AssetInspection:
        return AssetInspection.create("asset-1", InspectionType.PREVENTIVE, "inspector-1", "op-1")

    def test_create_requires_inspector(self):
        with pytest.raises(AssetDomainError):
            AssetInspection.create("asset-1", InspectionType.SAFETY, "", "op-1")

    def test_answer_then_record_result(self):
        insp = self._inspection()
        insp.answer("item-1", "true")
        insp.record_result(InspectionResultStatus.PASS_)
        assert insp.is_recorded() is True
        assert insp.passed() is True

    def test_cannot_answer_after_recorded(self):
        insp = self._inspection()
        insp.record_result(InspectionResultStatus.PASS_)
        with pytest.raises(InspectionStateInvalidError):
            insp.answer("item-1", "true")

    def test_cannot_record_result_twice(self):
        insp = self._inspection()
        insp.record_result(InspectionResultStatus.PASS_)
        with pytest.raises(InspectionStateInvalidError):
            insp.record_result(InspectionResultStatus.FAIL)

    def test_fail_shortcut(self):
        insp = self._inspection()
        insp.fail("Fuga detectada")
        assert insp.result is InspectionResultStatus.FAIL
        assert insp.passed() is False

    def test_pass_with_observations_counts_as_passed(self):
        insp = self._inspection()
        insp.record_result(InspectionResultStatus.PASS_WITH_OBSERVATIONS)
        assert insp.passed() is True
