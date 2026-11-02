# SDLC-ASSET-002 — Las guardias de arquitectura de Activos pasan en vacío y no vigilan el andamiaje ni el esquema legacy

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/activos.md` §110 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Las 21 guardias de §110 existen y están en verde, pero varias no comprueban nada: escanean una raíz de infraestructura y un archivo de esquema que no existen y lo toleran en silencio; la de Decimal hace `return` si falta el esquema; la de rutas busca 3 cadenas; la de scopes solo revisa un enum; la de Design System es una tautología. La lista de andamiaje huérfano tiene un prefijo de ruta equivocado y nadie la usa. Cuando se construya la persistencia (SDLC-ASSET-010), las guardias no van a morder.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `tests/architecture/assets_guardrails.py:29,33` — `ASSET_INFRA_REPO_ROOT` y `ASSET_SCHEMA_FILE` inexistentes; `:62-64` los trata en silencio
- `tests/architecture/assets_guardrails.py:50-51` — `LEGACY_ASSET_FILES` vacío; `:55-59` `ORPHANED_ASSET_SCAFFOLDING` con prefijo `pos_spj_v13.4/` y sin uso, sin `schedule_maintenance_use_case.py` ni `complete_maintenance_use_case.py`
- `tests/architecture/test_assets_use_decimal.py:44-45` — `return` en verde sin esquema
- `tests/architecture/test_assets_use_uuidv7.py:34-35` — `pytest.skip` (única omisión de la corrida; *verificado directamente*)
- `tests/architecture/test_asset_routes_are_registered.py:9,19-24` — solo busca 3 cadenas
- `tests/architecture/test_asset_scopes_are_enforced.py:9-24` — solo enum e inmutabilidad
- `tests/architecture/test_assets_use_design_system.py:23-25` — tautología
- `tests/architecture/test_assets_use_decimal.py:26` — no escanea `backend/application/commands/asset_commands.py` (float en `:17,45`)

## Impacto
Desarrollo: falsa sensación de cumplimiento. Bloquea la arquitectura porque es la red que debe atrapar SQL en UI, float, `uuid4` y escrituras a Finanzas cuando se escriba la capa de persistencia.

## Objetivo
- Una guardia falla si su raíz esperada no existe cuando el código ya debería existir (o declara de forma explícita y visible que aún no aplica).
- Las guardias de rutas comprueban las 36 rutas y su permiso; la de scopes comprueba que los servicios de consulta reciben alcance.
- Las guardias cubren también el andamiaje fuera de las raíces EAM y las tablas legacy de activos.

## Alcance
- **Incluye:** `tests/architecture/assets_guardrails.py` y las 21 pruebas de §110.
- **No incluye:** Corregir lo que las guardias encuentren (va a SDLC-ASSET-003/004).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T2: plan corto y pruebas afectadas.

## Trabajo previo relacionado
- ASSET-1 (guardias de septiembre)
- SDLC-CORE-008/CORE-009 (otras guardias en rojo)

## Preguntas abiertas
- Ninguna por ahora.
