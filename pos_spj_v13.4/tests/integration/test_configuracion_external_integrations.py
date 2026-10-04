"""FASE 8 — las integraciones externas viven en servicios, no en widgets.

Las pantallas legacy que este archivo inspeccionaba (`modulos/configuracion.py`,
`config_hardware.py`, `config_modules.py`) se borraron con `modulos/`; esas
aserciones fallaban por `FileNotFoundError` sin proteger nada. Quedan las que
prueban los servicios. `HardwareDiagnosticsService` se retiró el 2026-10-04:
abría `serial.Serial` desde la capa de aplicación (§70.6) y no tenía ningún
consumidor; la prueba de cajón vive en Caja (`cash_register/hardware`).
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.application.dto.diagnostics import DiagnosticResult
from backend.application.services.payment_provider_verification_service import (
    PaymentProviderVerificationService,
)
from backend.application.services.smtp_diagnostics_service import SMTPSettingsApplicationService

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
EXTERNAL_IMPORT_RE = re.compile(
    r"\b(import|from)\s+(smtplib|serial|urllib|socket|subprocess|ssl)\b"
)


def test_no_external_integration_imports_in_configuracion_ui():
    root = PACKAGE_ROOT / "frontend" / "desktop" / "modules" / "configuracion"
    offenders = [
        str(path.relative_to(PACKAGE_ROOT)) for path in root.rglob("*.py")
        if EXTERNAL_IMPORT_RE.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"external integration imported in UI: {offenders}"


def test_smtp_test_service_fails_explicitly_on_bad_input():
    result = SMTPSettingsApplicationService().send_test_email(
        host="", port=587, username="", password="", use_tls=True, recipient=""
    )
    assert isinstance(result, DiagnosticResult) and result.ok is False and result.message


def test_mercado_pago_verify_service_fails_explicitly_on_blank_token():
    result = PaymentProviderVerificationService().verify_mercado_pago_token("")
    assert isinstance(result, DiagnosticResult) and result.ok is False
    assert "Access Token" in result.message
