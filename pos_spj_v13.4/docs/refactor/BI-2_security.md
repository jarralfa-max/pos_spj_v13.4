# BI-2 — Seguridad: permisos granulares + eventos canónicos

Estado: **DONE** (permisos y eventos; sin Use Cases ni scopes en tiempo de
ejecución todavía — eso llega con BI-4+)

## Alcance

Capa de seguridad reutilizable para todo lo que se construya desde BI-3 en
adelante, siguiendo el **estándar de Compras** (`backend/application/procurement/`)
pedido explícitamente por el usuario para bounded contexts nuevos — ver
`[[feedback_permissions_compras_standard]]` — y ya replicado en Meat
Processing (`PROC-1_security.md`): códigos punteados `MODULO.accion`
**registrados en el catálogo canónico**, más una `AuthorizationPolicy` con
`require()`/`has_permission()`.

## Por qué `INTELIGENCIA_BI` y no una clave nueva

`interfaz/menu_lateral.py` ya define el botón "📈 Inteligencia de Negocios"
con id de módulo `"INTELIGENCIA_BI"`, y `security/rbac.py` ya siembra
permisos de ese módulo a los roles por defecto (`INTELIGENCIA_BI.ver`,
`INTELIGENCIA_BI.ver_ventas`, …). Introducir claves paralelas
(`ANALYTICS`, `FORECASTING`, `DECISION_INTELLIGENCE`) habría violado el
principio rector §3/§64 ("una sola ruta canónica") y roto la siembra de roles
existente — mismo razonamiento que PROC-1 aplicó a `PRODUCCION`.

