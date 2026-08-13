"""CASH-25: Finanzas no cierra Caja ni recibe servicio legacy."""

from __future__ import annotations

from core.use_cases.finanzas import GestionarFinanzasUC, SolicitudCierreCaja


def test_cierre_caja_preserves_str_turno_id_when_denied():
    uuid_like = "018f9c2e-7b6a-7c3d-9e4f-0123456789ab"
    uc = GestionarFinanzasUC(finance_service=None)

    res = uc.cierre_caja(
        SolicitudCierreCaja(sucursal_id=1, turno_id=uuid_like, efectivo_contado=100.0)
    )

    assert not res.ok
    assert res.turno_id == uuid_like
    assert isinstance(res.turno_id, str)


def test_cierre_caja_does_not_int_cast_uuid_turno():
    uuid_like = "018f9c2e-7b6a-7c3d-9e4f-0123456789ab"
    uc = GestionarFinanzasUC(finance_service=None)

    res = uc.cierre_caja(
        SolicitudCierreCaja(sucursal_id=1, turno_id=uuid_like, efectivo_contado=50.0)
    )

    assert not res.ok
    assert "bounded context canonico de Caja" in res.error
