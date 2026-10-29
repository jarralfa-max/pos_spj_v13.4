# SDLC-INV-003 — Cada flujo pone stock en una 'ubicación' distinta (sucursal, almacén o técnica)

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** SDLC-INV-001

## Problema
Compras usa el id de sucursal como `to_location_id` (y como `warehouse_id` si falta); ajustes, inspección y cuarentena caen al id de almacén; faltantes de venta usan la sucursal; transferencias, producción y mermas usan ubicaciones técnicas reales. La verificación de stock negativo es por cubeta ubicación/lote/estado, así que bajas y ajustes fallan contra cubetas vacías o crean cubetas fantasma. Incluye el hallazgo de la auditoría 2026-10-26: la recepción de transferencia cae a almacén `PURCHASE` y Producción sólo ve `PRODUCTION`.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/event_handlers/inventory/purchase_stock_entry_bridge.py:52-57`; `backend/application/procurement/integrations/downstream_translators.py:84-97`
- `backend/application/inventory/use_cases/adjustment_use_cases.py:87`, `inspect_receipt.py:81`, `quarantine_use_cases.py:76,195`
- `backend/infrastructure/integrations/sales_inventory_client.py:462,696`
- `backend/application/inventory/queries/stock_location_resolver.py:1-16,46-71`; `backend/infrastructure/persistence/loss_inventory_repository.py:54-59`; `backend/application/inventory/services/inventory_projection_service.py:107-123`
- `backend/application/inventory/use_cases/provision_default_warehouse.py:4-12` reconoce que rompe CLAUDE.md
- `backend/infrastructure/integrations/transfers_inventory_gateway.py:84` — `resolve_branch_warehouse(..., "PURCHASE")` *(verificado directamente en el triage)*

## Impacto
Stock 'existente' que no puede venderse, bajarse ni transformarse; saldos partidos.

## Objetivo
- Una sola regla de resolución de ubicación usada por todos los flujos que mueven stock.
- Migración que reubica saldos existentes en una copia de la BD real sin cambiar totales por producto/almacén.
- Pruebas por flujo (compra, ajuste, cuarentena, venta, transferencia, producción, merma).

## Alcance
- **Incluye:** Resolver único y su adopción.
- **No incluye:** Orquestación recepción→despiece (PROC-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Auditoría integral 2026-10-26 §3 (almacén por defecto); memoria INV-27.

## Preguntas abiertas
- Probablemente requiera dividirse en Design (resolver + migración por flujo).
