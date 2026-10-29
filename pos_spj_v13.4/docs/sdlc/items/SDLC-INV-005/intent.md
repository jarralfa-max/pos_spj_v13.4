# SDLC-INV-005 — Almacén de stock legacy (inventory_stock) se sigue creando y BI lo lee

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Una BD nueva todavía crea `inventory_stock` y tablas legacy junto a `inventory_ledger`/`inventory_balances`; servicio, repositorio y casos de uso legacy están huérfanos; BI cae a `inventory_stock` cuando la bandera está apagada.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `migrations/standalone/098_canonical_inventory.py:18`; `108_sync_inventory_stock.py:46`
- `backend/infrastructure/db/repositories/inventory_repository.py:1,52,154`
- `backend/application/services/inventory_application_service.py:31`
- `backend/application/use_cases/{adjust_inventory,register_inventory_movement,get_inventory_stock}_use_case.py`
- `backend/application/analytics/queries/bi_inventory_query_service.py:34-41`

## Impacto
Viola born-clean/fuente única.

## Objetivo
- BD nueva sin tablas legacy de stock; BI sólo canónico; código huérfano eliminado.

## Alcance
- **Incluye:** Esquema, BI, código huérfano.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria INV gap #1 (productos.existencia) cerrado 2026-09-03.

## Preguntas abiertas
- Ninguna por ahora.
