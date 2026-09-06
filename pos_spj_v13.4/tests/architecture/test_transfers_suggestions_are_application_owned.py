from pathlib import Path
from tests.architecture.architecture_guardrails import APP_ROOT


def test_transfer_suggestions_have_no_ui_sql_or_legacy_engine_dependency():
    domain = (APP_ROOT / "backend/domain/transfers/services/transfer_suggestion_service.py").read_text()
    application = (APP_ROOT / "backend/application/transfers/use_cases/transfer_suggestion_use_cases.py").read_text()
    source = domain + application

    assert "sqlite3" not in source
    assert "TransferSuggestionEngine" not in source
    assert "core.services.transfer_suggestion_engine" not in source
    assert "ProductTransferProfileQueryService" not in source
    assert "TransferSuggestionSupplyQueryService" in application
    assert "TransferSuggestionSettingsQueryService" in application
    assert "TRANSFER_SUGGESTION_REQUESTED" in application
    assert "TransferEvents.SUGGESTION_CREATED" in application
    assert "float(" not in source
