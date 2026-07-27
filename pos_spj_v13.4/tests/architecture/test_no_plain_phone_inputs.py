from .allowlists import PLAIN_PHONE_INPUTS_ALLOWLIST
from .architecture_guardrails import QLINEEDIT_RE, UI_ROOTS, assert_no_new_violations, collect_regex_violations, has_phone_term


def test_no_qlineedit_used_for_phone_inputs() -> None:
    violations = collect_regex_violations(
        pattern=QLINEEDIT_RE,
        roots=UI_ROOTS,
        line_filter=lambda _path, _number, line: has_phone_term(line),
    )
    assert_no_new_violations("QLineEdit used for phone inputs", violations, PLAIN_PHONE_INPUTS_ALLOWLIST)
