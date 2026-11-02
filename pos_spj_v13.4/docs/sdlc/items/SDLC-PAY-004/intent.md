# SDLC-PAY-004 — Cobros con procesador se asientan a la cuenta puente 1120 mientras tesorería y compras usan la 1115

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 10 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 1.3 «Asiento balanceado de venta con procesador» (`parcial`) y «CxC al procesador alineada con tesorería» (`defectuoso`))
- **Estado:** borrador
- **Depende de:** —

## Problema
Las ventas cobradas con Mercado Pago o tarjeta cargan la 1120 «Cuenta puente (partidas por identificar)». La cuenta de tesorería del procesador («Procesador de tarjetas», genérica) tiene como espejo la 1115, y las compras pagadas desde el saldo de MP abonan la 1115. Resultado: las entradas del procesador quedan en una cuenta y las salidas en otra; la conciliación contra la cuenta del procesador no encuentra ninguna venta y la 1115 tiende a saldo negativo. Con una segunda cuenta de procesador, el puente de compras se omite.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/event_handlers/finance/sale_completed_handler.py:112-114` — Debe `clearing_account_id` (*verificado directamente*)
- `backend/application/services/finance/finance_bootstrap.py:52-53,211-212,254` — 1115 procesadores, 1120 puente, tesorería espejo 1115, perfil SALE con puente 1120 (*verificado directamente*)
- `backend/application/event_handlers/finance/procurement_immediate_payment_bridge.py:57-61,110-111,137-161` — abona 1115 y exige una única cuenta activa
- `backend/application/event_handlers/finance/sale_returned_handler.py:44-45` — devoluciones abonan la 1120
- Prueba: `tests/integration/test_sales_checkout_settles_everything.py:347` sólo CARD; MP: ninguna

## Impacto
Finanzas: saldos del procesador incorrectos, conciliación imposible, estados financieros con partidas «por identificar» permanentes.

## Objetivo
- Cada cuenta cobradora (MP y adquirente de tarjeta) es una cuenta de tesorería `PAYMENT_PROCESSOR` con espejo propio.
- Ventas, devoluciones y compras con un procesador usan el mismo espejo, resuelto por método/cuenta y no por un perfil genérico.
- Migración de datos sobre copia con plan para saldos ya acumulados en la 1120.
- Pruebas de asiento balanceado para venta, devolución y compra con MP.

## Alcance
- **Incluye:** Perfil contable de ventas, resolución de cuenta de procesador, puente de compras, migración, pruebas.
- **No incluye:** Comisiones y liquidación (PAY-018).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria FIN-ERP / `docs/refactor/finance_refactor_execution_plan.md` (perfiles contables).

## Preguntas abiertas
- ¿Una cuenta de tesorería por cuenta cobradora MP y otra por adquirente de tarjeta, o una sola «procesadores»?
- ¿La venta MP carga directo la cuenta del procesador o la 1120 hasta la liquidación?
- ¿Cómo se reclasifica el saldo histórico de la 1120?
