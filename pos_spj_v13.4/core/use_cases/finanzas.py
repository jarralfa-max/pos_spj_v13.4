# core/use_cases/finanzas.py — GestionarFinanzasUC v13.5
"""
Caso de uso para operaciones financieras: cierre de caja, conciliación,
reportes de flujo y consulta de balances.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger("spj.use_cases.finanzas")


@dataclass
class SolicitudCierreCaja:
    sucursal_id: int
    turno_id: int
    efectivo_contado: float
    usuario: str
    notas: str = ""


@dataclass
class ResultadoCierreCaja:
    ok: bool
    turno_id: int = 0
    total_ventas: float = 0.0
    total_efectivo: float = 0.0
    diferencia: float = 0.0
    asiento_id: int = 0
    error: str = ""


@dataclass
class ResultadoBalance:
    ok: bool
    saldo_caja: float = 0.0
    cuentas_por_cobrar: float = 0.0
    cuentas_por_pagar: float = 0.0
    total_ventas_dia: float = 0.0
    total_compras_dia: float = 0.0
    error: str = ""


class GestionarFinanzasUC:

    def __init__(self, finance_service, caja_service=None, event_bus=None):
        self.finance = finance_service
        self.caja = caja_service
        self.bus = event_bus

    @classmethod
    def desde_container(cls, container) -> "GestionarFinanzasUC":
        return cls(
            finance_service=getattr(container, "finance_service", None),
            caja_service=getattr(container, "caja_service", None),
            event_bus=getattr(container, "event_bus", None),
        )

    def cierre_caja(self, solicitud: SolicitudCierreCaja) -> ResultadoCierreCaja:
        try:
            if self.caja is None:
                return ResultadoCierreCaja(ok=False, error="CajaService no disponible")

            resultado = self.caja.cerrar_turno(
                turno_id=solicitud.turno_id,
                efectivo_contado=solicitud.efectivo_contado,
                usuario=solicitud.usuario,
                notas=solicitud.notas,
            )
            if not resultado:
                return ResultadoCierreCaja(ok=False, error="Error al cerrar turno")

            total_ventas = resultado.get("total_ventas", 0.0)
            diferencia = round(solicitud.efectivo_contado - total_ventas, 2)

            # Asiento contable: diferencia de caja
            asiento_id = 0
            if self.finance and abs(diferencia) > 0:
                try:
                    cuenta_debe = "1101" if diferencia >= 0 else "6299"
                    cuenta_haber = "6299" if diferencia >= 0 else "1101"
                    asiento_id = self.finance.registrar_asiento(
                        cuenta_debe=cuenta_debe,
                        cuenta_haber=cuenta_haber,
                        concepto=f"Diferencia cierre caja turno {solicitud.turno_id}",
                        monto=abs(diferencia),
                        modulo="caja",
                        referencia_id=solicitud.turno_id,
                        evento="CIERRE_CAJA_DIFERENCIA",
                        sucursal_id=solicitud.sucursal_id,
                    ) or 0
                except Exception as e:
                    logger.warning("Asiento cierre caja: %s", e)

            if self.bus:
                try:
                    from core.events.event_bus import CONCILIACION_DIFERENCIA
                    self.bus.publish(CONCILIACION_DIFERENCIA, {
                        "turno_id": solicitud.turno_id,
                        "diferencia": diferencia,
                        "sucursal_id": solicitud.sucursal_id,
                    }, sucursal_id=solicitud.sucursal_id, prioridad=30)
                except Exception as e:
                    logger.debug("Bus cierre caja: %s", e)

            return ResultadoCierreCaja(
                ok=True,
                turno_id=solicitud.turno_id,
                total_ventas=total_ventas,
                total_efectivo=solicitud.efectivo_contado,
                diferencia=diferencia,
                asiento_id=asiento_id,
            )
        except Exception as e:
            logger.error("Cierre caja turno %s: %s", solicitud.turno_id, e)
            return ResultadoCierreCaja(ok=False, error=str(e))

    def consultar_balance(self, sucursal_id: int) -> ResultadoBalance:
        try:
            if self.finance is None:
                return ResultadoBalance(ok=False, error="FinanceService no disponible")

            saldo = self.finance.get_saldo_caja(sucursal_id) if hasattr(self.finance, "get_saldo_caja") else 0.0
            cxc = self.finance.get_total_cxc(sucursal_id) if hasattr(self.finance, "get_total_cxc") else 0.0
            cxp = self.finance.get_total_cxp(sucursal_id) if hasattr(self.finance, "get_total_cxp") else 0.0

            return ResultadoBalance(
                ok=True,
                saldo_caja=saldo,
                cuentas_por_cobrar=cxc,
                cuentas_por_pagar=cxp,
            )
        except Exception as e:
            logger.error("Consultar balance suc %s: %s", sucursal_id, e)
            return ResultadoBalance(ok=False, error=str(e))

    def registrar_asiento_manual(
        self, cuenta_debe: str, cuenta_haber: str,
        concepto: str, monto: float,
        sucursal_id: int = 1, usuario: str = "",
    ) -> dict:
        try:
            if self.finance is None:
                return {"ok": False, "error": "FinanceService no disponible"}
            if monto <= 0:
                return {"ok": False, "error": "Monto debe ser positivo"}

            asiento_id = self.finance.registrar_asiento(
                cuenta_debe=cuenta_debe,
                cuenta_haber=cuenta_haber,
                concepto=concepto,
                monto=monto,
                modulo="finanzas",
                evento="ASIENTO_MANUAL",
                sucursal_id=sucursal_id,
                metadata={"usuario": usuario},
            )
            return {"ok": True, "asiento_id": asiento_id}
        except Exception as e:
            logger.error("Asiento manual: %s", e)
            return {"ok": False, "error": str(e)}
