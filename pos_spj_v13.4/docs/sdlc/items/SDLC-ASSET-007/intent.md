# SDLC-ASSET-007 — Activos no tiene resolvedor de alcance: sin sucursal en la sesión, el tablero suma toda la empresa

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §83 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-ARQ-PERM-003

## Problema
§83 pide alcances OWN, ASSIGNED, BRANCH, REGION, COMPANY y ALL con un resolvedor. Solo existe el vocabulario y un Protocol. Los servicios de consulta no reciben alcance ni permiso; el presentador pasa la sucursal de la sesión tal cual y, si no hay, el tablero hace `list_all()`. El repo ya tiene un resolvedor común de alcance por sucursal que Activos no usa.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/application/assets/scopes.py:21-49` — enum, value object y `Protocol` sin implementación
- `backend/application/assets/queries/asset_read_services.py:46-140`, `:89` — sin alcance; `list_all()` sin sucursal
- `frontend/desktop/modules/assets/assets_presenter.py:64,71,84` — sucursal de sesión directa
- `backend/application/security/branch_scope_query_service.py` — resolvedor común no usado
- `tests/architecture/test_asset_scopes_are_enforced.py:9-24` — no prueba aplicación

## Impacto
Cuando haya datos, un usuario de sucursal podría ver activos de toda la empresa.

## Objetivo
- Un único resolvedor de alcance para Activos construido sobre el común (sin un tercer modelo).
- Todo servicio de consulta exige alcance; sin alcance, nada (fallo cerrado).
- Pruebas por nivel de alcance.

## Alcance
- **Incluye:** Resolvedor, aplicación en consultas, pruebas.
- **No incluye:** Alcance ASSIGNED de técnicos sobre OT (llega con SDLC-ASSET-016).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- Memoria «Alcance por sucursal: dos reglas incompatibles» (Inventario/Mermas/Transferencias, cerrado 2026-09-17)
- SDLC-ARQ-PERM-003 (dos resolvedores discrepan)

## Preguntas abiertas
- Ninguna por ahora.
