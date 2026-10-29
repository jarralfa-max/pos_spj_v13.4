# SDLC-ORD-003 — Tres pipelines de pedidos paralelos sin fuente de verdad decidida

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
WhatsApp escribe `ventas` (pendiente_wa), `cotizaciones` y `delivery_orders`; el escritorio usa `customer_orders` y `quotes`. La docstring de `whatsapp_schema.py` reconoce 'tres pipelines paralelos' sin decisión.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/db/schema/whatsapp_schema.py:38-47`
- `backend/infrastructure/db/schema/orders_delivery_schema.py:19-27`
- `whatsapp_service/router/delivery_router.py:204`

## Impacto
Pedidos que una pantalla ve y otra no.

## Objetivo
- Decisión registrada de pipeline autoritativo y plan de corte.

## Alcance
- **Incluye:** Decisión + plan.
- **No incluye:** Implementación del corte (ítems posteriores).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
ORD-30, WA-22.

## Preguntas abiertas
- ¿Cuál pipeline de pedidos es el autoritativo?
