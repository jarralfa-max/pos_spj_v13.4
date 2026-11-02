# SDLC-PROC-002 — Disponibilidad para producción suma piezas como kg y con REAL

- **Prioridad:** P0 (subida de P1 el 2026-10-31 por `inputs/correcciones.md` C-04)
- **Nivel de riesgo:** T0 (subido de T1: la corrección define unidad base/inventariable por producto, área `inventory`)
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`); ampliado con `inputs/correcciones.md` C-04 (oleada 1)
- **Estado:** borrador
- **Depende de:** SDLC-CORE-012

## Problema
`lots` suma `inventory_balances.quantity` con `CAST(... AS REAL)` y lo presenta como `available_kg`: piezas no equivalen a kg y REAL pierde precisión Decimal. El ledger de transferencias sí distingue cantidad y peso observados.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/meat_processing/queries/direct_transformation_query_service.py:132` *(verificado directamente en el triage)*
- Auditoría 2026-10-26 §3 P0 #4

**Re-verificado el 2026-10-31 sobre `4639fed2` (correcciones C-04):**
- `backend/application/meat_processing/queries/direct_transformation_query_service.py:132` — `SUM(CAST(b.quantity AS REAL) - CAST(b.reserved_quantity AS REAL))`; `:150` lo convierte a `Decimal(str(...))` ya con el error de REAL; `:47` el DTO lo llama `available_kg` sin mirar la unidad del producto.
- `direct_transformation_query_service.py:146-148` — un `sqlite3.OperationalError` se registra y devuelve lista vacía: la pantalla muestra «sin lotes» en vez de un error.

## Impacto
Despieces calculados sobre kg incorrectos.

## Objetivo
- Unidad base, unidad inventariable, piezas y peso neto definidos por producto.
- Disponibilidad en la unidad base del producto con Decimal y conversión explícita (sin `CAST AS REAL`).
- Sin peso neto para un perfil en kg, el despiece automático se bloquea y pide pesaje.
- Un error de consulta se distingue de «no hay lotes».

## Alcance
- **Incluye:** Consulta de disponibilidad y la definición de unidades que necesita.
- **No incluye:** Otros REAL (SDLC-CORE-006).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Auditoría 2026-10-26; `inputs/correcciones.md` C-04; SDLC-INV-002 (signo y suma del peso capturado); memoria «ERP search infrastructure» (`SEARCH_FAILED` vs `NO_RESULTS`, mismo patrón de error tragado).

## Preguntas abiertas
- ¿Dónde se define hoy la unidad inventariable de un producto de peso variable (perfil de producto, maestro cárnico) y cuál manda si discrepan? Se medirá en Design; si no hay fuente única, se pregunta. · bloquea `/sdlc-design SDLC-PROC-002` solo si no hay fuente única
