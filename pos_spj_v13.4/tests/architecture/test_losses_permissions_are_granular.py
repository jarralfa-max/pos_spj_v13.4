from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_losses_permission_catalog_does_not_define_general_merma_permissions():
    source = (ROOT / "backend/application/losses/permissions.py").read_text(encoding="utf-8")
    assert '"MERMA"' not in source
    assert '"MERMA.crear"' not in source
    assert '"MERMA.autorizar"' not in source


def test_losses_authorization_is_backend_owned_and_fail_closed():
    source = (ROOT / "backend/application/losses/authorization.py").read_text(encoding="utf-8")
    assert "LossConfigurationError" in source
    assert "APPROVE_OVER_LIMIT" in source
    assert "LossSegregationOfDutiesError" in source


def test_current_legacy_permissions_remain_explicit_debt_until_ui_cutover():
    source = (ROOT / "modulos/merma.py").read_text(encoding="utf-8")
    assert '"MERMA.crear"' in source
    assert '"MERMA.autorizar"' in source
