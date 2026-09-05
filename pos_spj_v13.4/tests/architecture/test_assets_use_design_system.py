"""ASSET-1 (§89-90, §109-110) — Activos UI uses only the canonical Design System."""

from __future__ import annotations

from tests.architecture.assets_guardrails import ASSET_UI_ROOT, asset_source_text

_FORBIDDEN_LEGACY_IMPORTS = (
    "modulos.ui_components",
    "modulos.design_tokens",
    "modulos.spj_styles",
)


def test_assets_ui_does_not_use_legacy_component_libraries():
    source = asset_source_text((ASSET_UI_ROOT,))
    offenders = [tok for tok in _FORBIDDEN_LEGACY_IMPORTS if tok in source]
    assert not offenders, (
        "La UI de Activos importa librerías de componentes legacy "
        f"(usar frontend/desktop/design_system/): {offenders}"
    )


def test_assets_ui_files_exist_check_is_meaningful():
    # Sanity: this suite must scan the real UI root, not a typo'd path.
    assert ASSET_UI_ROOT.as_posix().endswith("frontend/desktop/modules/assets")
