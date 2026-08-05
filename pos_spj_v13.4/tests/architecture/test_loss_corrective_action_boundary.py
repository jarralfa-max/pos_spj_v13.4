from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_loss17_has_canonical_states_segregation_and_events():
    migration=(ROOT/"migrations/standalone/174_losses_bounded_context_schema.py").read_text(encoding="utf-8"); service=(ROOT/"backend/application/losses/corrective_action.py").read_text(encoding="utf-8"); events=(ROOT/"backend/domain/losses/events.py").read_text(encoding="utf-8")
    for state in ("OPEN","IN_PROGRESS","PENDING_VERIFICATION","EFFECTIVE","INEFFECTIVE"): assert state in migration
    assert "verified_by_user_id <> owner_user_id" in migration; assert "validate_uuidv7" in service
    for event in ("LOSS_CORRECTIVE_ACTION_CREATED","LOSS_CORRECTIVE_ACTION_SUBMITTED","LOSS_CORRECTIVE_ACTION_VERIFIED"): assert event in events
def test_loss17_repository_owns_sql_and_outbox():
    repository=(ROOT/"backend/infrastructure/persistence/loss_corrective_action_repository.py").read_text(encoding="utf-8")
    assert "loss_processed_operations" in repository and "loss_outbox" in repository and "SAVEPOINT" in repository
    assert "CREATE TABLE" not in repository
