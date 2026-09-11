"""FASE 13 — la UI del módulo BI no ejecuta SQL directo.

Toda lectura debe pasar por los QueryServices / Application Services de BI. La UI
(modulos/reportes_bi_v2.py y helpers de charts) sólo compone y presenta.
"""
from .architecture_guardrails import (
    APP_ROOT, COMMIT_ROLLBACK_RE, SQL_RE, iter_source_lines,
)

#: Eran `modulos/reportes_bi_v2.py`, `bi_charts.py` y `bi_dashboard_view.py`.
#: Las tres se borraron en la reconstruccion y esta guardia se quedo mirando
#: rutas inexistentes: el `if not path.exists(): continue` de abajo la convertia
#: en verde permanente sin revisar una sola linea, mientras la UI de BI se
#: rehacia entera en otro sitio.
_BI_UI_ROOT = APP_ROOT / "frontend" / "desktop" / "modules" / "business_intelligence"
_BI_UI_FILES = tuple(sorted(
    p for p in _BI_UI_ROOT.rglob("*.py") if "__pycache__" not in p.parts))


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
