# SDLC-INST-003 — Carpeta de datos con permiso de modificación para todos los usuarios de Windows

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El instalador da `users-modify` a la carpeta de datos; los permisos sólo se aplican dentro de la app. Cualquier usuario de Windows que pueda editar el SQLite puede cambiar `usuarios` y `rol_permisos`. Que la BD esté en esa carpeta: **no verificado**.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `installer/windows/spj_setup.iss:119`
- `backend/shared/app_paths.py:208-213`

## Impacto
Elevación de permisos dentro de la app por manipulación del archivo.

## Objetivo
- ACL mínima necesaria documentada y aplicada, o integridad de tablas de seguridad verificable.

## Alcance
- **Incluye:** Instalador y rutas.
- **No incluye:** Job del updater (INST-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
INST-0.

## Preguntas abiertas
- ¿Varios usuarios de Windows por PC de sucursal, o uno solo?
