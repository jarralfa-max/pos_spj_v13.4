# SDLC-ASSET-006 — Los 83 permisos `ACTIVOS.*` no están sembrados en ningún rol y no existen los roles de §82: solo el dueño entra

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/activos.md` §71–§82 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Los permisos de Activos existen en el catálogo y se pueden otorgar, pero ninguna migración se los da a ningún rol. En la base real `rol_permisos` no tiene filas de ACTIVOS; el único que entra al módulo es `system_owner` por el comodín. Tampoco existen los roles sugeridos (visor, técnico, custodio, gerente de activos, auditor…). Otorgable no es otorgado.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/application/assets/permissions.py:24-128` — 83 códigos
- `backend/application/security/permission_catalog.py:61` — entran al catálogo; `:97-102` `_SEEDED_MODULES` sin ACTIVOS (*verificado directamente* que existe `_SEEDED_MODULES` en `:97`)
- `migrations/m000_base_schema.py:3188-3193` — siembra de módulos sin ACTIVOS
- `backend/security/permissions/principals.py:29-30` — comodín del dueño
- Consulta de solo lectura del subagente E sobre `data/spj_pos_database.db`: 0 filas ACTIVOS en `rol_permisos`, un único usuario `system_owner` (**no verificado** sobre copia)

## Impacto
Ningún gerente, técnico o auditor puede usar Activos cuando exista. Riesgo de que, al construirlo, se otorgue de golpe a roles amplios sin decisión.

## Objetivo
- Matriz rol × permiso de Activos aprobada por el responsable y sembrada por migración.
- Los roles de §82 que se aprueben existen como roles de datos (no se autoriza por nombre de rol).
- Prueba: un usuario de cada rol ve y puede exactamente lo de la matriz.

## Alcance
- **Incluye:** Migración de siembra, roles, pruebas.
- **No incluye:** Alcance por sucursal (SDLC-ASSET-007).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento, revisión independiente obligatoria, migraciones probadas sobre una copia de la BD en el directorio temporal.

## Trabajo previo relacionado
- Memoria Precios: migraciones 206/260 (siembra congelada de `system_owner`; todo módulo nuevo queda fuera en silencio)
- SDLC-ARQ-PERM-004 (el nombre del rol concede privilegios)

## Preguntas abiertas
- ¿Qué roles existentes (gerente, cajero, administrador…) reciben qué permisos de Activos, y cuáles de los roles de §82 se crean?
