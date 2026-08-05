from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_yield_alert_schema_and_event_are_canonical():
    migration = (ROOT / "migrations/standalone/174_losses_bounded_context_schema.py").read_text(encoding="utf-8")
    events = (ROOT / "backend/domain/losses/events.py").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS loss_yield_alerts" in migration
    assert "yield_variance_id TEXT NOT NULL UNIQUE" in migration
    assert 'YIELD_ALERT_RAISED = "YIELD_ALERT_RAISED"' in events


def test_yield_calculation_has_no_float_or_sql():
    source = (ROOT / "backend/application/losses/production_loss.py").read_text(encoding="utf-8")
    assert "float(" not in source
    assert "SELECT " not in source.upper()
    assert "INSERT " not in source.upper()


def test_yield_reads_are_exposed_through_query_service():
    source = (ROOT / "backend/application/losses/yield_queries.py").read_text(encoding="utf-8")
    assert "class YieldMonitoringQueryService" in source
    assert "def recent_variances" in source
    assert "def open_alerts" in source
    assert "SELECT " not in source.upper()
