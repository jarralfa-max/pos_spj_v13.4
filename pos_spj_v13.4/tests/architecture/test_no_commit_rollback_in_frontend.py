from .allowlists import COMMIT_ROLLBACK_IN_UI_ALLOWLIST
from .architecture_guardrails import COMMIT_ROLLBACK_RE, UI_ROOTS, assert_no_new_violations, collect_regex_violations


def test_no_commit_rollback_in_frontend() -> None:
    violations = collect_regex_violations(pattern=COMMIT_ROLLBACK_RE, roots=UI_ROOTS)
    assert_no_new_violations("commit/rollback in UI", violations, COMMIT_ROLLBACK_IN_UI_ALLOWLIST)
