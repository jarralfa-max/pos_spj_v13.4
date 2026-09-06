"""No service may receive the DI container as an opaque service bag.

`container` is unfortunately also a Logistics *domain* word — a physical
shipping container — so the shared `APPCONTAINER_RE` matches
`backend/application/logistics/service.py`'s
`register_container(*, container: PhysicalContainer, ...)` and the call that
forwards that entity (`shipment.attach_container(container=container, ...)`).
Neither is a Service Locator: both name a concrete, imported domain class.

The smell this guard exists for is an OPAQUE bag a service reaches into
(`getattr(container, "db", ...)`), so the exemption below is deliberately
narrow: a file qualifies only if it never mentions `AppContainer` at all AND
annotates `container` with a concrete domain type. Anything that actually
touches the DI container keeps being reported, which
`test_domain_container_exemption_does_not_disarm_the_guard` pins down.
"""

import re

from .allowlists import APPCONTAINER_PASSED_TO_SERVICES_ALLOWLIST
from .architecture_guardrails import (
    APPCONTAINER_RE,
    assert_no_new_violations,
    collect_regex_violations,
    is_service_path,
)

# Concrete domain classes whose instances legitimately travel as `container`.
DOMAIN_CONTAINER_ANNOTATION_RE = re.compile(r"\bcontainer\s*:\s*PhysicalContainer\b")


def _is_domain_container_file(source: str) -> bool:
    return "AppContainer" not in source and bool(DOMAIN_CONTAINER_ANNOTATION_RE.search(source))


def test_no_appcontainer_passed_to_services() -> None:
    violations = collect_regex_violations(pattern=APPCONTAINER_RE, path_filter=is_service_path)
    violations = [
        violation
        for violation in violations
        if not _is_domain_container_file(violation.path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert_no_new_violations(
        "AppContainer passed to services", violations, APPCONTAINER_PASSED_TO_SERVICES_ALLOWLIST
    )


def test_domain_container_exemption_does_not_disarm_the_guard() -> None:
    """The exemption must not let a real DI container through."""
    domain_only = (
        "from backend.domain.logistics.entities import PhysicalContainer\n"
        "def register(*, container: PhysicalContainer) -> None: ...\n"
    )
    assert _is_domain_container_file(domain_only)

    # Same domain annotation, but the file also touches the DI container.
    mixed = domain_only + "from core.app_container import AppContainer\n"
    assert not _is_domain_container_file(mixed)

    # The classic Service Locator shape stays reported.
    service_locator = 'def build(container):\n    return getattr(container, "db", None)\n'
    assert not _is_domain_container_file(service_locator)
