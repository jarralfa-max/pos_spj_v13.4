# SDLC-ARQ-PERM-005 — Permisos sin dimensión de recurso ni condiciones; el ámbito va codificado en el nombre

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/requisitos-arquitectura.md` §3 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-brechas.md`, requisito R3.5 Módulo/acción/recurso/ámbito/condiciones, estado `parcial`)
- **Estado:** borrador
- **Depende de:** SDLC-ARQ-PERM-001

## Problema
El permiso es una cadena `MODULO.accion`; el ámbito se codifica en el nombre (`X.ver.todas_sucursales`) o sale de asignaciones, y las condiciones viven en tablas por módulo (`cash_operation_limits`, `user_purchase_limits`). El documento pide distinguir módulo, acción, recurso, ámbito y condiciones. El catálogo vive sólo en código.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea viene del barrido por sección con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/security/permissions/codes.py:51-104`
- `backend/application/security/permission_catalog.py`

## Impacto
Deuda estructural: cada módulo reinventa límites y alcance.

## Objetivo
- Modelo de permiso con recurso y condiciones expresables, compatible con los códigos actuales.
- Catálogo consultable (tabla o contrato) para la UI de administración.

## Alcance
- **Incluye:** Diseño + migración compatible.
- **No incluye:** Reescribir todos los módulos en un PR (se divide en Design).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; no borrar ni restablecer roles, permisos ni asignaciones existentes (docs/sdlc/inputs/requisitos-arquitectura.md §3); presupuesto $0; Windows 10/11. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
