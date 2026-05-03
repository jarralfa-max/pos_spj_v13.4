# core/use_cases/nomina.py — SPJ POS v13.5
"""
Caso de uso: Gestionar Nómina

Orquesta el flujo completo de pago de nómina:
  1. Calcular nómina (RRHHService)
  2. Procesar pago (RRHHService — escribe nomina_pagos + treasury opex)
  3. Asiento contable sueldos/caja     [6101/1101] (FinanceService)
  4. Asiento IMSS patronal devengado   [6102/2201] (FinanceService)
  5. Auditar pago (HRRuleEngine — escribe hr_auditoria_log)
  6. Publicar NOMINA_PAGADA al EventBus

Brecha que cierra: RRHHService.procesar_pago_nomina() llama a
treasury.registrar_gasto_opex() pero NUNCA llama registrar_asiento().
El pago de nómina no tiene entrada en financial_event_log.
Este UC agrega los asientos sin modificar RRHHService.

Acceso desde AppContainer: container.uc_nomina
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("spj.use_cases.nomina")


# ── DTOs ─────────────────────────────────────────────────────────────────────

@dataclass
class SolicitudNomina:
    empleado_id:  int
    fecha_inicio: str        # "YYYY-MM-DD"
    fecha_fin:    str        # "YYYY-MM-DD"
    metodo_pago:  str = "efectivo"


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
    error:           str   = ""


# ── Caso de uso ───────────────────────────────────────────────────────────────

class GestionarNominaUC:
    """
    Orquestador del flujo de pago de nómina.

    Uso desde AppContainer:
        uc = container.uc_nomina
        res = uc.ejecutar(SolicitudNomina(...), sucursal_id, admin_user)
    """

    def __init__(
        self,
        rrhh_service,
        finance_service,
        hr_rule_engine = None,
        event_bus      = None,
    ):
        self._rrhh    = rrhh_service
        self._finance = finance_service
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

    # ── Punto de entrada ─────────────────────────────────────────────────────

    def ejecutar(
        self,
        solicitud:   SolicitudNomina,
        sucursal_id: int,
        admin_user:  str,
    ) -> ResultadoNomina:
        """
        Ejecuta el flujo completo de pago de nómina.
        RRHHService maneja el cálculo y el pago; este UC agrega los asientos
        contables en financial_event_log que faltaban en ese flujo.
        """
        # ── 1. Calcular nómina ───────────────────────────────────────────────
        try:
            datos = self._rrhh.calcular_nomina(
                solicitud.empleado_id,
                solicitud.fecha_inicio,
                solicitud.fecha_fin,
            )
        except ValueError as exc:
            return ResultadoNomina(ok=False, error=str(exc))
        except Exception as exc:
            logger.error("GestionarNominaUC.calcular_nomina: %s", exc)
            return ResultadoNomina(ok=False, error=str(exc))

        # ── 2. Procesar pago (escribe nomina_pagos + treasury) ───────────────
        try:
            self._rrhh.procesar_pago_nomina(
                datos_nomina = datos,
                metodo_pago  = solicitud.metodo_pago,
                sucursal_id  = sucursal_id,
                admin_user   = admin_user,
            )
        except Exception as exc:
            logger.error("GestionarNominaUC.procesar_pago_nomina: %s", exc)
            return ResultadoNomina(ok=False, error=str(exc))

        neto_deducido = datos.get("neto_deducido", datos.get("neto_a_pagar", 0.0))
        imss_patronal = datos.get("retenciones", {}).get("imss_patronal", 0.0)
        nombre        = datos.get("nombre_completo", "")

        # ── 3. Asiento sueldos/caja  [6101 / 1101] ──────────────────────────
        asiento_id = 0
        try:
            asiento_id = self._finance.registrar_asiento(
                debe         = "6101",
                haber        = "1101",
                concepto     = f"Nómina {nombre} {solicitud.fecha_fin}",
                monto        = neto_deducido,
                modulo       = "nomina",
                referencia_id= solicitud.empleado_id,
                evento       = "NOMINA_PAGADA",
                sucursal_id  = sucursal_id,
                metadata     = {
                    "periodo_inicio": solicitud.fecha_inicio,
                    "periodo_fin":    solicitud.fecha_fin,
                    "metodo_pago":    solicitud.metodo_pago,
                },
            )
        except Exception as exc:
            logger.warning("GestionarNominaUC asiento 6101/1101: %s", exc)

        # ── 4. Asiento IMSS patronal  [6102 / 2201] ─────────────────────────
        asiento_imss_id = 0
        if imss_patronal > 0:
            try:
                asiento_imss_id = self._finance.registrar_asiento(
                    debe         = "6102",
                    haber        = "2201",
                    concepto     = f"IMSS patronal {nombre} {solicitud.fecha_fin}",
                    monto        = imss_patronal,
                    modulo       = "nomina",
                    referencia_id= solicitud.empleado_id,
                    evento       = "IMSS_PATRONAL_DEVENGADO",
                    sucursal_id  = sucursal_id,
                )
            except Exception as exc:
                logger.warning("GestionarNominaUC asiento IMSS: %s", exc)

        # ── 5. Auditar pago via HRRuleEngine (hr_auditoria_log) ──────────────
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

        # ── 6. Publicar NOMINA_PAGADA ────────────────────────────────────────
        if self._bus:
            try:
                from core.events.event_bus import NOMINA_PAGADA
                self._bus.publish(
                    NOMINA_PAGADA,
                    {
                        "empleado_id":     solicitud.empleado_id,
                        "nombre":          nombre,
                        "neto":            neto_deducido,
                        "periodo_inicio":  solicitud.fecha_inicio,
                        "periodo_fin":     solicitud.fecha_fin,
                        "sucursal_id":     sucursal_id,
                    },
                    async_=True,
                )
            except Exception as exc:
                logger.warning("GestionarNominaUC publish: %s", exc)

        return ResultadoNomina(
            ok              = True,
            empleado_id     = solicitud.empleado_id,
            nombre_completo = nombre,
            neto_a_pagar    = datos.get("neto_a_pagar", 0.0),
            neto_deducido   = neto_deducido,
            imss_obrero     = datos.get("imss_obrero", 0.0),
            imss_patronal   = imss_patronal,
            isr_mensual     = datos.get("isr_mensual", 0.0),
            asiento_id      = asiento_id,
            asiento_imss_id = asiento_imss_id,
        )
