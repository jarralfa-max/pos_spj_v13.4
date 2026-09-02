import pytest

from backend.bootstrap.bootstrap_severity import BootstrapFailureReason, BootstrapSeverity, severity_for


@pytest.mark.parametrize("reason", [
    BootstrapFailureReason.DATABASE_CORRUPTED_UNRECOVERABLE,
    BootstrapFailureReason.SCHEMA_INCOMPLETE,
    BootstrapFailureReason.IDENTITY_NOT_UUIDV7,
    BootstrapFailureReason.BOOTSTRAP_INVALID,
    BootstrapFailureReason.REQUIRED_DEPENDENCY_MISSING,
    BootstrapFailureReason.DEPENDENCY_GRAPH_INVALID,
    BootstrapFailureReason.INSTALLATION_LOCKED,
    BootstrapFailureReason.CRITICAL_CONFIGURATION_MISSING,
])
def test_fatal_reasons_classify_as_fatal(reason):
    assert severity_for(reason) is BootstrapSeverity.FATAL


@pytest.mark.parametrize("reason", [
    BootstrapFailureReason.WHATSAPP_UNAVAILABLE,
    BootstrapFailureReason.PRINTER_DISCONNECTED,
    BootstrapFailureReason.GEOCODING_UNAVAILABLE,
    BootstrapFailureReason.UPDATE_CHECKER_FAILED,
    BootstrapFailureReason.OPTIONAL_INTEGRATION_INACTIVE,
])
def test_degraded_reasons_classify_as_degraded(reason):
    assert severity_for(reason) is BootstrapSeverity.DEGRADED


@pytest.mark.parametrize("reason", [
    BootstrapFailureReason.BACKUP_OVERDUE,
    BootstrapFailureReason.OPTIONAL_DEVICE_DISCONNECTED,
    BootstrapFailureReason.CAMPAIGN_NOT_SYNCED,
    BootstrapFailureReason.SECONDARY_SERVICE_PAUSED,
    BootstrapFailureReason.SCHEMA_COVERAGE_INCOMPLETE,
])
def test_warning_reasons_classify_as_warning(reason):
    assert severity_for(reason) is BootstrapSeverity.WARNING


def test_every_reason_is_classified():
    # No BootstrapFailureReason should be left without a bucket — this is
    # what makes "no convertir una excepción de migración crítica en
    # warning" a fact about the code, not a convention someone can forget.
    for reason in BootstrapFailureReason:
        severity_for(reason)  # must not raise
