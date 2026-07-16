"""Bug 2 (arquitectura): ui/dashboard.py sin SQL y sin default de sucursal 1.

La UI del dashboard consume DashboardQueryService (registrado en AppContainer);
prohibido volver a `self.conn.execute(` o al fallback `sucursal_id=1`.
"""
from __future__ import annotations

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]


def _code(path: str) -> str:
    text = (APP_ROOT / path).read_text(encoding="utf-8")
    return "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("#")
    )


def test_dashboard_ui_has_no_sql():
    code = _code("ui/dashboard.py")
    assert "self.conn.execute(" not in code, (
        "ui/dashboard.py no debe ejecutar SQL — usar DashboardQueryService"
    )
    assert "conn.execute(" not in code
    assert "SELECT " not in code.upper().replace("SELECTOR", "")


def test_dashboard_ui_consumes_registered_query_service():
    code = _code("ui/dashboard.py")
    assert "DashboardQueryService" in code
    assert 'getattr(self._container, "dashboard_query_service"' in code


def test_dashboard_ui_has_no_integer_branch_fallback():
    code = _code("ui/dashboard.py")
    assert "sucursal_id',1)" not in code.replace('"', "'")
    assert "sucursal_id=1" not in code
    assert "sucursal_id: int" not in code


def test_dashboard_order_signal_is_uuid_string():
    code = _code("ui/dashboard.py")
    assert "ver_pedido = pyqtSignal(str)" in code
    assert "ver_pedido = pyqtSignal(int)" not in code
