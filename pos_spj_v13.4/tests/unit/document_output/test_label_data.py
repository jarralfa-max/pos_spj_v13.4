"""SET-14 — "Serialización": LabelData. Pure domain — no DB."""

from __future__ import annotations

from decimal import Decimal

import pytest

from backend.domain.document_output.enums import DocumentType, LabelVariableType
from backend.domain.document_output.exceptions import DocumentInvalidValueError, LabelVariableMissingError
from backend.domain.document_output.value_objects.label_data import LabelData
from backend.domain.document_output.value_objects.label_variable import LabelVariable
from backend.domain.document_output.value_objects.label_variable_set import LabelVariableSet
from backend.shared.ids import new_uuid


class TestLabelDataCreate:
    def test_requires_a_label_document_type(self):
        with pytest.raises(DocumentInvalidValueError):
            LabelData.create(label_type=DocumentType.SALE_TICKET, title="Carne molida")

    @pytest.mark.parametrize(
        "label_type",
        [
            DocumentType.LOT_LABEL, DocumentType.WEIGHT_LABEL, DocumentType.TRANSFER_LABEL,
            DocumentType.COUNT_LABEL, DocumentType.ADJUSTMENT_LABEL, DocumentType.PRODUCT_LABEL,
        ],
    )
    def test_accepts_every_label_document_type(self, label_type):
        data = LabelData.create(label_type=label_type, title="Etiqueta")
        assert data.label_type is label_type

    def test_requires_title(self):
        with pytest.raises(DocumentInvalidValueError):
            LabelData.create(label_type=DocumentType.LOT_LABEL, title="   ")

    @pytest.mark.parametrize("copies", [0, -1, 1.5, True])
    def test_rejects_invalid_copies(self, copies):
        with pytest.raises(DocumentInvalidValueError):
            LabelData.create(label_type=DocumentType.LOT_LABEL, title="Etiqueta", copies=copies)

    def test_defaults(self):
        data = LabelData.create(label_type=DocumentType.LOT_LABEL, title="Etiqueta")
        assert data.body_lines == ()
        assert data.barcode is None
        assert data.qr_payload is None
        assert data.entity_ref is None
        assert data.copies == 1
        assert data.variables == {}


class TestLabelDataWithVariableSet:
    def _variable_set(self) -> LabelVariableSet:
        return LabelVariableSet.create([
            LabelVariable.create(name="product_name", var_type=LabelVariableType.STRING),
            LabelVariable.create(name="net_weight", var_type=LabelVariableType.DECIMAL),
        ])

    def test_valid_variables_pass_through(self):
        data = LabelData.create(
            label_type=DocumentType.WEIGHT_LABEL, title="Carne molida",
            variables={"product_name": "Carne molida", "net_weight": Decimal("1.250")},
            variable_set=self._variable_set(),
        )
        assert data.variables["net_weight"] == Decimal("1.250")

    def test_missing_required_variable_is_rejected_at_construction(self):
        with pytest.raises(LabelVariableMissingError):
            LabelData.create(
                label_type=DocumentType.WEIGHT_LABEL, title="Carne molida",
                variables={"product_name": "Carne molida"}, variable_set=self._variable_set(),
            )

    def test_no_variable_set_means_no_validation(self):
        data = LabelData.create(
            label_type=DocumentType.WEIGHT_LABEL, title="Carne molida", variables={"anything": "goes"},
        )
        assert data.variables == {"anything": "goes"}


class TestLabelDataToRenderData:
    def test_flattens_fields_and_stringifies_variables(self):
        data = LabelData.create(
            label_type=DocumentType.WEIGHT_LABEL, title="Carne molida",
            body_lines=("Peso neto: 1.250 kg", "Lote: L-001"), barcode="L-001", qr_payload="lot:L-001",
            entity_ref=new_uuid(), copies=2, variables={"net_weight": Decimal("1.250")},
        )
        rendered = data.to_render_data()
        assert rendered["label_type"] == "WEIGHT_LABEL"
        assert rendered["title"] == "Carne molida"
        assert rendered["body_lines"] == ["Peso neto: 1.250 kg", "Lote: L-001"]
        assert rendered["barcode"] == "L-001"
        assert rendered["copies"] == 2
        assert rendered["net_weight"] == "1.250"
        assert isinstance(rendered["net_weight"], str)
