# SDLC-ARQ-IDEM-001 — Doble clic en cobro registra dos pagos: el POS genera un operation_id nuevo por clic

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §12 · §10 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R12.1 / R10.3 Doble clic y reintentos → una sola operación, estado `defectuoso`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El presentador del POS crea un `operation_id` nuevo en cada llamada (`_new_op()`) para abrir venta, registrar pago e iniciar cobro, de modo que la deduplicación por operación de los casos de uso nunca se activa ante un doble clic o un reintento. `sale_payments` no tiene `operation_id` y `RecordSalePaymentUseCase` no detecta reintentos: un pago parcial puede duplicarse hasta el saldo pendiente.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/modules/sales_pos/sales_pos_presenter.py:128,135,412,417` (*verificado directamente*)
- `backend/infrastructure/db/schema/sales_schema.py:117-125` — `sale_payments` sin `operation_id` (*verificado directamente*)
- `backend/application/sales/use_cases/payment_use_cases.py:70-129`; tope por saldo en `backend/domain/sales/entities.py:421-439`
- `backend/application/sales/use_cases/cart_use_cases.py:53-56` (la dedup existe para crear venta, pero recibe un id nuevo cada vez)
- Pruebas: `tests/ui/test_operations_standard_dialogs.py::test_payment_retry_keeps_recorded_lines_and_accepts_once` (diálogo); doble envío al caso de uso: ninguna.

## Impacto
Cajero y Finanzas: pagos registrados dos veces (efectivo, tarjeta, transferencia) que descuadran el corte y el asiento. Frecuencia: cada doble clic o reintento tras lentitud.

## Objetivo
- El `operation_id` se genera una vez por intención del usuario (al abrir el diálogo o la acción) y se reutiliza en reintentos.
- `sale_payments` tiene `operation_id` único (migración) y el caso de uso devuelve el resultado original ante repetición.
- Prueba: dos llamadas con el mismo `operation_id` producen un solo pago, un solo efecto de caja y un solo asiento.

## Alcance
- **Incluye:** Presentador POS, esquema `sale_payments`, `RecordSalePaymentUseCase`, pruebas.
- **No incluye:** Replay de checkout y apertura de turno (SDLC-ARQ-IDEM-002, SHIFT-004).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-CORE-002 (operation_id derivados por concatenación) — misma familia; coordinar el formato de ids.

## Preguntas abiertas
- Ninguna por ahora.
