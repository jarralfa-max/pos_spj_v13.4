# SDLC-PAY-006 — Reembolsos y anulaciones a medio electrónico se registran como ejecutados sin que nadie los haga

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 15 · Fase 9 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 1.2 «Reembolso a medio electrónico» (`defectuoso`))
- **Estado:** borrador
- **Depende de:** SDLC-PAY-003

## Problema
Al devolver o cancelar una venta pagada con Mercado Pago o tarjeta, Caja crea un `CashRefundExecution` con método `ORIGINAL_PAYMENT_METHOD` como ya ejecutado y Finanzas abona la cuenta puente, pero el sistema sólo muestra un texto para que el cajero reembolse a mano en el panel del proveedor. No hay estado solicitado/confirmado, ni referencia del reembolso, ni registro cuando el reverso de venta se compone sin servicio de reembolso.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/cash_register/refund_integration.py:130-155` (*verificado directamente*)
- `backend/application/sales/use_cases/payment_void_use_cases.py:58-60` — sólo instrucción de texto
- `backend/application/sales/use_cases/lifecycle_use_cases.py:119,139` — cancelación igual
- `frontend/desktop/modules/sales_pos/composition.py:430-432` — reverso sin `cash_refund_service`; `return_use_cases.py:258-263` sólo efectivo
- `backend/domain/sales/services/refund_service.py:59-100` — reparte por método y pierde la referencia
- Prueba: `tests/e2e/test_cash_sale_refund_flow.py:57` (tarjeta); MP: ninguna

## Impacto
Finanzas y clientes: reembolsos contabilizados que nunca ocurrieron, o hechos dos veces a mano; sin rastro para un reclamo.

## Objetivo
- Un reembolso electrónico nace `SOLICITADO` y sólo pasa a `CONFIRMADO` con evidencia (referencia del reembolso) capturada por alguien autorizado, o `RECHAZADO`.
- El asiento se emite al confirmar, no al solicitar.
- El reverso de venta deja registro de reembolso para la parte no efectivo.
- Pruebas: devolución parcial y reverso de venta MP; doble confirmación es idempotente.

## Alcance
- **Incluye:** Caja (ejecución de reembolso), Ventas (anulación, cancelación, reverso), Finanzas (momento del asiento), pruebas.
- **No incluye:** Reembolso automático vía API (PAY-020); contracargos (PAY-021).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria SALES-AUD V02/V03 (anulación de pagos en cobro).

## Preguntas abiertas
- Mientras no exista la API: ¿quién confirma el reembolso hecho en el panel de Mercado Pago y con qué permiso?
