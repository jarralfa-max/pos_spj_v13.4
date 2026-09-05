import pytest

from backend.domain.analytical_alerting.enums import AlertType
from backend.domain.analytical_alerting.services.fingerprint import build_fingerprint


def test_fingerprint_is_deterministic_composite():
    fp1 = build_fingerprint(AlertType.STOCKOUT_RISK, "b1", "p1")
    fp2 = build_fingerprint(AlertType.STOCKOUT_RISK, "b1", "p1")
    assert fp1 == fp2 == "STOCKOUT_RISK:b1:p1"


def test_different_branch_or_target_yields_different_fingerprint():
    fp_a = build_fingerprint(AlertType.STOCKOUT_RISK, "b1", "p1")
    fp_b = build_fingerprint(AlertType.STOCKOUT_RISK, "b2", "p1")
    fp_c = build_fingerprint(AlertType.STOCKOUT_RISK, "b1", "p2")
    assert len({fp_a, fp_b, fp_c}) == 3


def test_different_alert_type_yields_different_fingerprint():
    fp_a = build_fingerprint(AlertType.STOCKOUT_RISK, "b1", "p1")
    fp_b = build_fingerprint(AlertType.OVERSTOCK, "b1", "p1")
    assert fp_a != fp_b


def test_rejects_empty_branch_or_target():
    with pytest.raises(ValueError):
        build_fingerprint(AlertType.STOCKOUT_RISK, "", "p1")
    with pytest.raises(ValueError):
        build_fingerprint(AlertType.STOCKOUT_RISK, "b1", "")
