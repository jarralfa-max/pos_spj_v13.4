"""CRM-1 (§79, "No emojis" / master prompt §94) — icons come from IconProvider.

Legacy modulos/clientes.py uses emoji as icons throughout (KPI cards, tab
labels, RFM segment markers — see docs/architecture/CRM_0_CUSTOMER_MASTER_AUDIT.md
§1-2). The new module must use the canonical IconProvider instead. Detection
covers the common pictographic Unicode blocks (misc symbols/pictographs,
transport, supplemental symbols, dingbats, emoticons) rather than a fixed
character list, so new emoji don't silently slip through.
"""

from __future__ import annotations

import re

from .customers_crm_guardrails import CRM_UI_ROOT, crm_ui_py_files, relative

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # misc symbols & pictographs, transport, supplemental symbols, extended-A
    "\U00002600-\U000026FF"  # misc symbols
    "\U00002700-\U000027BF"  # dingbats (includes ✅)
    "\U00002B00-\U00002BFF"  # misc symbols & arrows (includes ⭐)
    "\U0001F1E6-\U0001F1FF"  # regional indicators (flags)
    "]"
)


def test_customers_crm_ui_has_no_emoji_icons():
    offenders = []
    for path in crm_ui_py_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            found = _EMOJI_RE.findall(line)
            if found:
                offenders.append(f"{relative(path)}:{lineno}: {found} — {line.strip()}")
    assert not offenders, (
        f"Emoji used as icon literals under {relative(CRM_UI_ROOT)} — use "
        "IconProvider instead:\n" + "\n".join(offenders)
    )
