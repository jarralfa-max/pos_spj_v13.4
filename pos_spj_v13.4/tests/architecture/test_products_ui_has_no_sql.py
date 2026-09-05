r"""PROD-18 (§41, "Sin SQL directo en UI") — the Products desktop UI never
executes raw SQL against a connection.

Two real regex collisions found and fixed while writing this, both matching
lessons already documented elsewhere in this pipeline's own memory before a
single test ran here:
1. A first draft copied `test_customers_crm_ui_has_no_sql.py`'s bare
   `\.execute\(` pattern verbatim — 59 false positives, since Products' UI
   correctly calls `.execute(command)` on injected UseCase objects throughout
   `presenter.py` (the RIGHT pattern); switched to the narrower, already-proven
   pattern from `test_productos_guardrails.py::PATTERNS["cursor_execute"]`
   (requires a DB-connection-shaped name immediately before `.execute(`).
2. Even that narrower pass still tripped twice more: `# pragma: no cover`
   (a routine Python coverage-tooling comment) collided with the SQL keyword
   `PRAGMA` (case-insensitive, inline trailing comments aren't stripped by a
   naive `startswith("#")` check), and `self.nav.select(0)` collided with a
   bare `\bSELECT\b` (no word-boundary regex distinguishes the SQL keyword
   from a Python method literally named `select`) — the exact same
   `SideNav.select()` collision this pipeline's CRM-14 phase already hit.
   Fixed by stripping trailing `#...` comments before matching, and requiring
   `SELECT` to be followed by whitespace (`SELECT\s+\w`, matching how
   `UPDATE\s+\w`/`DELETE\s+FROM` already avoid the same trap) rather than
   matching as a bare word.
"""

from __future__ import annotations

import re

from .products_ui_guardrails import PRODUCTS_UI_ROOT, products_ui_py_files, relative

_SQL_KEYWORDS = re.compile(
    r"\b(SELECT\s+\w|INSERT\s+INTO|UPDATE\s+\w|DELETE\s+FROM|DROP\s+TABLE|"
    r"CREATE\s+TABLE|PRAGMA\s+\w)\b",
    re.IGNORECASE,
)
_DB_EXECUTE_CALL = re.compile(
    r"(cursor|cur|conn|self\.db|self\.conn|self\._conn|self\.conexion|"
    r"self\.container\.db)\.execute"
)
_SQLITE_IMPORT = re.compile(r"^\s*import\s+sqlite3\b|^\s*from\s+sqlite3\b")


def _without_trailing_comment(line: str) -> str:
    """Best-effort strip of a trailing ``# ...`` comment (doesn't try to
    handle a literal ``#`` inside a string — none of this module's real code
    does that, confirmed while writing this test)."""
    idx = line.find("#")
    return line if idx == -1 else line[:idx]


def test_products_ui_has_no_raw_sql():
    offenders = []
    for path in products_ui_py_files():
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            code = _without_trailing_comment(line)
            if (_SQL_KEYWORDS.search(code) or _DB_EXECUTE_CALL.search(code)
                    or _SQLITE_IMPORT.search(code)):
                offenders.append(f"{relative(path)}:{lineno}: {line.strip()}")
    assert not offenders, (
        f"Raw SQL / direct DB access found under {relative(PRODUCTS_UI_ROOT)} — the "
        "UI must call a QueryService/UseCase, never the database:\n"
        + "\n".join(offenders))
