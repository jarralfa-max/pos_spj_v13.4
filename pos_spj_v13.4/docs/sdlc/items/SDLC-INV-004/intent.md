# SDLC-INV-004 — Cableado muerto de inventario (cutover canónico, puentes huérfanos, wire_logistics)

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`CanonicalInventoryCutover.wire()` nunca se llama aunque la migración 134 persiste la bandera en ON; los puentes de venta, producción, devolución de cliente y ejecución de producción quedan huérfanos; `ProductionCompletedLossHandler` se construye y no se suscribe; `wire_logistics` nunca se llama. Cablear el cutover tal como está postearía `PURCHASE_RECEIPT` dos veces.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/bootstrap/wiring/event_wiring.py:180-197`
- `backend/application/inventory/cutover/canonical_cutover.py:35-42,74-90`
- `backend/application/event_handlers/inventory/sale_items_bridge.py:12`, `production_items_bridge.py:80,85`, `production_execution_handler.py:21`
- `backend/application/logistics/wiring.py:7-28`

## Impacto
Código que confunde y es peligroso de reactivar.

## Objetivo
- Cada pieza se cablea con prueba o se elimina; la bandera persistida refleja la realidad.

## Alcance
- **Incluye:** Cableado de inventario.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria Compras: 'cutover flag ON pero .wire() nunca se llama'.

## Preguntas abiertas
- Ninguna por ahora.
