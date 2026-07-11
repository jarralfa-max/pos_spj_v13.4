"""FASE 13 — la UI del módulo BI no ejecuta SQL directo.

Toda lectura debe pasar por los QueryServices / Application Services de BI. La UI
(modulos/reportes_bi_v2.py y helpers de charts) sólo compone y presenta.
"""
from .architecture_guardrails import (
    APP_ROOT, COMMIT_ROLLBACK_RE, SQL_RE, iter_source_lines,
)

_BI_UI_FILES = (
    APP_ROOT / "modulos" / "reportes_bi_v2.py",
    APP_ROOT / "modulos" / "bi_charts.py",
)


def test_bi_ui_has_no_sql():
    offending = []
    for path in _BI_UI_FILES:
        if not path.exists():
            continue
        for num, line in iter_source_lines(path):
            if SQL_RE.search(line):
                offending.append(f"{path.name}:{num}: {line.strip()}")
    assert not offending, "SQL directo en UI de BI:\n" + "\n".join(offending)


def test_bi_ui_has_no_commit_rollback():
    offending = []
    for path in _BI_UI_FILES:
        if not path.exists():
            continue
        for num, line in iter_source_lines(path):
            if COMMIT_ROLLBACK_RE.search(line):
                offending.append(f"{path.name}:{num}: {line.strip()}")
    assert not offending, "commit/rollback en UI de BI:\n" + "\n".join(offending)
