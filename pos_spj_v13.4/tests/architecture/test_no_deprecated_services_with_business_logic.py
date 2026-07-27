from .allowlists import DEPRECATED_SERVICES_WITH_BUSINESS_LOGIC_ALLOWLIST
from .architecture_guardrails import DEPRECATED_SERVICE_LOGIC_RE, assert_no_new_violations, collect_regex_violations, is_deprecated_service_path


def test_no_deprecated_services_with_business_logic() -> None:
    violations = collect_regex_violations(
        pattern=DEPRECATED_SERVICE_LOGIC_RE,
        path_filter=is_deprecated_service_path,
    )
    assert_no_new_violations(
        "deprecated/legacy services with business logic",
        violations,
        DEPRECATED_SERVICES_WITH_BUSINESS_LOGIC_ALLOWLIST,
    )
