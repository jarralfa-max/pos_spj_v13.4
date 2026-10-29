# SDLC-BI-001 — BI ignora el alcance por sucursal y usa un verificador de permisos que permite todo

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Las rutas de BI reciben `branch_id` y todos los builders lo descartan; los presenters consultan con `DashboardFilters()` vacío (todas las sucursales, mes actual). `BiDashboardService` usa por defecto un verificador que permite todo y ningún presenter pasa uno. Cualquiera con `INTELIGENCIA_BI.ver` ve cifras de toda la empresa, sin filtro de sucursal ni fecha.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `frontend/desktop/modules/business_intelligence/business_intelligence_routes.py:98-100,108-183`
- `executive_dashboard_presenter.py:103,107`, `analytical_section_presenter.py:119`, `reports_presenter.py:72`
- `backend/application/analytics/services/bi_dashboard_service.py:56`

## Impacto
Exposición de información financiera de otras sucursales.

## Objetivo
- BI aplica el alcance de sucursal del usuario (estándar `BranchScopeQueryService`).
- Verificador de permisos real inyectado; sin default permisivo.
- Filtros de sucursal y fecha en las páginas.

## Alcance
- **Incluye:** Rutas, presenters y servicio de BI.
- **No incluye:** Persistencia de BI (BI-002).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
`docs/refactor/BI-33_final_validation.md`; memoria alcance por sucursal.

## Preguntas abiertas
- Ninguna por ahora.