Los 11 códigos planos legacy (`ver`, `ver_ventas`, …, `configurar`) se
**conservan sin cambios**: `backend/application/services/bi_dashboard_service.py`
y `security/rbac.py` ya los consumen tal cual, y no hay motivo para
romperlos antes de que BI-4 relocalice ese servicio. BI-2 solo **amplía** el
catálogo con la superficie granular que no existía en absoluto: forecast,
decision intelligence, escenarios, alertas y acceso web remoto futuro
(~70 códigos nuevos, mismo orden de magnitud que `PRODUCCION` tras PROC-1).

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/application/analytics/permissions.py` | `AnalyticsPermissions` — catálogo de códigos punteados `INTELIGENCIA_BI.accion`, organizados por §104-114 del prompt maestro (general, ventas, inventario, compras, producción, pricing, finanzas, forecast, decision intelligence, alertas, web remota). `ALL_ANALYTICS_PERMISSIONS` frozenset derivado por introspección, mismo patrón que `PurchasePermissions`/`MeatProcessingPermissions`. |
| `core/security/permission_catalog.py` | `CANONICAL_MODULE_PERMISSIONS["INTELIGENCIA_BI"]` ampliado de 11 códigos planos a ~70 (planos + punteados). Única fuente de verdad para la matriz de Configuración → Seguridad. |
| `backend/application/analytics/authorization.py` | `AnalyticsAuthorizationPolicy` — `require()` (falla cerrado sin checker o sin permiso), `has_permission()` (probe no-raise para gating de UI, §119). Sin autorización en caliente todavía (BI no tiene el patrón de "excepción aprobada por un segundo usuario" que sí tiene Compras/Procesamiento — se añade si algún Use Case futuro lo necesita). |
| `backend/domain/analytics/exceptions.py` | `AnalyticsDomainError` y subclases: `AnalyticsPermissionDeniedError`, `MetricNotFoundError`, `MetricLineageUnavailableError`, `RecommendationExpiredError`, `ScopeViolationError` (§62). (`ForecastModelNotApprovedError` se re-declaró originalmente aquí; BI-7 la relocalizó a `backend/domain/forecasting/exceptions.py` — forecasting es un bounded context separado de analytics, §7 — sin consumidores que actualizar, era código sin uso todavía.) |
| `core/events/domain_events.py` | 17 eventos canónicos nuevos (§122): `ANALYTICS_SNAPSHOT_CREATED`, `FORECAST_RUN_STARTED/COMPLETED/FAILED`, `FORECAST_MODEL_APPROVED/ACTIVATED/DEGRADED`, `ANALYTICS_ALERT_CREATED/ACKNOWLEDGED/RESOLVED`, `BUSINESS_RECOMMENDATION_CREATED/APPROVED/REJECTED/EXPIRED`, `SCENARIO_CREATED/EVALUATED`, `ANALYTICAL_REPORT_GENERATED`. Todos lowercase (convención del archivo para eventos nuevos, no legacy UPPERCASE). No se tocó el legacy `FORECAST_GENERADO` (`event_bus.py`) ni el string crudo no registrado `"FORECAST_GENERATED"` de `core/forecast/replenishment_engine.py` — ambos se retiran en BI-32 junto con sus emisores. |

## Brecha identificada y NO corregida en esta pasada

`core/forecast/replenishment_engine.py:139` sigue publicando el string crudo
`"FORECAST_GENERATED"` (inglés, no registrado) en vez del nuevo
`FORECAST_RUN_COMPLETED` canónico — no se edita ese archivo aquí porque es
código muerto (`BLOCKED` en BI-0, cero consumidores en producción); tocarlo
sin más contexto no reduce riesgo real. Se corrige cuando ese motor se
re-implemente dentro de la `ForecastingPlatform` canónica (BI-11) o se
retire (BI-32).

## Auditoría REGLA CERO

| Componente | Hallazgo | Estado |
|---|---|---|
| `permissions.py` | Solo constantes `str`; sin ids | ✅ N/A |
| `authorization.py` | Sin persistencia; no genera identidad | ✅ N/A |
| `exceptions.py` | Sin persistencia; no genera identidad | ✅ N/A |
| `domain_events.py` (nuevos eventos) | Solo constantes `str`; el `event_id`/`operation_id` de cada evento lo genera el emisor real (BI-11+) vía `backend/shared/ids.py`, no aquí | ✅ N/A |

## Tests

- `tests/unit/analytics/test_analytics_permissions.py` (6 tests): unicidad,
  namespace `INTELIGENCIA_BI.*`, distinción lectura/mutación, código dedicado
  para métricas financieras sensibles (§117), sincronía con el catálogo,
  normalización case-insensitive.
- `tests/unit/analytics/test_analytics_authorization.py` (6 tests): sin
  checker configurado, código desconocido, sin usuario, checker deniega,
  checker concede, `has_permission()` no lanza.
- `tests/architecture/test_analytics_permissions_are_granular.py` (3 tests):
  reutiliza `INTELIGENCIA_BI` (no crea claves paralelas), el catálogo creció
  más allá del stub plano, `backend/domain/analytics`/`backend/application/analytics`
  no importan ningún motor legacy.

17/17 verdes (incluye los 2 de BI-1) — ver también regresión verde de
`tests/test_bi_role_permissions_seed.py`, `tests/integration/test_bi_permissions.py`
y `tests/test_event_bus_aliases.py` tras los cambios.

## Pendiente

- Scopes en tiempo de ejecución (OWN/TEAM/BRANCH/TERRITORY/REGION/COMPANY/ALL,
  §62/§116) — sin `ExecutionContext` todavía; se añade cuando existan Use
  Cases/QueryServices reales que lo necesiten (BI-4+).
- Registrar `AnalyticsAuthorizationPolicy` en una futura
  `AnalyticsUseCaseFactory` (composition root) cuando existan Use Cases
  reales (BI-4+).
- Auditoría persistente de acceso (§121) requiere infraestructura de
  persistencia — no implementada aquí.
- Otorgar los nuevos códigos granulares a roles por defecto vía
  Configuración → Seguridad → Permisos queda **fuera de esta pasada**
  (mismo criterio que PROC-1: no se conceden automáticamente a ningún rol).
