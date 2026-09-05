"""ASSET-1 — shared scanners for the Activos/EAM bounded context guardrails.

Canonical layout (docs/refactor §10, mirrors customers_crm_guardrails.py):

    frontend/desktop/modules/assets/              single UI module (ASSET-16+)
    backend/domain/assets/                         entities/value_objects/policies (ASSET-3+)
    backend/application/assets/                     use_cases/commands/queries/permissions (ASSET-2+)
    backend/infrastructure/db/repositories/assets/  repository implementations (later phase)
    backend/infrastructure/db/schema/assets_schema.py  DDL (later phase)

Every guardrail here is a RATCHET: it scans whatever exists under these roots
today and FAILS the moment new code violates the rule. Positive-requirement
checks (must define scopes, must register routes, ...) skip with a pointer to
the phase that will make them meaningful rather than silently passing as if
satisfied. This module intentionally mirrors
``tests/architecture/customers_crm_guardrails.py`` rather than introducing a
new style.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

REPO = Path(__file__).resolve().parents[2]

ASSET_DOMAIN_ROOT = REPO / "backend" / "domain" / "assets"
ASSET_APPLICATION_ROOT = REPO / "backend" / "application" / "assets"
ASSET_INFRA_REPO_ROOT = REPO / "backend" / "infrastructure" / "db" / "repositories" / "assets"
ASSET_BACKEND_ROOTS = (ASSET_DOMAIN_ROOT, ASSET_APPLICATION_ROOT, ASSET_INFRA_REPO_ROOT)

# Canonical schema file (created when a later ASSET phase adds persistence).
ASSET_SCHEMA_FILE = REPO / "backend" / "infrastructure" / "db" / "schema" / "assets_schema.py"

# The single desktop UI module (§9-10 of the master prompt).
ASSET_UI_ROOT = REPO / "frontend" / "desktop" / "modules" / "assets"

# Canonical permission module for this context (created in ASSET-2).
ASSET_PERMISSIONS_FILE = ASSET_APPLICATION_ROOT / "permissions.py"

# Canonical routes file for the UI module (created in a later ASSET phase).
ASSET_ROUTES_FILE = ASSET_UI_ROOT / "assets_routes.py"

ALL_ASSET_CODE_ROOTS = ASSET_BACKEND_ROOTS + (ASSET_UI_ROOT,)

# Legacy files that own "activo/mantenimiento" logic today (see
# docs/refactor/assets_legacy_inventory.md). These are NOT exceptions granted
# to the new assets module — they are the burn-down list this guardrail suite
# exists to eventually make obsolete (a future ASSET-legacy-removal phase).
LEGACY_ASSET_FILES = (
    "pos_spj_v13.4/modulos/activos.py",
    "pos_spj_v13.4/core/services/asset_service.py",
)

# Thin/likely-abandoned scaffolding flagged in the ASSET-0 audit as
# "REVISAR -> probable DELETE_DUPLICATE" — tracked here, not silently ignored.
ORPHANED_ASSET_SCAFFOLDING = (
    "pos_spj_v13.4/backend/application/commands/asset_commands.py",
    "pos_spj_v13.4/backend/application/queries/asset_query_service.py",
    "pos_spj_v13.4/backend/application/use_cases/create_asset_use_case.py",
)


def _py_files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def asset_py_files(roots: Iterable[Path] = ALL_ASSET_CODE_ROOTS) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        files.extend(_py_files(root))
    return files


def asset_backend_py_files() -> list[Path]:
    return asset_py_files(ASSET_BACKEND_ROOTS)


def asset_ui_py_files() -> list[Path]:
    return asset_py_files((ASSET_UI_ROOT,))


def asset_source_text(roots: Iterable[Path] = ALL_ASSET_CODE_ROOTS) -> str:
    """Concatenated source of every .py file under the given Assets roots.

    Empty string when nothing has been written yet under a given root —
    callers asserting absence of a forbidden pattern get a vacuous pass,
    which is the intended ratchet behaviour.
    """
    chunks = []
    for path in asset_py_files(roots):
        try:
            chunks.append(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            chunks.append(path.read_text(encoding="latin-1"))
    return "\n".join(chunks)


def has_any_asset_code() -> bool:
    """True once at least one .py file exists under the canonical Assets roots."""
    return bool(asset_py_files())


def relative(path: Path) -> str:
    return path.relative_to(REPO).as_posix()
