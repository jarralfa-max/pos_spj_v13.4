# SDLC-BI-002 — BI: ajustes y estado de alertas sólo en memoria; errores SQL se muestran como $0

- **Prioridad:** P2
- **Nivel de riesgo:** T2
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** SDLC-BI-001

## Problema
`BiSettingsService` cae a `_MemoryStore` porque nadie le pasa almacén: umbrales, meta y ventana de pronóstico son fijos. Las reglas de alerta reciben UUID nuevos en cada evaluación, `existing_alerts` nunca se pasa (no hay dedup/cooldown) y reconocer/resolver sólo cambia el objeto en memoria. La capa de consultas atrapa errores SQL y devuelve `[]`/ceros (13 `except Exception`), así que una consulta rota aparece como KPI en $0.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/analytics/services/bi_settings_service.py:38-39`
- `bi_dashboard_service.py:62`, `alert_explorer_presenter.py:78,84-120`, `forecast_explorer_presenter.py:87`, `price_recommendation_presenter.py:110`
- `backend/application/analytical_alerting/services/alert_engine.py:35,43`; `pages/alert_explorer_page.py:82-90`
- `backend/application/analytics/queries/bi_sales_query_service.py:72-77`; `bi_forecast_query_service.py:30-32`

## Impacto
Decisiones sobre cifras en cero por error; alertas que reaparecen.

## Objetivo
- Ajustes y estado de alertas persistidos (UUIDv7).
- Error de consulta visible como error, no como cero.

## Alcance
- **Incluye:** Servicios y presenters de BI.
- **No incluye:** Alcance (BI-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T2: plan corto y pruebas afectadas.

## Trabajo previo relacionado
BI-33 brechas #4 y #6.

## Preguntas abiertas
- Ninguna por ahora.
