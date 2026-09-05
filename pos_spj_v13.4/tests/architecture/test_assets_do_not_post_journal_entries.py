"""ASSET-1 (§2, §33, §54, §77, §110) — Activos never posts journal entries.

Finanzas owns asientos contables. Activos may only PROPOSE capitalization
(AssetCapitalizationProposal) and read financial projections; it must never
import PostingEngine or call finance_service.registrar_asiento directly.
See docs/refactor/assets_finance_boundary_map.md.
"""

from __future__ import annotations

import re

from tests.architecture.assets_guardrails import ALL_ASSET_CODE_ROOTS, asset_py_files, relative

_FORBIDDEN = re.compile(
    r"\bPostingEngine\b"
    r"|registrar_asiento\s*\("
    r"|\bJournalEntry\b"
    r"|cuenta_debe|cuenta_haber"
    r"|\b610[0-9]\b|\b130[0-9]\b",  # cuentas contables hardcodeadas (§109)
)


def test_assets_do_not_post_journal_entries():
    offenders = []
    for path in asset_py_files(ALL_ASSET_CODE_ROOTS):
        text = path.read_text(encoding="utf-8")
        for m in _FORBIDDEN.finditer(text):
            offenders.append(f"{relative(path)}: {m.group(0)!r}")
    assert not offenders, (
        "Activos intenta contabilizar directamente (eso es responsabilidad de "
        "Finanzas):\n" + "\n".join(offenders)
    )
