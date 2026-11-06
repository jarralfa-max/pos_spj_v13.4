# SDLC-PAY-005 — Arqueo y cortes X/Z sólo cuentan efectivo: no desglosan tarjeta, Mercado Pago, transferencia, vales ni crédito

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 9.1 · 9.2 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 1.2 «Corte X/Z con desglose…» (`ausente`))
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-PAY-003

## Problema
Los cortes X y Z leen sólo el libro de efectivo. `payment_allocations` se escribe en cada venta pero nadie la lee, así que el corte no muestra cobros por medio, pagos mixtos, pagos pendientes, reembolsos electrónicos ni referencias. El cajero y el gerente no pueden cuadrar lo cobrado con terminal contra el reporte del procesador.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/cash_register/x_cut_use_cases.py:53-69`; `z_cut_use_cases.py:70` reutiliza `_snapshot`
- `backend/infrastructure/desktop/cash_register_factory.py:1007-1035,1127-1153` — documentos impresos sólo efectivo
- `backend/infrastructure/db/repositories/cash_register/repositories.py:269` — única escritura de `payment_allocations`, sin lector
- Prueba: `tests/unit/cash_register/test_cash_x_cut_query_service.py`, `test_cash_z_cut_query_service.py` (sólo efectivo)

## Impacto
Cajero y gerente: cierre de turno incompleto; diferencias con el procesador invisibles.

## Objetivo
- El corte X/Z separa efectivo, tarjeta, Mercado Pago, transferencia, vales, crédito y otros, con número de transacciones y total bruto por medio.
- Muestra reembolsos electrónicos y, cuando existan, pagos pendientes y comisiones conocidas separadas de las estimadas (sin restar comisión al bruto).
- Se preservan formato, impresión y trazabilidad actuales; pruebas con venta mixta.

## Alcance
- **Incluye:** Consultas de corte, documento impreso, pruebas.
- **No incluye:** Estados de pago pendiente (PAY-008); comisiones (PAY-018).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria CASH-26 / CASH-AUD (corte y documentos de Caja).

## Preguntas abiertas
- Ninguna por ahora.
