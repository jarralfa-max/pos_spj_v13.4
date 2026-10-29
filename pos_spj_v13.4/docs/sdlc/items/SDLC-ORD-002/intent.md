# SDLC-ORD-002 — Outbox de Pedidos, CRM, clientes, cotizaciones, tarjetas, sorteos y privacidad nunca se drenan

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`dispatch_orders_delivery_outbox` no tiene llamador y no está en el cableado ni en las tareas periódicas; `crm_outbox`, `customer_outbox`, `quote_outbox`, `loyalty_cards_outbox`, `sweepstakes_outbox`, `customer_service_outbox` y `customer_privacy_outbox` no tienen despachador (sólo los lee la replicación). Sus eventos nunca llegan a suscriptores locales.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/orders_delivery/integrations/orders_delivery_outbox_dispatcher.py:32`
- `backend/bootstrap/wiring/event_wiring.py:62-127`
- `backend/infrastructure/sync/replication_sources.py`

## Impacto
Integraciones entre contextos que aparentan existir y no corren.

## Objetivo
- Cada outbox con consumidores locales se drena periódicamente; los que no tienen consumidor se documentan como sólo-replicación.

## Alcance
- **Incluye:** Despachadores y tarea periódica.
- **No incluye:** Dinero de Pedidos (ORD-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
Memoria corte del shell.

## Preguntas abiertas
- Ninguna por ahora.
