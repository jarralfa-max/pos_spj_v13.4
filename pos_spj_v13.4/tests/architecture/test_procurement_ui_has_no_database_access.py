"""PUR-13.5 — the canonical procurement UI never touches the database.

The purchasing UI (frontend/desktop/modules/purchasing) and its entry wrappers
(modulos/compra_directa.py, modulos/compras_enterprise.py) must delegate every
read/mutation to a QueryService / UseCase / Repository / UnitOfWork through the
presenter — never SQL, cursors, connections, repositories or UoW imports.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
UI_ROOTS = [
    REPO / "frontend" / "desktop" / "modules" / "purchasing",
    REPO / "modulos" / "compra_directa.py",
    REPO / "modulos" / "compras_enterprise.py",
]

# Scope execute/commit/rollback to DB-connection receivers so that use-case
# ``.execute(...)`` invocations (the correct delegation) are not flagged.
_FORBIDDEN = re.compile(
    r"\bimport sqlite3\b"
    r"|\bcursor\b"
    r"|(?:cursor|conn|connection|_conn|self\._conn\(\)|db|_db)\s*\.\s*execute\s*\("
    r"|(?:conn|connection|_conn|db|_db)\s*\.\s*(?:commit|rollback)\s*\("
    r"|\b(SELECT|INSERT\s+INTO|UPDATE\s+\w|DELETE\s+FROM)\b"
    r"|infrastructure\.db\.repositories"
    r"|ProcurementUnitOfWork",
    re.IGNORECASE,
)


def _ui_files():
    for root in UI_ROOTS:
        if root.is_file():
            yield root
        elif root.is_dir():
            for p in root.rglob("*.py"):
                if "__pycache__" not in p.parts:
                    yield p


def test_procurement_ui_has_no_database_access():
    offenders = []
    for path in _ui_files():
        text = path.read_text(encoding="utf-8")
        for m in _FORBIDDEN.finditer(text):
            offenders.append(f"{path.relative_to(REPO)}: {m.group(0)!r}")
    assert not offenders, (
        "La UI canónica de Compras no debe tocar la base de datos "
        "(usa QueryService/UseCase/Repository/UnitOfWork vía presenter):\n"
        + "\n".join(offenders))
