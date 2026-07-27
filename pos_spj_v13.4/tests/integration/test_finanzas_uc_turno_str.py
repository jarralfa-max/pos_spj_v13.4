"""FASE 4 (caja) — GestionarFinanzasUC keeps the turno identity as str.

The cierre-caja use case must not cast turno_id to int (REGLA CERO): a UUIDv7
turno id would crash on int(). The DTOs declare turno_id as str and the result
preserves whatever the caja service returns, unchanged.
"""

from __future__ import annotations

from core.use_cases.finanzas import (
    GestionarFinanzasUC,
    SolicitudCierreCaja,
)


class _FakeCaja:
    def __init__(self, returned_turno_id):
        self._tid = returned_turno_id
        self.called_with = None

    def cerrar_turno(self, turno_id, efectivo_contado):
        self.called_with = turno_id
        return {"turno_id": self._tid, "total_ventas": 100.0}


def test_cierre_caja_preserves_str_turno_id():
    uuid_like = "018f9c2e-7b6a-7c3d-9e4f-0123456789ab"
    caja = _FakeCaja(uuid_like)
    uc = GestionarFinanzasUC(finance_service=None, caja_service=caja)
    res = uc.cierre_caja(
        SolicitudCierreCaja(sucursal_id=1, turno_id=uuid_like, efectivo_contado=100.0)
    )
    assert res.ok
    assert res.turno_id == uuid_like  # not int-cast, not mangled
    assert isinstance(res.turno_id, str)


def test_cierre_caja_does_not_int_cast_uuid_turno():
    # A real UUID would raise ValueError under the old int(res["turno_id"]) path.
    uuid_like = "018f9c2e-7b6a-7c3d-9e4f-0123456789ab"
    uc = GestionarFinanzasUC(finance_service=None, caja_service=_FakeCaja(uuid_like))
    res = uc.cierre_caja(
        SolicitudCierreCaja(sucursal_id=1, turno_id=uuid_like, efectivo_contado=50.0)
    )
    assert res.ok  # would be False (caught ValueError) under the legacy int() cast
