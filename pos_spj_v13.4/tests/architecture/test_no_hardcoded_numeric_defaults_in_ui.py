from .allowlists import HARDCODED_NUMERIC_DEFAULTS_IN_UI_ALLOWLIST
from .architecture_guardrails import NUMERIC_DEFAULT_RE, UI_ROOTS, assert_no_new_violations, collect_regex_violations


def test_no_hardcoded_numeric_defaults_in_ui() -> None:
    violations = collect_regex_violations(pattern=NUMERIC_DEFAULT_RE, roots=UI_ROOTS)
    assert_no_new_violations("hardcoded numeric defaults in UI", violations, HARDCODED_NUMERIC_DEFAULTS_IN_UI_ALLOWLIST)
