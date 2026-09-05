"""ASSET-1 (§9-10, §16) — canonical asset.* route registry.

Positive requirement: skips with a pointer to the phase that builds the
routes file (UI Foundations, later ASSET phase) rather than passing as if
satisfied — mirrors customers_crm_guardrails' documented convention.
"""

from __future__ import annotations

import pytest

from tests.architecture.assets_guardrails import ASSET_ROUTES_FILE

_REQUIRED_PREFIXES = ("assets.overview", "assets.directory", "assets.create")


def test_asset_routes_are_registered():
    if not ASSET_ROUTES_FILE.exists():
        pytest.skip(
            "assets_routes.py no existe aún — llega en la fase de UI Foundations "
            "(no antes de que exista frontend/desktop/modules/assets/)"
        )
    text = ASSET_ROUTES_FILE.read_text(encoding="utf-8")
    missing = [route for route in _REQUIRED_PREFIXES if route not in text]
    assert not missing, f"Rutas canónicas de Activos faltantes en assets_routes.py: {missing}"
