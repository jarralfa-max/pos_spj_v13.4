# SDLC-ASSET-030 — Indicadores de Activos incompletos: 5 conteos, sin gráficas, MTBF/MTTR, salud ni candidatos a reemplazo, y nada expuesto a BI

- **Prioridad:** P3
- **Nivel de riesgo:** T2
- **Origen:** `docs/sdlc/inputs/activos.md` §58–§61, §91, §92 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-ASSET-016, SDLC-ASSET-024

## Problema
El tablero muestra 5 conteos por estado. Faltan valor de adquisición, mantenimientos vencidos, OT abiertas, costo de mantenimiento, gráficas, MTBF, MTTR, puntaje de salud explicable y candidatos a reemplazo. BI no recibe métricas de activos.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/application/assets/queries/asset_read_services.py:88-96`
- `frontend/desktop/modules/assets/pages/overview_page.py:91-105`
- `frontend/desktop/components/chart_view.py` sin uso en el módulo

## Impacto
Sin información para decidir mantenimiento o reemplazo.

## Objetivo
- Los 6 KPIs principales de §91 calculados en backend, gráficas por ChartDTO, MTBF/MTTR, salud y reemplazo con su explicación.
- Métricas publicadas a BI.

## Alcance
- **Incluye:** Indicadores y exposición a BI.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T2: plan corto y pruebas afectadas.

## Trabajo previo relacionado
- Memoria BI-0..33 (páginas BI)

## Preguntas abiertas
- Ninguna por ahora.
