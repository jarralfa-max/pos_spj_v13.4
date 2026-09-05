"""ASSET-1 (§29-30, §54, §110) — maintenance code never writes to Finance.

Maintenance work order cost confirmation must publish MAINTENANCE_COST_CONFIRMED
and let Finance/AP decide OPEX vs CAPEX — it must never call finance_service
or PostingEngine directly. Complements test_assets_do_not_post_journal_entries
(broader Activos-wide check) with a check scoped to any file whose path
signals it's maintenance-related, so a future `application/assets/use_cases/
maintenance_*.py` can't reintroduce the legacy coupling under a different name.
"""

from __future__ import annotations

import re

from tests.architecture.assets_guardrails import ALL_ASSET_CODE_ROOTS, asset_py_files, relative

_MAINTENANCE_PATH = re.compile(r"maintenance|mantenimiento", re.IGNORECASE)
_FORBIDDEN = re.compile(
    r"\bfinance_service\b|\bFinanceService\b|registrar_asiento\s*\(|\bPostingEngine\b",
)


def test_assets_maintenance_code_does_not_write_finance():
    offenders = []
    for path in asset_py_files(ALL_ASSET_CODE_ROOTS):
        if not _MAINTENANCE_PATH.search(path.as_posix()):
            continue
        text = path.read_text(encoding="utf-8")
        for m in _FORBIDDEN.finditer(text):
            offenders.append(f"{relative(path)}: {m.group(0)!r}")
    assert not offenders, (
        "Código de mantenimiento en Activos escribe a Finanzas directamente "
        "(debe emitir MAINTENANCE_COST_CONFIRMED y dejar que Finance/AP decida):\n"
        + "\n".join(offenders)
    )
