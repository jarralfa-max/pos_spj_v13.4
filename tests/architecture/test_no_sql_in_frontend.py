from .allowlists import SQL_IN_UI_ALLOWLIST
from .architecture_guardrails import SQL_RE, UI_ROOTS, assert_no_new_violations, collect_regex_violations


def test_no_sql_in_frontend() -> None:
    violations = collect_regex_violations(pattern=SQL_RE, roots=UI_ROOTS)
    assert_no_new_violations("SQL in UI", violations, SQL_IN_UI_ALLOWLIST)
