# SDLC-ASSET-003 — Restos del legacy de Activos: pruebas y script que importan `core/` borrado y andamiaje muerto con float

- **Prioridad:** P3
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §1, §5, §109 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-ASSET-002

## Problema
Tres pruebas sueltas importan módulos borrados y fallan (20 fallas y 8 errores), pero ningún job de CI las corre, así que nadie lo nota. `scripts/weekly_maintenance.py` importa `core.database`, que no existe. Sigue presente una cadena de comandos, casos de uso y servicio de consulta de activos sin llamadores que devuelve `not_implemented` y maneja dinero en `float`, exportada desde `backend/application/queries/__init__.py`. Varios comentarios y docstrings citan archivos borrados como si estuvieran vivos.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `tests/test_asset_service_ui_reads.py:35`, `tests/test_fase3_depreciacion.py:60`, `tests/test_fase1_uiux_module_guards.py:11` — importan `core/`/`modulos/` (corrida del subagente A: 20 failed, 8 errors)
- `scripts/weekly_maintenance.py:1` — `core.database`
- `backend/application/commands/asset_commands.py:17,45` — `float`
- `backend/application/use_cases/create_asset_use_case.py`, `schedule_maintenance_use_case.py:9`, `complete_maintenance_use_case.py:9` — `DelegatingUseCase` sin handler (`base_use_case.py:35-38`)
- `backend/application/queries/asset_query_service.py:8`, reexportado en `backend/application/queries/__init__.py:17,37`; fijado por `tests/integration/test_phase0_phase1_scaffolding.py:67`
- `backend/domain/assets/entities/asset_capitalization_proposal.py:15`, `asset_disposal.py:5` — citan `capital_and_asset_use_cases.py` inexistente
- `backend/application/sales/session_authorization.py:6` (y loyalty, orders_delivery) — citan `core/app_container.py`

## Impacto
Deuda: confunde a quien busque dónde vive la lógica de activos y oculta pruebas rotas.

## Objetivo
- Ninguna prueba ni script importa `core/` o `modulos/`.
- El andamiaje de activos sin llamadores se elimina (o se reemplaza por los casos de uso reales cuando existan), sin `float` monetario.
- Comentarios y docstrings apuntan a archivos existentes.

## Alcance
- **Incluye:** Los archivos listados.
- **No incluye:** Las tablas legacy (SDLC-ASSET-004). Los cascarones de otros módulos (SDLC-CORE-005).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- SDLC-CORE-005 (cascarones de ventas, delivery, RRHH, BI; no lista estos archivos)
- ASSET-23 (reporte de disposición legacy, sin borrar)

## Preguntas abiertas
- `tests/test_fase3_depreciacion.py` describe la lógica legacy prohibida (capitalizar por UPDATE, depreciación local): ¿se borra, o se rescatan los casos que describan comportamiento deseado como pruebas de Finanzas? borrar
