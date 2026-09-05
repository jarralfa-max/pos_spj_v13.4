"""ASSET-1 (§110) — the new Assets/EAM bounded context tolerates zero
architecture-guardrail exceptions. Mirrors
test_customers_crm_legacy_allowlist_is_empty.py.
"""

from __future__ import annotations

from tests.architecture.allowlists import ASSETS_MODULE_ALLOWLIST
from tests.architecture.assets_guardrails import ALL_ASSET_CODE_ROOTS, relative


def test_assets_module_allowlist_is_empty():
    assert ASSETS_MODULE_ALLOWLIST == {}, (
        "ASSETS_MODULE_ALLOWLIST no está vacío — el nuevo bounded context de "
        f"Activos no debe tolerar excepciones a los guardrails: {ASSETS_MODULE_ALLOWLIST}"
    )


def test_assets_module_allowlist_entries_are_under_canonical_roots():
    root_prefixes = tuple(relative(root) for root in ALL_ASSET_CODE_ROOTS)
    stray = [path for path in ASSETS_MODULE_ALLOWLIST if not any(
        path.startswith(prefix) for prefix in root_prefixes)]
    assert not stray, f"Entradas fuera de las rutas canónicas de Activos: {stray}"
