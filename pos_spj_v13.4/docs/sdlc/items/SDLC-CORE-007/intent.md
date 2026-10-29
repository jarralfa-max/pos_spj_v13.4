# SDLC-CORE-007 — El segmento de integración de CI no colecta: las pruebas de integración nunca corren

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`tests/integration/test_sqlite_sales_repository_uuid.py` importa `infrastructure.persistence.sqlite_sales_repository`, módulo que no existe; pytest aborta la colección y el paso 'Validate integration tests' de `ci-segmented.yml` falla sin ejecutar ninguna prueba. Así ningún ítem T0 puede pasar la etapa Test con evidencia de integración.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `docs/sdlc/baseline/2026-10-28.md` — `python -m pytest tests/integration -q`: `1 error during collection`, `5 skipped, 1 error` *(verificado directamente en el triage)*
- `tests/integration/test_sqlite_sales_repository_uuid.py:17` — `ModuleNotFoundError: No module named 'infrastructure'` *(verificado directamente en el triage)*
- Archivo introducido en `9a405ff7` (FASE 7.18 ventas) — `git log` *(verificado directamente en el triage)*
- Corrida con `--continue-on-collection-errors` (sólo medición): ver resultado en la línea base

## Impacto
Bloquea la etapa Test de todo el SDLC; regresiones de integración pasan inadvertidas.

## Objetivo
- `python -m pytest tests/integration -q` colecta sin errores.
- Las fallas reales que aparezcan al colectar se registran como ítems aparte, no se silencian.

## Alcance
- **Incluye:** El archivo de prueba roto (migrarlo al módulo real o retirarlo con evidencia).
- **No incluye:** Arreglar las fallas de integración que se revelen (ítems nuevos).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria del proyecto: `tests/unit` y `tests/architecture` sueltos traen fallas preexistentes; se usaba una lista curada.

## Preguntas abiertas
- ¿Se mantiene la lista curada como gate o se vuelve a exigir el segmento completo verde?
