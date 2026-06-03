from .allowlists import APPCONTAINER_PASSED_TO_SERVICES_ALLOWLIST
from .architecture_guardrails import APPCONTAINER_RE, assert_no_new_violations, collect_regex_violations, is_service_path


def test_no_appcontainer_passed_to_services() -> None:
    violations = collect_regex_violations(pattern=APPCONTAINER_RE, path_filter=is_service_path)
    assert_no_new_violations("AppContainer passed to services", violations, APPCONTAINER_PASSED_TO_SERVICES_ALLOWLIST)
