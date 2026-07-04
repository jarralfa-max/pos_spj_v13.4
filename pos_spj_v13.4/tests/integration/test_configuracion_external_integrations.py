"""FASE 8 — external integrations live in services, not PyQt widgets."""

from __future__ import annotations

import re
from pathlib import Path

from backend.application.dto.diagnostics import DiagnosticResult
from backend.application.services.hardware_diagnostics_service import HardwareDiagnosticsService
from backend.application.services.payment_provider_verification_service import (
    PaymentProviderVerificationService,
)
from backend.application.services.smtp_diagnostics_service import SMTPSettingsApplicationService

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
UI_FILES = (
    "modulos/configuracion.py",
    "modulos/config_hardware.py",
    "modulos/config_interfaz.py",
    "modulos/config_modules.py",
)
EXTERNAL_IMPORT_RE = re.compile(
    r"\b(import|from)\s+(smtplib|serial|urllib|socket|subprocess|ssl)\b"
)


def test_no_external_integration_imports_in_ui():
    offenders = []
    for rel in UI_FILES:
        src = (PACKAGE_ROOT / rel).read_text(encoding="utf-8")
        if EXTERNAL_IMPORT_RE.search(src):
            offenders.append(rel)
    assert not offenders, f"external integration imported in UI: {offenders}"


def test_smtp_test_uses_service():
    src = (PACKAGE_ROOT / "modulos" / "configuracion.py").read_text(encoding="utf-8")
    assert "smtp_diagnostics_service.send_test_email" in src
    # service returns explicit Result and never raises on bad input
    result = SMTPSettingsApplicationService().send_test_email(
        host="", port=587, username="", password="", use_tls=True, recipient=""
    )
    assert isinstance(result, DiagnosticResult) and result.ok is False and result.message


def test_mercado_pago_verify_uses_service():
    src = (PACKAGE_ROOT / "modulos" / "configuracion.py").read_text(encoding="utf-8")
    assert "payment_provider_verification_service.verify_mercado_pago_token" in src
    result = PaymentProviderVerificationService().verify_mercado_pago_token("")
    assert isinstance(result, DiagnosticResult) and result.ok is False
    assert "Access Token" in result.message


def test_hardware_diagnostics_uses_service():
    src = (PACKAGE_ROOT / "modulos" / "config_hardware.py").read_text(encoding="utf-8")
    for call in ("test_scale", "open_drawer", "ping_gateway", "current_ip"):
        assert f"hardware_diagnostics_service.{call}" in src
    svc = HardwareDiagnosticsService()
    assert isinstance(svc.ping_gateway(""), DiagnosticResult)
    assert svc.ping_gateway("").ok is False
    assert isinstance(svc.test_scale("NOPORT", 9600), DiagnosticResult)
    assert isinstance(svc.current_ip(), DiagnosticResult)
    # bad hex command -> explicit failure, no raise
    bad = svc.open_drawer(method="serial", command_hex="ZZ", location="", fallback_port="COM1")
    assert bad.ok is False
