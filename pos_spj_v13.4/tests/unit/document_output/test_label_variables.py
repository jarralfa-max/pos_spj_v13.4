"""SET-14 — "Variables": LabelVariable + LabelVariableSet. Pure domain —
no DB.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from backend.domain.document_output.enums import LabelVariableType
from backend.domain.document_output.exceptions import DocumentInvalidValueError, LabelVariableMissingError
from backend.domain.document_output.value_objects.label_variable import LabelVariable
from backend.domain.document_output.value_objects.label_variable_set import LabelVariableSet


class TestLabelVariableCreate:
    def test_requires_name(self):
        with pytest.raises(DocumentInvalidValueError):
            LabelVariable.create(name="   ", var_type=LabelVariableType.STRING)

    def test_defaults_to_required(self):
        variable = LabelVariable.create(name="product_name", var_type=LabelVariableType.STRING)
        assert variable.required is True

    def test_can_be_optional(self):
        variable = LabelVariable.create(
            name="expiration_date", var_type=LabelVariableType.DATE, required=False,
        )
        assert variable.required is False


class TestLabelVariableSetCreate:
    def test_requires_at_least_one_variable(self):
        with pytest.raises(DocumentInvalidValueError):
            LabelVariableSet.create([])

    def test_rejects_duplicate_names(self):
        with pytest.raises(DocumentInvalidValueError):
            LabelVariableSet.create([
                LabelVariable.create(name="product_name", var_type=LabelVariableType.STRING),
                LabelVariable.create(name="product_name", var_type=LabelVariableType.STRING),
            ])

    def test_accepts_distinct_names(self):
        variable_set = LabelVariableSet.create([
            LabelVariable.create(name="product_name", var_type=LabelVariableType.STRING),
            LabelVariable.create(name="net_weight", var_type=LabelVariableType.DECIMAL),
        ])
        assert len(variable_set.variables) == 2


def _weight_label_variable_set() -> LabelVariableSet:
    return LabelVariableSet.create([
        LabelVariable.create(name="product_name", var_type=LabelVariableType.STRING),
        LabelVariable.create(name="net_weight", var_type=LabelVariableType.DECIMAL),
        LabelVariable.create(name="lot_number", var_type=LabelVariableType.INTEGER, required=False),
        LabelVariable.create(name="expiration_date", var_type=LabelVariableType.DATE, required=False),
    ])


class TestAssertSatisfied:
    def test_all_required_variables_present_with_correct_type_passes(self):
        variable_set = _weight_label_variable_set()
        variable_set.assert_satisfied({"product_name": "Carne molida", "net_weight": Decimal("1.250")})

    def test_optional_variables_may_be_omitted(self):
        variable_set = _weight_label_variable_set()
        variable_set.assert_satisfied({"product_name": "Carne molida", "net_weight": Decimal("1.250")})

    def test_optional_variable_validated_when_supplied(self):
        variable_set = _weight_label_variable_set()
        variable_set.assert_satisfied({
            "product_name": "Carne molida", "net_weight": Decimal("1.250"),
            "expiration_date": date(2026, 9, 1),
        })

    def test_missing_required_variable_raises(self):
        variable_set = _weight_label_variable_set()
        with pytest.raises(LabelVariableMissingError):
            variable_set.assert_satisfied({"product_name": "Carne molida"})

    def test_missing_optional_variable_does_not_raise(self):
        variable_set = _weight_label_variable_set()
        variable_set.assert_satisfied({"product_name": "Carne molida", "net_weight": Decimal("1.250")})

    def test_wrong_type_raises(self):
        variable_set = _weight_label_variable_set()
        with pytest.raises(LabelVariableMissingError):
            variable_set.assert_satisfied({"product_name": "Carne molida", "net_weight": 1.25})

    def test_wrong_type_for_optional_variable_still_raises_when_supplied(self):
        variable_set = _weight_label_variable_set()
        with pytest.raises(LabelVariableMissingError):
            variable_set.assert_satisfied({
                "product_name": "Carne molida", "net_weight": Decimal("1.250"), "lot_number": "not-an-int",
            })

    def test_bool_never_satisfies_integer(self):
        variable_set = LabelVariableSet.create([
            LabelVariable.create(name="lot_number", var_type=LabelVariableType.INTEGER),
        ])
        with pytest.raises(LabelVariableMissingError):
            variable_set.assert_satisfied({"lot_number": True})
