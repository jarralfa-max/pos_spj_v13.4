# SDLC-ASSET-024 — Dos identidades de activo: el `Asset` de Activos y el `FixedAsset` de Finanzas no se enlazan, y hay dos pantallas de activos

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/activos.md` §2, §7, §32–§35, §115 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** SDLC-FIN-002, SDLC-ASSET-010

## Problema
§115 pide un solo registro de activos y una sola identidad. Hoy Finanzas → «Activos fijos» es el único inventario de activos con datos (alta, suspensión, reactivación y baja) y el módulo Activos tiene su propio agregado sin datos. El enlace `financial_asset_id` no se guarda en ningún lado y no existe la proyección financiera de solo lectura que §34 pide mostrar en Activos.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/domain/assets/entities/asset.py:63` — `financial_asset_id` sin persistencia
- `frontend/desktop/modules/finance/finance_view.py:76-77` — «Activos fijos» y «Depreciación» en Finanzas (*verificado directamente*)
- `backend/application/queries/finance/fixed_asset_query_service.py:12-48`
- No existe `AssetFinancialProjectionQueryService` (solo lo cita `tests/architecture/test_assets_do_not_own_financial_depreciation.py:6,44`)

## Impacto
Dos lugares para lo mismo; riesgo de altas duplicadas y cifras que no coinciden.

## Objetivo
- Regla única de qué pantalla da de alta un activo y cómo se enlaza con el auxiliar de Finanzas.
- Proyección de solo lectura (costo, depreciación acumulada, valor en libros, vida remanente) leída de Finanzas en Activos.
- Pruebas.

## Alcance
- **Incluye:** Enlace de identidades, proyección financiera, decisión de pantallas.
- **No incluye:** Bajas (SDLC-ASSET-026).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento, revisión independiente obligatoria, migraciones probadas sobre una copia de la BD en el directorio temporal.

## Trabajo previo relacionado
- SDLC-UI-017 (pregunta abierta: ¿consolidar Finanzas → Activos fijos con el módulo Activos?)
- SDLC-ASSET-001

## Preguntas abiertas
- Igual que en SDLC-UI-017: ¿el alta de un activo nace en Activos (y Finanzas solo lo reconoce) o se mantiene el alta en Finanzas y Activos la toma de ahí?
