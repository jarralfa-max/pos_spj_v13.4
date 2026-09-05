"""ASSET-1 (§89, §109) — no hardcoded hex colors in the Activos UI."""

from __future__ import annotations

import re

from tests.architecture.assets_guardrails import ASSET_UI_ROOT, asset_py_files, relative

_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3}\b|#[0-9a-fA-F]{6}\b")


def test_assets_ui_has_no_hardcoded_hex_colors():
    offenders = []
    for path in asset_py_files((ASSET_UI_ROOT,)):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _HEX_COLOR.search(line):
                offenders.append(f"{relative(path)}:{n}: {line.strip()}")
    assert not offenders, (
        "colores hex hardcodeados en la UI de Activos (usar tokens del Design System):\n"
        + "\n".join(offenders)
    )
