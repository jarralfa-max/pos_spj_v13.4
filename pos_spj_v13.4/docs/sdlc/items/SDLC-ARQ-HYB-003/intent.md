# SDLC-ARQ-HYB-003 — Central sin artefactos de despliegue, respaldo de PostgreSQL ni salud real

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §2 · §10 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R2.F / R10.5 Respaldo, recuperación y supervisión central, estado `parcial`)
- **Estado:** borrador
- **Depende de:** SDLC-SYNC-001

## Problema
El docstring del central menciona Caddy/TLS, pero no hay Caddyfile, unidad systemd ni Docker en el repo. No hay script de `pg_dump`/restauración (sólo documentado como 'Slice 11'), ni métricas, y `/health` responde 'ok' sin consultar la base.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/api/central_app.py:10-14,155-157`
- `docs/architecture/hybrid_postgresql/12_slice3_postgresql_minimum.md:100`
- Pruebas: ninguna.

## Impacto
El central no puede desplegarse de forma reproducible ni recuperarse ante pérdida de la base.

## Objetivo
- Artefactos de despliegue versionados (proxy TLS, servicio) sin secretos.
- Respaldo y restauración de PostgreSQL con prueba en CI.
- `/health` verifica BD y versión de esquema.

## Alcance
- **Incluye:** Artefactos, scripts, prueba.
- **No incluye:** Elegir proveedor de hosting.

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
SDLC-SYNC-001.

## Preguntas abiertas
- Ninguna por ahora.
