"""
test_audit_service_registrar.py — v13.4
Verifica el alias registrar() de AuditService.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from unittest.mock import MagicMock, call


def _make_service():
    from core.services.audit_service import AuditService
    repo = MagicMock()
    return AuditService(repo), repo


def test_registrar_calls_log_change():
    svc, repo = _make_service()
    svc.registrar(
        accion="TEST_ACCION",
        entidad="productos",
        entidad_id=42,
        usuario_id=7,
        datos_antes={"precio": 10},
        datos_despues={"precio": 20},
    )
    repo.insert_audit_log.assert_called_once()
    kwargs = repo.insert_audit_log.call_args.kwargs
    assert kwargs["accion"] == "TEST_ACCION"
    assert kwargs["entidad"] == "productos"
    assert kwargs["entidad_id"] == "42"
    assert kwargs["usuario"] == "7"


def test_registrar_without_optional_params():
    svc, repo = _make_service()
    svc.registrar(accion="MINIMAL", entidad="ventas", entidad_id=1, usuario_id=1)
    repo.insert_audit_log.assert_called_once()


def test_log_change_still_works():
    """Verifica que el método original log_change() no fue alterado."""
    svc, repo = _make_service()
    svc.log_change(
        usuario="admin",
        accion="UPDATE",
        modulo="VENTAS",
        entidad="ventas",
        entidad_id="99",
    )
    repo.insert_audit_log.assert_called_once()
