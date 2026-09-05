"""ASSET-1 (§13, §109-110) — the Activos UI must never execute SQL directly.

Ratchet: frontend/desktop/modules/assets/ does not exist yet (built starting
ASSET-16), so this scans an empty root today and passes vacuously. It fails
the moment any file under that root embeds SQL.
"""

from __future__ import annotations

import re

from tests.architecture.assets_guardrails import asset_ui_py_files, relative

_FORBIDDEN = re.compile(
    r"\bimport sqlite3\b"
    r"|\bcursor\s*\("
    r"|(?:cursor|conn|connection|_conn|db|_db)\s*\.\s*execute\s*\("
    r"|\b(SELECT\s+.+\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b",
    re.IGNORECASE,
)


def test_assets_ui_has_no_sql():
    offenders = []
    for path in asset_ui_py_files():
        text = path.read_text(encoding="utf-8")
        for m in _FORBIDDEN.finditer(text):
            offenders.append(f"{relative(path)}: {m.group(0)!r}")
    assert not offenders, (
        "SQL directo en la UI de Activos (debe pasar por QueryService/UseCase):\n"
        + "\n".join(offenders)
    )
