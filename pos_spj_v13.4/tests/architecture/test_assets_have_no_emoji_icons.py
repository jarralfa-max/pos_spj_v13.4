"""ASSET-1 (§103, §109) — no emoji icons in the Activos UI; use IconProvider."""

from __future__ import annotations

import re

from tests.architecture.assets_guardrails import ASSET_UI_ROOT, asset_py_files, relative

_EMOJI = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "]"
)


def test_assets_ui_has_no_emoji_icons():
    offenders = []
    for path in asset_py_files((ASSET_UI_ROOT,)):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _EMOJI.search(line):
                offenders.append(f"{relative(path)}:{n}: {line.strip()}")
    assert not offenders, (
        "emojis usados como iconos en la UI de Activos (usar IconProvider):\n"
        + "\n".join(offenders)
    )
