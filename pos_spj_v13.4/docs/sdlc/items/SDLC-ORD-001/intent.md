# SDLC-ORD-001 — Dinero de Pedidos: efecto de caja tragado y cobros/liquidaciones de repartidor sin asiento

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
En la ruta Pedidos/Delivery (`require_cash_shift=False`) una falla al registrar el efecto de caja se guarda en `cash_effects_error`, campo que nadie lee: la venta se completa y su efectivo no queda en ningún lado. Además, los cobros de repartidor y las liquidaciones (`CASH_COLLECTION_RECORDED`, `DRIVER_SETTLEMENT_*`) no tienen handler en Finanzas y su outbox no se drena: el efectivo en manos de repartidores es invisible para el mayor.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/sales/use_cases/checkout_use_cases.py:172-185`; llamado desde `backend/infrastructure/integrations/orders_delivery_sales_client.py:136-137`
- Grep: ningún lector de `cash_effects_error` en backend/frontend (reportado por el barrido)
- `backend/application/orders_delivery/use_cases/cash_collection_use_cases.py:72-102`, `settlement_use_cases.py:27-67`
- `backend/domain/orders_delivery/events.py:101-104`; `backend/application/orders_delivery/use_cases/sales_finance_use_cases.py:36-41` lo documenta como abierto
- Posible doble conteo con `driver_cash_collections`: **no verificado**

## Impacto
Efectivo de entregas a domicilio sin rastro contable; riesgo de faltantes no detectables.

## Objetivo
- Una falla del efecto de caja en Pedidos aborta o queda en una cola visible y reintentable, nunca tragada.
- Cobro y liquidación de repartidor producen asientos balanceados (caja en tránsito/repartidor ↔ caja).
- Sin doble conteo entre la venta y el cobro del repartidor (prueba).

## Alcance
- **Incluye:** Ruta de cobro de Pedidos, handlers de Finanzas para cobro/liquidación, despacho de su outbox.
- **No incluye:** Resto de outbox de CRM/clientes (SDLC-ORD-002).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
`docs/refactor/ORD-30_validacion_final.md`; memoria: outbox de orders_delivery sin drenar.

## Preguntas abiertas
- ¿Cuenta contable para 'efectivo en poder de repartidores'?
