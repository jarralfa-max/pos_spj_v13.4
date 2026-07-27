from .allowlists import HARDCODED_RELATIVE_PATHS_ALLOWLIST
from .architecture_guardrails import RELATIVE_PATH_RE, assert_no_new_violations, collect_regex_violations, is_loose_relative_path_line


def test_no_loose_relative_paths() -> None:
    violations = collect_regex_violations(
        pattern=RELATIVE_PATH_RE,
        line_filter=is_loose_relative_path_line,
    )
    assert_no_new_violations("loose relative paths", violations, HARDCODED_RELATIVE_PATHS_ALLOWLIST)
