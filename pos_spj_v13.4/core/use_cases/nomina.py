# core/use_cases/nomina.py — SPJ POS v13.5
"""
Caso de uso: Gestionar Nómina

Orquesta el flujo completo de pago de nómina:
  1. Calcular nómina (RRHHService)
  2. Publicar NOMINA_GENERADA con payload canónico
  3. Procesar pago (RRHHService — solo escribe nomina_pagos/notifica; no OPEX directo)
  4. Auditar pago (HRRuleEngine — escribe hr_auditoria_log)
  5. Publicar NOMINA_PAGADA al EventBus

Finanzas consume NOMINA_GENERADA y NOMINA_PAGADA para registrar el impacto
contable de forma idempotente por operation_id. Este UC ya no llama
FinanceService.registrar_asiento() directamente para evitar doble registro.

Acceso desde AppContainer: container.uc_nomina
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from core.rrhh.events import (
    PayrollGeneratedPayload,
    PayrollPaidPayload,
    new_operation_id,
)

logger = logging.getLogger("spj.use_cases.nomina")


@dataclass
class SolicitudNomina:
    empleado_id:  int
    fecha_inicio: str        # "YYYY-MM-DD"
    fecha_fin:    str        # "YYYY-MM-DD"
    metodo_pago:  str = "efectivo"
    operation_id: str = ""


@dataclass
class ResultadoNomina:
    ok:              bool
    empleado_id:     int   = 0
    nombre_completo: str   = ""
    neto_a_pagar:    float = 0.0
    neto_deducido:   float = 0.0
    imss_obrero:     float = 0.0
    imss_patronal:   float = 0.0
    isr_mensual:     float = 0.0
    asiento_id:      int   = 0
    asiento_imss_id: int   = 0
    payroll_payment_id: int = 0
    operation_id:    str   = ""
    error:           str   = ""


class GestionarNominaUC:
    """Orquestador del flujo de pago de nómina."""

    def __init__(
        self,
        rrhh_service,
        finance_service,
        hr_rule_engine = None,
        event_bus      = None,
    ):
        self._rrhh    = rrhh_service
        self._finance = finance_service  # conservado por compatibilidad; Finanzas consume eventos
        self._hr      = hr_rule_engine
        self._bus     = event_bus

    @classmethod
    def desde_container(cls, container) -> "GestionarNominaUC":
        from core.events.event_bus import EventBus
        return cls(
            rrhh_service    = container.rrhh_service,
            finance_service = container.finance_service,
            hr_rule_engine  = getattr(container, "hr_rule_engine", None),
            event_bus       = EventBus(),
        )

    def ejecutar(
        self,
        solicitud:   SolicitudNomina,
        sucursal_id: int,
        admin_user:  str,
    ) -> ResultadoNomina:
        """Ejecuta el flujo completo y deja Finanzas como consumidor de eventos."""
        op_id = str(solicitud.operation_id or "").strip() or new_operation_id("nomina")

        try:
            datos = self._rrhh.calcular_nomina(
                solicitud.empleado_id,
                solicitud.fecha_inicio,
                solicitud.fecha_fin,
            )
        except ValueError as exc:
            return ResultadoNomina(ok=False, error=str(exc), operation_id=op_id)
        except Exception as exc:
            logger.error("GestionarNominaUC.calcular_nomina: %s", exc)
            return ResultadoNomina(ok=False, error=str(exc), operation_id=op_id)

        datos["periodo_inicio"] = solicitud.fecha_inicio
        datos["periodo_fin"] = solicitud.fecha_fin
        datos["operation_id"] = op_id

        neto_deducido = float(datos.get("neto_deducido", datos.get("neto_a_pagar", 0.0)) or 0.0)
        total_nomina = float(datos.get("neto_a_pagar", neto_deducido) or 0.0)
        imss_patronal = float(datos.get("retenciones", {}).get("imss_patronal", 0.0) or 0.0)
        nombre = datos.get("nombre_completo", "")

        try:
            self._rrhh.procesar_pago_nomina(
                datos_nomina = datos,
                metodo_pago  = solicitud.metodo_pago,
                sucursal_id  = sucursal_id,
                admin_user   = admin_user,
                operation_id = op_id,
                publish_events = False,
            )
        except Exception as exc:
            logger.error("GestionarNominaUC.procesar_pago_nomina: %s", exc)
            return ResultadoNomina(ok=False, error=str(exc), operation_id=op_id)

        payroll_payment_id = int(datos.get("payroll_payment_id") or 0)

        if payroll_payment_id:
            self._publish(
                PayrollGeneratedPayload(
                    operation_id=op_id,
                    employee_id=solicitud.empleado_id,
                    period_start=solicitud.fecha_inicio,
                    period_end=solicitud.fecha_fin,
                    total=total_nomina,
                    neto=neto_deducido,
                    sucursal_id=sucursal_id,
                    nombre=nombre,
                    payroll_payment_id=payroll_payment_id,
                ),
                async_=True,
            )

        if self._hr and hasattr(self._hr, "registrar_pago_auditado"):
            try:
                self._hr.registrar_pago_auditado(
                    empleado_id = solicitud.empleado_id,
                    nombre      = nombre,
                    monto       = neto_deducido,
                    periodo     = solicitud.fecha_fin,
                    sucursal_id = sucursal_id,
                    usuario     = admin_user,
                )
            except Exception as exc:
                logger.debug("GestionarNominaUC hr_auditoria: %s", exc)

        if payroll_payment_id:
            self._publish(
                PayrollPaidPayload(
                    operation_id=op_id,
                    payroll_payment_id=payroll_payment_id,
                    employee_id=solicitud.empleado_id,
                    period_start=solicitud.fecha_inicio,
                    period_end=solicitud.fecha_fin,
                    total=total_nomina,
                    neto=neto_deducido,
                    metodo_pago=solicitud.metodo_pago,
                    sucursal_id=sucursal_id,
                    nombre=nombre,
                    source_id=payroll_payment_id,
                ),
                async_=True,
            )

        return ResultadoNomina(
            ok              = True,
            empleado_id     = solicitud.empleado_id,
            nombre_completo = nombre,
            neto_a_pagar    = total_nomina,
            neto_deducido   = neto_deducido,
            imss_obrero     = float(datos.get("imss_obrero", 0.0) or 0.0),
            imss_patronal   = imss_patronal,
            isr_mensual     = float(datos.get("isr_mensual", 0.0) or 0.0),
            payroll_payment_id = payroll_payment_id,
            operation_id    = op_id,
        )

    def _publish(self, payload, *, async_: bool = True) -> None:
        if not self._bus:
            return
        try:
            self._bus.publish(payload.event_type, payload.to_dict(), async_=async_)
        except Exception as exc:
            logger.warning("GestionarNominaUC publish %s: %s", payload.event_type, exc)
