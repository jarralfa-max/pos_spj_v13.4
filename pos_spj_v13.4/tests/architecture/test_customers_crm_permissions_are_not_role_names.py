"""CRM-1 (§59, "No usar if role == 'admin'") — authorization is never by role name.

Two checks:

1. RATCHET (active now): no CRM code compares a role/user attribute against a
   hardcoded role-name string to make an authorization decision — e.g.
   ``if role == "admin"`` or ``if rol_nombre == "gerente"``.
2. Positive check on the canonical permission module
   (``backend/application/customers/permissions.py``, mirroring
   ``backend/application/cash_register/permissions.py``'s ``CashPermissions``):
   once it exists (CRM-2), its permission codes must use the
   ``MODULE.accion`` vocabulary and must not literally be role names. Skipped
   until CRM-2 creates that file.
"""

from __future__ import annotations

import re

import pytest

from .customers_crm_guardrails import ALL_CRM_CODE_ROOTS, CRM_PERMISSIONS_FILE, crm_py_files, relative

_ROLE_NAME_COMPARISON = re.compile(
    r"""\b(role|rol|role_name|rol_nombre)\s*(==|!=)\s*["'](admin|administrador|vendedor|"""
    r"""supervisor|gerente|cajero|auditor)["']""",
    re.IGNORECASE,
)

_KNOWN_ROLE_NAMES = {
    "admin", "administrador", "vendedor", "supervisor", "gerente", "cajero", "auditor",
    "crm_viewer", "crm_agent", "crm_sales_representative", "crm_sales_supervisor",
    "crm_sales_manager", "crm_account_manager", "crm_customer_service_agent",
    "crm_customer_service_supervisor", "crm_credit_analyst", "crm_credit_manager",
    "crm_data_steward", "crm_privacy_officer", "crm_marketing_operator", "crm_auditor",
    "crm_administrator",
}
_CANONICAL_CODE = re.compile(r"^[A-Z][A-Z_]*\.[a-z][a-z0-9_.]*$")


def test_customers_crm_does_not_authorize_by_role_name_comparison():
    offenders = []
    for path in crm_py_files(ALL_CRM_CODE_ROOTS):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _ROLE_NAME_COMPARISON.search(line):
                offenders.append(f"{relative(path)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Authorization by hardcoded role-name comparison found — gate on a "
        "granular permission code instead:\n" + "\n".join(offenders)
    )


def test_customers_crm_permission_codes_are_not_role_names():
    if not CRM_PERMISSIONS_FILE.exists():
        pytest.skip(
            f"{relative(CRM_PERMISSIONS_FILE)} does not exist yet — CRM-2 creates the "
            "canonical CustomerPermissions class. This guardrail activates then."
        )
    source = CRM_PERMISSIONS_FILE.read_text(encoding="utf-8")
    codes = re.findall(r'=\s*["\']([^"\']+)["\']', source)
    offenders = [c for c in codes if c.lower() in _KNOWN_ROLE_NAMES]
    malformed = [c for c in codes if "." in c and not _CANONICAL_CODE.match(c)]
    assert not offenders, f"Permission code(s) literally are role names: {offenders}"
    assert not malformed, (
        f"Permission code(s) don't follow the canonical MODULE.accion format: {malformed}"
    )
