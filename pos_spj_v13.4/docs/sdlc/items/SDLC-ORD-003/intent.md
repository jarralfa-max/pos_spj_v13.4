# SDLC-ORD-003 — Tres pipelines de pedidos paralelos sin fuente de verdad decidida

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** —

## Problema
WhatsApp escribe `ventas` (pendiente_wa), `cotizaciones` y `delivery_orders`; el escritorio usa `customer_orders` y `quotes`. La docstring de `whatsapp_schema.py` reconoce 'tres pipelines paralelos' sin decisión.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/db/schema/whatsapp_schema.py:38-47`
- `backend/infrastructure/db/schema/orders_delivery_schema.py:19-27`
- `whatsapp_service/router/delivery_router.py:204`
- **Ampliado 2026-10-31** (`/sdlc-plan` Modo B sobre `docs/audits/DELIVERY_REFACTOR_AUDIT.md` §Fuentes duplicadas de verdad), *verificado directamente* sobre `ed026f7b`: el expediente del cliente lee la tabla legacy. `backend/application/customers/queries/customer_delivery_summary_query.py:67-77` consulta `delivery_orders WHERE cliente_id=?`, y lo consume `customer_360_query_service.py:72,211`. Los pedidos capturados en escritorio viven en `customer_orders`, así que el expediente no los muestra. `delivery_orders` sigue creándose en `migrations/m000_base_schema.py:1154` y solo la escriben el microservicio (`whatsapp_service/erp/adjustment_approval.py:85-119`) y el caso de uso muerto `backend/application/use_cases/settle_delivery_driver_use_case.py:135` (SDLC-CORE-005).
- Los demás duplicados de la auditoría (`ventas.estado`/`ventas.total` escritos por `DeliveryRepository`/`OrderTotalService`, `historial_cambios` JSON) desaparecieron con el legacy (`a35b8bab`). En el escritorio solo queda la proyección por `backend/infrastructure/integrations/orders_delivery_sales_client.py`. Los `INSERT/UPDATE ventas` restantes están en `whatsapp_service/erp/bridge.py:475-1039` (SDLC-WA-003/WA-007).

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
ORD-30, WA-22; `docs/audits/DELIVERY_REFACTOR_AUDIT.md` (§Fuentes duplicadas de verdad); CRM-21 (puente `clientes.id`/`customers.id`); SDLC-CRM-003.

## Preguntas abiertas
- ¿Cuál pipeline de pedidos es el autoritativo? El que este mas avanzado 
