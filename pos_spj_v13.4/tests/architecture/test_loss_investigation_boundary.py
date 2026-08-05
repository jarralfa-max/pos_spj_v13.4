from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_loss15_mutations_are_application_owned_and_idempotent():
    service = (ROOT / "backend/application/losses/investigation.py").read_text(encoding="utf-8")
    repository = (ROOT / "backend/infrastructure/persistence/loss_investigation_repository.py").read_text(encoding="utf-8")
    assert "find_processed" in service
    assert "validate_uuidv7" in service
    assert "loss_processed_operations" in repository
    assert "loss_outbox" in repository
    assert "CREATE TABLE" not in service
    assert "CREATE TABLE" not in repository


def test_loss15_schema_has_findings_evidence_and_independent_conclusion():
    migration = (ROOT / "migrations/standalone/174_losses_bounded_context_schema.py").read_text(encoding="utf-8")
    for contract in ("loss_investigation_findings", "loss_investigation_evidence",
                     "conclusion_operation_id", "concluded_by_user_id",
                     "concluded_by_user_id <> opened_by_user_id"):
        assert contract in migration


def test_loss15_uses_granular_permissions_and_events():
    permissions = (ROOT / "backend/application/losses/permissions.py").read_text(encoding="utf-8")
    events = (ROOT / "backend/domain/losses/events.py").read_text(encoding="utf-8")
    for permission in ("LOSSES_OPEN_INVESTIGATION", "LOSSES_INVESTIGATE",
                       "LOSSES_CONCLUDE_INVESTIGATION"):
        assert permission in permissions
    for event in ("LOSS_INVESTIGATION_OPENED", "LOSS_INVESTIGATION_EVIDENCE_ADDED",
                  "LOSS_INVESTIGATION_FINDING_ADDED", "LOSS_INVESTIGATION_CONCLUDED"):
        assert event in events
