"""Prohibido commit()/rollback() en módulos PyQt.

Alias obligatorio del bugfix skill sobre la regla de
test_no_commit_rollback_in_frontend.py: reusa la allowlist congelada.
"""

from __future__ import annotations

from .allowlists import COMMIT_ROLLBACK_IN_UI_ALLOWLIST
from .architecture_guardrails import (
    COMMIT_ROLLBACK_RE,
    UI_ROOTS,
    assert_no_new_violations,
    collect_regex_violations,
)


def test_no_commit_rollback_in_pyqt() -> None:
    violations = collect_regex_violations(pattern=COMMIT_ROLLBACK_RE, roots=UI_ROOTS)
    assert_no_new_violations(
        "commit/rollback in PyQt modules", violations, COMMIT_ROLLBACK_IN_UI_ALLOWLIST
    )
