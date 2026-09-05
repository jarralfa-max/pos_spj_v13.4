"""PROC-21: MeatProcessingValidator — domain-aware sync validator for the
new Procesamiento Cárnico schema. Mirrors the shape of
tests/test_refactor_v133.py::TestProductionValidator (the legacy sibling for
production_batches/production_outputs, untouched by this refactor)."""

from sync.domain_validators.meat_processing_validator import MeatProcessingValidator


def test_ignores_non_meat_processing_tables():
    v = MeatProcessingValidator()
    assert v.validate("ventas", {"status": "CLOSED"}, {}, {}) is None


class TestProcessingOrders:
    def test_rejects_reopening_closed_order(self):
        v = MeatProcessingValidator()
        err = v.validate(
            "processing_orders", {},
            {"id": "o1", "status": "CLOSED"}, {"status": "IN_PROGRESS"})
        assert err is not None
        assert "cerrada" in err.lower()

    def test_accepts_closed_staying_closed(self):
        v = MeatProcessingValidator()
        err = v.validate(
            "processing_orders", {},
            {"id": "o1", "status": "CLOSED"}, {"status": "CLOSED"})
        assert err is None

    def test_accepts_normal_progression(self):
        v = MeatProcessingValidator()
        err = v.validate(
            "processing_orders", {},
            {"id": "o1", "status": "APPROVED"}, {"status": "RELEASED"})
        assert err is None


class TestYieldReconciliations:
    def test_accepts_variance_within_default_threshold(self):
        v = MeatProcessingValidator()
        err = v.validate(
            "yield_reconciliations",
            {"id": "y1", "input_weight": "100", "actual_output_weight": "85"}, {}, {})
        assert err is None

    def test_rejects_extreme_variance(self):
        v = MeatProcessingValidator(max_variance_pct=50)
        err = v.validate(
            "yield_reconciliations",
            {"id": "y2", "input_weight": "100", "actual_output_weight": "10"}, {}, {})
        assert err is not None
        assert "variaci" in err.lower()

    def test_zero_input_weight_is_not_a_division_error(self):
        v = MeatProcessingValidator()
        err = v.validate(
            "yield_reconciliations",
            {"id": "y3", "input_weight": "0", "actual_output_weight": "0"}, {}, {})
        assert err is None


class TestProcessOutputs:
    def test_rejects_posted_output_with_zero_weight_and_quantity(self):
        v = MeatProcessingValidator()
        err = v.validate(
            "process_outputs",
            {"id": "p1", "weight": "0", "quantity": "0",
             "inventory_operation_id": "inv1"}, {}, {})
        assert err is not None
        assert "sospechoso" in err.lower()

    def test_accepts_posted_output_with_positive_weight(self):
        v = MeatProcessingValidator()
        err = v.validate(
            "process_outputs",
            {"id": "p2", "weight": "5", "quantity": "0",
             "inventory_operation_id": "inv1"}, {}, {})
        assert err is None

    def test_accepts_unposted_zero_weight_output(self):
        # Not yet posted to inventory — zero at this stage isn't suspicious
        # (the row simply hasn't been finalized).
        v = MeatProcessingValidator()
        err = v.validate(
            "process_outputs",
            {"id": "p3", "weight": "0", "quantity": "0", "inventory_operation_id": None},
            {}, {})
        assert err is None
