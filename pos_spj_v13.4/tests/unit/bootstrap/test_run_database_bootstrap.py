from backend.bootstrap.run_database_bootstrap import database_bootstrap_steps


def test_database_bootstrap_steps_is_the_canonical_sequence():
    names = [step.name for step in database_bootstrap_steps()]
    assert names == [
        "database_integrity", "schema_compatibility", "database_migration",
        "schema_validation", "installation_state",
    ]
