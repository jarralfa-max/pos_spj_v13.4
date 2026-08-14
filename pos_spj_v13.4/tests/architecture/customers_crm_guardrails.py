"""CRM-1 — shared scanners for the Clientes/CRM bounded context guardrails.

Canonical layout (docs/refactor/customers_crm_master_prompt.md §10):

    frontend/desktop/modules/customers_crm/          single UI module
    backend/domain/{customers,crm,customer_service,customer_credit,customer_privacy}/
    backend/application/{customers,crm,customer_service,customer_credit,customer_privacy}/
    backend/infrastructure/db/repositories/{customers,crm,customer_service,customer_credit,customer_privacy}/
    backend/infrastructure/db/schema/customers_crm_schema.py   (created in CRM-3+)

CRM-1 ships these roots as empty packages (no domain/application logic yet —
that starts at CRM-3). Every guardrail here is therefore a RATCHET: it scans
whatever exists under these roots today (nothing) and FAILS the moment new
code violates the rule, exactly like ``test_design_system_guardrails.py`` and
``test_inventory_does_not_use_legacy_permissions.py`` already do for other
bounded contexts. Positive-requirement checks (must use UUIDv7, must define
scopes, ...) are written to ``pytest.skip`` with a pointer to the phase that
will make them meaningful (CRM-2/CRM-3/...), never to silently pass as if
satisfied.

This module intentionally mirrors ``architecture_guardrails.py`` /
``tests/architecture/test_inventory_*`` conventions rather than introducing a
new style.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parents[2]

# ── canonical bounded-context sub-packages (backend) ───────────────────────
CRM_SUBCONTEXTS = ("customers", "crm", "customer_service", "customer_credit", "customer_privacy")

CRM_DOMAIN_ROOTS = tuple(REPO / "backend" / "domain" / ctx for ctx in CRM_SUBCONTEXTS)
CRM_APPLICATION_ROOTS = tuple(REPO / "backend" / "application" / ctx for ctx in CRM_SUBCONTEXTS)
CRM_INFRA_REPO_ROOTS = tuple(
    REPO / "backend" / "infrastructure" / "db" / "repositories" / ctx for ctx in CRM_SUBCONTEXTS
)
CRM_BACKEND_ROOTS = CRM_DOMAIN_ROOTS + CRM_APPLICATION_ROOTS + CRM_INFRA_REPO_ROOTS

# Canonical schema files — one per sub-bounded-context (CRM-3 added
# customers_crm_schema.py for `customers`; CRM-4 added crm_schema.py for
# `crm`; customer_service/customer_credit/customer_privacy get their own
# when those phases build entities). Each sub-context owns its DDL the same
# way finance/inventory/suppliers each own a single schema file — a shared
# file across five unrelated aggregates would blur exactly the bounded-context
# lines CRM-1 exists to keep sharp.
CRM_SCHEMA_FILES: dict[str, Path] = {
    "customers": REPO / "backend" / "infrastructure" / "db" / "schema" / "customers_crm_schema.py",
    "crm": REPO / "backend" / "infrastructure" / "db" / "schema" / "crm_schema.py",
    "customer_service": REPO / "backend" / "infrastructure" / "db" / "schema" / "customer_service_schema.py",
    "customer_credit": REPO / "backend" / "infrastructure" / "db" / "schema" / "customer_credit_schema.py",
    "customer_privacy": REPO / "backend" / "infrastructure" / "db" / "schema" / "customer_privacy_schema.py",
}

# Backward-compatible single-file alias (Customer Master's own schema file,
# the first one CRM-3 created). Prefer CRM_SCHEMA_FILES for anything that
# should apply across the whole customers_crm module.
CRM_SCHEMA_FILE = CRM_SCHEMA_FILES["customers"]

# The single desktop UI module (§7-10 of the master prompt).
CRM_UI_ROOT = REPO / "frontend" / "desktop" / "modules" / "customers_crm"

# Canonical permission/scope module for this context (created in CRM-2).
CRM_PERMISSIONS_FILE = REPO / "backend" / "application" / "customers" / "permissions.py"

# Canonical routes file for the UI module (created in CRM-14+).
CRM_ROUTES_FILE = CRM_UI_ROOT / "customers_crm_routes.py"

ALL_CRM_CODE_ROOTS = CRM_BACKEND_ROOTS + (CRM_UI_ROOT,)

# Pre-existing legacy files that own "cliente/customer" logic today (see
# docs/architecture/CRM_0_CUSTOMER_MASTER_AUDIT.md). These are NOT exceptions
# granted to the new customers_crm module — they are the burn-down list this
# guardrail suite exists to eventually make obsolete (CRM-21/22). Tracked
# centrally so no test has to hardcode this list independently.
LEGACY_CUSTOMER_FILES = (
    # modulos/clientes.py and core/services/cliente_query_service.py were
    # retired (see docs/refactor/CRM-24_retiro_modulo_legacy.md) — removed
    # from here per this tuple's own rule ("no solo bajar de número").
    "core/services/cliente_service.py",
    "core/use_cases/cliente.py",
    "repositories/cliente_repository.py",
    "api/routers/clientes.py",
    "application/services/customer_credit_service.py",
    "backend/application/use_cases/create_customer_use_case.py",
    "backend/application/commands/customer_commands.py",
    "backend/application/queries/customer_history_query_service.py",
)


def _py_files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def crm_py_files(roots: Iterable[Path] = ALL_CRM_CODE_ROOTS) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        files.extend(_py_files(root))
    return files


def crm_backend_py_files() -> list[Path]:
    return crm_py_files(CRM_BACKEND_ROOTS)


def crm_ui_py_files() -> list[Path]:
    return crm_py_files((CRM_UI_ROOT,))


def existing_crm_schema_files() -> list[Path]:
    """The subset of CRM_SCHEMA_FILES that a phase has actually created so
    far. Empty until CRM-3."""
    return [path for path in CRM_SCHEMA_FILES.values() if path.exists()]


def crm_source_text(roots: Iterable[Path] = ALL_CRM_CODE_ROOTS) -> str:
    """Concatenated source of every .py file under the given CRM roots.

    Empty string when nothing has been written yet (CRM-1 baseline) — callers
    that assert absence of a forbidden pattern get a vacuous pass, which is
    the intended ratchet behaviour.
    """
    chunks = []
    for path in crm_py_files(roots):
        try:
            chunks.append(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            chunks.append(path.read_text(encoding="latin-1"))
    return "\n".join(chunks)


def has_any_crm_code() -> bool:
    """True once at least one .py file exists under the canonical CRM roots."""
    return bool(crm_py_files())


def relative(path: Path) -> str:
    return path.relative_to(REPO).as_posix()
