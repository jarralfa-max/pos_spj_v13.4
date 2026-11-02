# SDLC-PAY-018 — Finanzas no registra comisión del procesador, IVA de la comisión ni depósito neto; un depósito puede duplicar el ingreso

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 10 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 10 «Comisión, IVA de comisión, depósito neto vs bruto» (`ausente`) y «Depósito no duplica ingreso» (`defectuoso`))
- **Estado:** borrador
- **Depende de:** SDLC-PAY-004

## Problema
No hay asiento para la comisión del procesador ni su IVA, ni para el depósito neto que liquida la cuenta del procesador. La cuenta de comisiones de MP sólo existe en la tabla legacy `plan_cuentas`. El movimiento de tesorería acepta cualquier contrapartida, incluida la cuenta de ingresos, así que registrar el depósito puede duplicar el ingreso.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/event_handlers/finance/sale_completed_handler.py:210,235` — `direct_cost='0.00'` fijo
- `migrations/standalone/059_plan_cuentas.py:77` — 6108 sólo en legacy; códigos chocan con el bootstrap
- `backend/application/use_cases/finance/register_treasury_movement_use_case.py:52-54,92-99`
- Prueba: ninguna

## Impacto
Estados financieros sin gastos financieros reales; ingreso inflado si se asienta el depósito contra ventas.

## Objetivo
- Liquidación del procesador: Debe banco (neto) + gasto comisión + IVA acreditable; Haber cuenta del procesador (bruto), balanceado.
- El depósito nunca usa cuentas de ingreso como contrapartida.
- Comisiones conocidas vs estimadas separadas; pruebas de asiento.

## Alcance
- **Incluye:** Caso de uso de liquidación, cuentas, validación de contrapartida, pruebas.
- **No incluye:** Importación y conciliación de reportes (PAY-019).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria FIN-AUD / FIN-ERP.

## Preguntas abiertas
- ¿La comisión e IVA se toman del reporte de liquidación de MP o de una tarifa configurada? ¿Qué cuentas?
