"""CRM-1 (§99, "Allowlist vacía") — the new CRM module never accrues legacy debt.

Two different allowlists exist for this bounded context
(tests/architecture/allowlists.py):

- ``CUSTOMERS_CRM_MODULE_ALLOWLIST`` — exceptions granted to files *inside*
  the new canonical CRM paths (backend/domain|application/{customers,crm,
  customer_service,customer_credit,customer_privacy}/,
  backend/infrastructure/db/repositories/{...}/,
  frontend/desktop/modules/customers_crm/). This one must stay empty forever
  — it is the whole point of building the new bounded context guardrailed
  from CRM-1 onward instead of accumulating debt like the legacy modules did.
- ``CUSTOMERS_CRM_LEGACY_CONSUMERS`` — the burn-down list of pre-existing
  legacy files (modulos/clientes.py and friends) that still own "cliente"
  logic outside the new module. That one is *expected* to be non-empty until
  CRM-21/22 retire those files; it is not checked here.
"""

from __future__ import annotations

from .allowlists import CUSTOMERS_CRM_MODULE_ALLOWLIST
from .customers_crm_guardrails import ALL_CRM_CODE_ROOTS, relative


def test_customers_crm_module_allowlist_is_empty():
    assert CUSTOMERS_CRM_MODULE_ALLOWLIST == {}, (
        "CUSTOMERS_CRM_MODULE_ALLOWLIST is not empty — the new CRM bounded "
        "context must not tolerate architecture-guardrail exceptions:\n"
        f"{CUSTOMERS_CRM_MODULE_ALLOWLIST}"
    )


def test_customers_crm_module_allowlist_entries_are_under_canonical_roots():
    """Guards against the allowlist quietly becoming a dumping ground for
    files outside the CRM bounded context (which would defeat its purpose)."""
    root_prefixes = tuple(relative(root) for root in ALL_CRM_CODE_ROOTS)
    stray = [
        path for path in CUSTOMERS_CRM_MODULE_ALLOWLIST
        if not any(path.startswith(prefix) for prefix in root_prefixes)
    ]
    assert not stray, f"Entries outside the canonical CRM roots: {stray}"
