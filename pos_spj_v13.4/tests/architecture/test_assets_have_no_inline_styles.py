"""ASSET-1 (§89, §109) — no `setStyleSheet(` / local QSS in the Activos UI."""

from __future__ import annotations

from tests.architecture.assets_guardrails import ASSET_UI_ROOT, asset_py_files, relative


def test_assets_ui_has_no_inline_stylesheets():
    offenders = []
    for path in asset_py_files((ASSET_UI_ROOT,)):
        text = path.read_text(encoding="utf-8")
        if "setStyleSheet(" in text:
            offenders.append(relative(path))
    assert not offenders, (
        f"setStyleSheet() usado en la UI de Activos (usar Design System): {offenders}"
    )
