"""ASSET-1 (§89-90, §109) — Activos UI uses canonical components, not raw
PyQt widgets that already have a Design System equivalent (StandardTable V2,
MoneyInput, route-based navigation instead of QTabWidget)."""

from __future__ import annotations

from tests.architecture.assets_guardrails import ASSET_UI_ROOT, asset_source_text

_FORBIDDEN_RAW_WIDGETS = ("QTableWidget", "QTabWidget", "QGroupBox", "QDoubleSpinBox")


def test_assets_ui_does_not_use_raw_pyqt_widgets_with_canonical_equivalents():
    source = asset_source_text((ASSET_UI_ROOT,))
    offenders = [tok for tok in _FORBIDDEN_RAW_WIDGETS if tok in source]
    assert not offenders, (
        "La UI de Activos usa widgets PyQt crudos con equivalente canónico "
        f"(StandardTable V2 / MoneyInput / rutas en vez de tabs): {offenders}"
    )
