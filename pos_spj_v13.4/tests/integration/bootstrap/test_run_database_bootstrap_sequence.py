"""run_database_bootstrap_sequence — SHELL-4 regression coverage.

The specific bug this phase fixes: main.py's old third migration block
caught a bare `Exception` from the migration engine, logged "continuando
con repositorios como fallback", and kept booting anyway. These tests prove
the new single entry point never does that — a fatal migration failure
always comes back as `success=False`, never silently swallowed.
"""
from backend.bootstrap.bootstrap_state import BootstrapState
from backend.bootstrap.run_database_bootstrap import run_database_bootstrap_sequence
from backend.security.provisioning.installation import ProvisioningStatus


def test_full_sequence_succeeds_against_a_fresh_database(tmp_path):
    result = run_database_bootstrap_sequence(tmp_path / "spj.db")

    assert result.success is True
    assert result.final_state is BootstrapState.RUNNING
    assert len(result.step_results) == 4
    assert result.context.installation_status is ProvisioningStatus.UNINITIALIZED
    result.context.conn.close()


def test_migration_engine_failure_is_never_silently_swallowed(tmp_path, monkeypatch):
    import migrations.engine as real_engine

    def _boom(conn):
        raise RuntimeError("simulated critical migration failure")

    monkeypatch.setattr(real_engine, "up", _boom)

    result = run_database_bootstrap_sequence(tmp_path / "spj.db")

    assert result.success is False
    assert result.final_state is BootstrapState.FAILED
    failed = result.failed_step()
    assert failed is not None
    assert failed.step_name == "database_migration"
    # the schema/installation steps after it never ran
    assert len(result.step_results) == 2
    result.context.conn.close()


def test_corrupted_database_file_fails_before_any_migration_runs(tmp_path):
    db_path = tmp_path / "corrupt.db"
    db_path.write_bytes(b"not a real sqlite file" * 20)

    result = run_database_bootstrap_sequence(db_path)

    assert result.success is False
    failed = result.failed_step()
    assert failed.step_name == "database_integrity"
    assert len(result.step_results) == 1
