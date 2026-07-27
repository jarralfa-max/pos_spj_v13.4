"""AppContainer registra e inyecta explícitamente los servicios canónicos.

Regla 16 del refactor skill: toda dependencia se inyecta explícitamente —
sin autoconstrucción lazy dentro de los servicios cuando se arma vía
container, y sin instancias duplicadas de la misma fuente de lectura.
(Test estático: PyQt no está disponible en CI para instanciar el container.)
"""
from __future__ import annotations

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
SRC = (APP_ROOT / "core" / "app_container.py").read_text(encoding="utf-8")
CODE = "\n".join(
    line for line in SRC.splitlines() if not line.strip().startswith("#")
)


def test_container_registers_dashboard_query_service():
    assert "self.dashboard_query_service = DashboardQueryService(self.db)" in CODE


def test_container_registers_finance_read_repository():
    assert "self.finance_read_repository = FinanceReadRepository(self.db)" in CODE


def test_container_registers_and_injects_supplier_credit_service():
    assert "self.supplier_credit_service = SupplierCreditService(self.db)" in CODE
    assert "supplier_credit_service=self.supplier_credit_service" in CODE


def test_caja_ticket_service_receives_printer_service_explicitly():
    """Bug 4: sin PrinterService inyectado, el corte Z jamás auto-imprimía."""
    assert "printer_service=self.printer_service" in CODE
    # La inyección tardía por atributo privado (legacy) no debe volver
    assert "caja_ticket_service._hw" not in CODE
    assert "hardware_service=None,  # wired later" not in SRC


def test_finanzas_ui_uses_registered_finance_read_repository():
    """La UI de finanzas no construye FinanceReadRepository inline."""
    text = (APP_ROOT / "modulos" / "finanzas_unificadas.py").read_text(
        encoding="utf-8"
    )
    code = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("#")
    )
    assert "FinanceReadRepository(db)" not in code
    assert "FinanceReadRepository(m.container.db)" not in code
    assert '"finance_read_repository"' in code
