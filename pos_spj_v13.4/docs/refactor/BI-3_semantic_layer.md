# BI-3 — Semantic Metrics Layer

Estado: **DONE** (dominio + registro en memoria + catálogo seed; sin
persistencia ni consumidores reales todavía — eso llega en BI-4)

## Alcance

Capa semántica central (§11/§12 del prompt maestro): un único lugar donde
vive la fórmula, unidad, dimensiones, permiso y política de scope/freshness
de cada KPI, para que ningún widget/QueryService/export vuelva a
hardcodear una fórmula por su cuenta. Pura metadata — no toca SQL ni DB.

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/domain/analytics/enums.py` | `AggregationType`, `TimeGrain`, `CurrencyBehavior`, `ScopePolicy` (§62/§116), `FreshnessPolicy` (§65). |
| `backend/domain/analytics/value_objects/metric_definition.py` | `MetricDefinition` (frozen, con los 13 campos exigidos por §11: key/name/description/domain_owner/formula/unit/aggregation/dimensions/time_grain/currency_behavior/permission/scope_policy/freshness_policy + version), `DimensionDefinition`, `MeasureDefinition`. Validación en `__post_init__` (key `UPPER_SNAKE_CASE`, campos requeridos no vacíos, version ≥ 1). |
| `backend/domain/analytics/value_objects/metric_lineage.py` | `MetricLineage` — lo que responde "¿Cómo se calcula?" (§12): fórmula, versión, dueño, período, filtros, freshness, timestamp de cómputo. |
| `backend/domain/analytics/services/metric_lineage_service.py` | `build_lineage()` — función pura, arma un `MetricLineage` desde un `MetricDefinition` + contexto de evaluación (período/filtros/timestamp). Sin I/O. |
| `backend/application/analytics/services/metric_registry.py` | `MetricRegistry` — catálogo en memoria (`register`/`get`/`all`/`by_domain_owner`/`lineage_for`). `register()` rechaza versiones iguales o menores a la ya registrada (§69: nunca sobrescribir historia silenciosamente — aquí aplicado a la *definición* de la métrica, no solo a los resultados de forecast). |
| `backend/application/analytics/services/default_metric_catalog.py` | `build_default_catalog()` — siembra 13 métricas reales: `NET_SALES`, `COGS`, `NET_PROFIT`, `GROSS_MARGIN_PCT`, `AVERAGE_TICKET`, `ORDERS_COUNT`, `INVENTORY_VALUE`, `INVENTORY_TURNOVER`, `WASTE_RATE`, `ACCOUNTS_RECEIVABLE`, `ACCOUNTS_PAYABLE`, más dos forward-looking explícitamente nombradas en §11 (`CUSTOMER_FREQUENCY`, `FORECAST_ERROR`) cuya computación real llega en BI-12/BI-10 respectivamente. Las 11 primeras usan las fórmulas **ya documentadas y en producción** en `docs/architecture/BI_DASHBOARD.md` — no se inventó ninguna fórmula nueva. |

## Por qué en memoria y no persistido

El objetivo de BI-3 es que exista *una* fuente de verdad de metadata, no
todavía una tabla administrable. Persistir `MetricDefinition` (para que un
admin edite umbrales/fórmulas desde UI) es una capacidad de BI-4+ una vez
que exista un consumidor real (QueryService/UI) que lo justifique — construir
la tabla antes tendría cero consumidores y violaría la misma regla que aplica
a los `Bi*QueryService` (no agregar infraestructura sin que algo la use).

## Decisiones tomadas

- `CUSTOMER_FREQUENCY` usa `AnalyticsPermissions.PURCHASES_VIEW` como
  permiso provisional (documentado en el propio `description` del metric) —
  Customer Analytics (BI-12) todavía no tiene su propio código granular
  porque no hay Use Case que lo consuma; se corrige cuando ese Use Case
  exista, no antes (mismo criterio de "no anticipar permisos sin
  consumidor" que BI-2 aplicó al resto del catálogo).
- `ACCOUNTS_RECEIVABLE`/`ACCOUNTS_PAYABLE` usan
  `FINANCE_SENSITIVE_VIEW` (no `FINANCE_VIEW` general) — aplica §117
  literalmente: un gerente de sucursal no debe ver CxC/CxP de la compañía
  solo por ver su dashboard.
- Dimensiones usan claves en inglés (`branch`, `category`, `product`,
  `channel`, `payment_method`, `customer`, `supplier`, `customer_segment`)
  siguiendo el vocabulario de §17/§92 del prompt maestro — son claves de
  API/dominio, no texto visible al usuario (que sigue en español en la UI).

## Auditoría REGLA CERO

Sin persistencia, sin generación de identidad — value objects puros y un
registro en memoria. N/A.

## Tests

`tests/unit/analytics/test_metric_definition.py` (10 tests),
`test_metric_registry.py` (7 tests), `test_default_metric_catalog.py`
(5 tests) — 22 tests nuevos, todos verdes. Total acumulado BI-1/2/3:
40/40 tests verdes, 0 regresiones.

## Pendiente

- `MetricLineage` no tiene todavía ningún consumidor real (ninguna UI/API
  lo pide aún) — se cablea cuando exista el "¿Cómo se calcula?" en BI-24+.
  `datetime.now(timezone.utc)` en `MetricRegistry.lineage_for()` como default
  de `computed_at` es un detalle de conveniencia para BI-4; los QueryServices
  reales deben pasar el timestamp real de cómputo explícitamente, no confiar
  en el default.
- Sin `AnalyticalDataset` todavía (§11 lo menciona junto a MetricDefinition)
  — se define en BI-8 (Time Series Data) cuando exista una necesidad
  concreta de series, no antes.
- Ningún `Bi*QueryService` existente consume este registro todavía —
  ese es exactamente el trabajo de BI-4 (Consolidación de Query Layer).
