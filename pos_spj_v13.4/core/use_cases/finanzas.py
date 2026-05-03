# core/use_cases/finanzas.py
"""GestionarFinanzasUC — casos de uso financieros (cierre de caja, balance, asientos)."""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SolicitudCierreCaja:
    sucursal_id: int
    turno_id: int
    efectivo_contado: float
    usuario: str = "admin"
    comentarios: str = ""


@dataclass
class ResultadoCierreCaja:
    ok: bool
    turno_id: int = 0
    total_ventas: float = 0.0
    diferencia: float = 0.0
    error: str = ""


@dataclass
class ResultadoBalance:
    ok: bool
    saldo_caja: float = 0.0
    total_cxc: float = 0.0
    total_cxp: float = 0.0
    error: str = ""


@dataclass
class AsientoManualDTO:
    cuenta_debe: str
    cuenta_haber: str
    monto: float
    descripcion: str = ""
    usuario: str = "admin"
    sucursal_id: int = 1


class GestionarFinanzasUC:

    def __init__(self, finance_service=None, caja_service=None):
        self._finance = finance_service
        self._caja = caja_service

    def cierre_caja(self, solicitud: SolicitudCierreCaja) -> ResultadoCierreCaja:
        if not self._caja:
            return ResultadoCierreCaja(ok=False, error="caja_service no disponible")
        try:
            res = self._caja.cerrar_turno(
                turno_id=solicitud.turno_id,
                efectivo_contado=solicitud.efectivo_contado,
            )
            total_ventas = float(res.get("total_ventas", 0.0))
            diferencia = round(solicitud.efectivo_contado - total_ventas, 2)

            if self._finance and abs(diferencia) > 0.01:
                cuenta_debe  = "1100-caja" if diferencia > 0 else "5200-diferencias"
                cuenta_haber = "5200-diferencias" if diferencia > 0 else "1100-caja"
                try:
                    self._finance.registrar_asiento(
                        cuenta_debe=cuenta_debe,
                        cuenta_haber=cuenta_haber,
                        monto=abs(diferencia),
                        descripcion=f"Diferencia cierre turno {solicitud.turno_id}",
                        usuario=solicitud.usuario,
                        sucursal_id=solicitud.sucursal_id,
                    )
                except Exception as exc:
                    logger.warning("asiento diferencia cierre: %s", exc)

            return ResultadoCierreCaja(
                ok=True,
                turno_id=int(res.get("turno_id", solicitud.turno_id)),
                total_ventas=total_ventas,
                diferencia=diferencia,
            )
        except Exception as exc:
            logger.error("cierre_caja: %s", exc)
            return ResultadoCierreCaja(ok=False, error=str(exc))

    def consultar_balance(self, sucursal_id: int = 1) -> ResultadoBalance:
        if not self._finance:
            return ResultadoBalance(ok=False, error="finance_service no disponible")
        try:
            return ResultadoBalance(
                ok=True,
                saldo_caja=float(self._finance.get_saldo_caja(sucursal_id=sucursal_id) or 0),
                total_cxc=float(self._finance.get_total_cxc(sucursal_id=sucursal_id) or 0),
                total_cxp=float(self._finance.get_total_cxp(sucursal_id=sucursal_id) or 0),
            )
        except Exception as exc:
            logger.error("consultar_balance: %s", exc)
            return ResultadoBalance(ok=False, error=str(exc))

    def registrar_asiento_manual(self, dto: AsientoManualDTO) -> int:
        if not self._finance:
            raise RuntimeError("finance_service no disponible")
        if dto.monto <= 0:
            raise ValueError("monto debe ser mayor a cero")
        return int(self._finance.registrar_asiento(
            cuenta_debe=dto.cuenta_debe,
            cuenta_haber=dto.cuenta_haber,
            monto=dto.monto,
            descripcion=dto.descripcion,
            usuario=dto.usuario,
            sucursal_id=dto.sucursal_id,
        ) or 0)
