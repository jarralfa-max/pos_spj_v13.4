"""BI-21 guardrail — analytical_alerting must never import the concrete
notification/WhatsApp delivery stack directly.

Mirrors `test_forecasting_never_imports_treasury_directly.py` (BI-14): the
port (`AlertRecipientResolverPort`/`AlertDispatchPort`,
`backend/domain/analytical_alerting/integration_ports.py`) is the only
seam — an infrastructure adapter (future phase) wraps
`RecipientResolver`/`NotificationDispatcher`/`WhatsAppService`, but domain
and application code here never imports them concretely.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Precise import-shaped needles — deliberately NOT bare class-name
# substrings: this package's own port names (`AlertRecipientResolverPort`)
# legitimately contain "RecipientResolver" as a naming echo of the concrete
# class they abstract over, which a naive substring check would misfire on.
_FORBIDDEN_NEEDLES = (
    "import WhatsAppService",
    "import NotificationDispatcher",
    "import RecipientResolver",
    "core.services.whatsapp_service",
    "core.services.notifications.notification_dispatcher",
    "core.services.notifications.recipient_resolver",
    "core.services.notification_service",
)


def test_analytical_alerting_domain_and_application_never_import_notification_infra():
    domain_dir = ROOT / "backend/domain/analytical_alerting"
    application_dir = ROOT / "backend/application/analytical_alerting"
    for path in list(domain_dir.rglob("*.py")) + list(application_dir.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for needle in _FORBIDDEN_NEEDLES:
            assert needle not in source, f"{path} references forbidden {needle}"
