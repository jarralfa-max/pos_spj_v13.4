from .allowlists import SCHEMA_CHANGES_OUTSIDE_MIGRATIONS_ALLOWLIST
from .architecture_guardrails import SCHEMA_CHANGE_RE, SOURCE_SUFFIXES, assert_no_new_violations, collect_regex_violations, outside_migrations


def test_no_create_or_alter_table_outside_migrations() -> None:
    violations = collect_regex_violations(
        pattern=SCHEMA_CHANGE_RE,
        suffixes=SOURCE_SUFFIXES,
        path_filter=outside_migrations,
    )
    assert_no_new_violations(
        "CREATE TABLE / ALTER TABLE outside migrations",
        violations,
        SCHEMA_CHANGES_OUTSIDE_MIGRATIONS_ALLOWLIST,
    )
