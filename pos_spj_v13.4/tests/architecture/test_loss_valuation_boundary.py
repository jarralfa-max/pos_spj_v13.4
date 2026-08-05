from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_loss18_preserves_cost_provenance_and_exact_values():
    migration=(ROOT/"migrations/standalone/174_losses_bounded_context_schema.py").read_text(encoding="utf-8");domain=(ROOT/"backend/domain/losses/valuation.py").read_text(encoding="utf-8")
    for value in ("loss_valuations","loss_cost_references","reference_type","reference_id","gross_value","recovered_value","net_loss_value"):assert value in migration
    assert "Decimal" in domain and "isinstance(value,(bool,float))" in domain
def test_loss18_emits_valuation_and_finance_request_through_outbox():
    events=(ROOT/"backend/domain/losses/events.py").read_text(encoding="utf-8");repository=(ROOT/"backend/infrastructure/persistence/loss_valuation_repository.py").read_text(encoding="utf-8")
    assert "LOSS_VALUED" in events and "LOSS_FINANCE_RECOGNITION_REQUESTED" in events
    assert "loss_outbox" in repository and "loss_processed_operations" in repository and "SAVEPOINT" in repository
