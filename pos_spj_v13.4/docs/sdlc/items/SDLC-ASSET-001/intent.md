# SDLC-ASSET-001 — Módulo Activos visible en el menú sin persistencia: 31 de 36 rutas en construcción

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Activos está en la barra lateral con `query_services={}`; 31 rutas caen a 'sección en construcción' y las otras 5 no tienen datos.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/modules/assets/shell_registration.py:70-87`
- `assets_workspace.py:117-138`
- `frontend/desktop/shell/sidebar/migrated_modules_navigation.py:211-220`

## Impacto
Usuario ve un módulo que no funciona.

## Objetivo
- Ocultar hasta tener persistencia, o construir la capa de escritura (proyecto aparte).

## Alcance
- **Incluye:** Decisión de visibilidad.
- **No incluye:** Construcción de la capa de escritura.

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T2: plan corto y pruebas afectadas.

## Trabajo previo relacionado
Memoria ASSET-0..24 (capa de escritura nunca construida).

## Preguntas abiertas
- ¿Ocultar Activos del menú hasta construirlo?
