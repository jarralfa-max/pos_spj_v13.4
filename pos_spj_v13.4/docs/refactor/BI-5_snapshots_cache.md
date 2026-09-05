# BI-5 — Snapshots / Cache

Estado: **DONE** (decisión documentada sobre las tablas legacy + primitivas
canónicas nuevas creadas; sin persistencia real ni migración de datos —
eso es explícitamente `BLOCKED` hasta que `AnalyticsEngine` se retire)

## Decisión: NO reconciliar `bi_sales_daily` vs `ventas_diarias` todavía

BI-0 (gap #1) señaló dos familias de tablas de snapshot diario aparentemente
duplicadas: `ventas_diarias`/`inventario_diario`/`clientes_diarios`
(migración 032) vs `bi_sales_daily`/`bi_product_profit`/`bi_transformations`/
`bi_branch_ranking` (migración 062). Investigación de consumidores reales
(BI-5):

| Tabla | Escritor | Lector | Naturaleza |
|---|---|---|---|
| `ventas_diarias` | `core/services/enterprise/report_engine_v2.py::save_daily_snapshot()` | `core/services/analytics/analytics_engine.py` (línea 484, fast-path "hoy") | Snapshot por lote/scheduler |
| `bi_sales_daily` | `AnalyticsEngine.update_sales()` (evento `SALE_CREATED`) | `AnalyticsEngine` mismo (líneas 424-525: ventana de 30 días para un cálculo tipo forecast interno) | Snapshot event-driven en tiempo real |
| `inventario_diario`, `clientes_diarios` | — (solo en la migración) | — (cero consumidores encontrados) | Ya muertas, ni siquiera duplicadas — simplemente sin uso |
| `bi_product_profit`, `bi_branch_ranking` | `AnalyticsEngine` (parcial: `bi_branch_ranking` no tiene escritor encontrado) | `AnalyticsEngine` | Igual que `bi_sales_daily` |
| `kpi_snapshots` | `core/services/enterprise/report_engine.py` | — | Tercera familia adicional, tampoco reconciliada aquí |

**Ninguna de estas tablas alimenta el dashboard ejecutivo** (`BiDashboardService`/
`Bi*QueryService`, ya relocalizado en BI-4) — los `Bi*QueryService` calculan
todo en tiempo real contra `ventas`/`detalles_venta`/etc., no contra
snapshots. Las dos familias solo alimentan `AnalyticsEngine`, que las escribe
**y** las lee él mismo (dos pipelines de alimentación distintas — una por
lote nocturno, otra síncrona por evento — para el mismo consumidor).

Fusionar los esquemas ahora significaría reescribir el comportamiento interno
de `AnalyticsEngine` (`BLOCKED` en BI-0, activo en producción, sin tests de
regresión propios en este refactor) solo para eliminar una duplicación que
**no tiene ningún efecto visible fuera de esa clase**. Eso viola la regla de
oro del prompt maestro (§150: "No eliminar funcionalidad antes de
inventariarla") aplicada en sentido inverso — modificar sin necesidad real
es el mismo riesgo que eliminar sin reemplazo. **Decisión: no tocar ninguna
de las dos familias de tablas en BI-5.** La reconciliación real ocurre en
BI-32 (Legacy Removal) cuando `AnalyticsEngine` se reemplace por el
`AnalyticalSnapshotWorker` canónico (§65/§125) — en ese momento ya no importa
si las tablas legacy se fusionan o simplemente se dejan de escribir.

## Componentes nuevos (aditivos, sin consumidores todavía)

| Archivo | Responsabilidad |
|---|---|
| `backend/domain/analytics/value_objects/analytical_snapshot.py` | `AnalyticalSnapshot` (§64) — value object inmutable: `kind` (`SnapshotKind`: `DAILY_SALES`/`INVENTORY_DAILY`/`BRANCH_DAILY`/`PRODUCT_PROFITABILITY`/`FORECAST_ACCURACY`, mismo vocabulario que los 5 ejemplos de §64), `scope_policy`/`scope_value`, `period`, `values: dict[str, Decimal]`, `computed_at`, y **`source_event_ids`** obligatorio — sin eso el snapshot no es reconstruible (§64: "Son proyecciones reconstruibles"), que es precisamente lo que le falta a `bi_sales_daily`/`ventas_diarias` hoy (ninguna de las dos guarda qué evento/venta produjo cada fila). |
| `backend/application/analytics/services/analytics_cache.py` | `AnalyticsCacheKey` (§63: `company_id`+`scope_policy`+`scope_value`+`permissions_hash`+`filters_signature`+`metric_version`+`dataset_version`, todos obligatorios) + `AnalyticsCache` genérico con TTL (reloj inyectable para tests). **No reemplaza** el cache ad hoc de `BiDashboardService` (ese sigue con su dict simple keyeado solo por filtros — funciona, tiene tests, tocarlo no es parte de esta fase) — es la forma canónica que **futuros** consumidores (BI-12+) deben usar, precisamente para evitar que dos usuarios con permisos distintos compartan una entrada de cache (fuga de datos entre scopes). |

## Por qué sin persistencia todavía

Igual que `MetricRegistry` en BI-3: no existe ningún productor real de
`AnalyticalSnapshot` todavía (eso es `AnalyticalSnapshotWorker`, §125, fase
futura) — construir una tabla `analytical_snapshots` sin escritor real sería
infraestructura sin consumidor, el mismo error que ya cometió la migración
062 con `bi_branch_ranking` (tabla creada, nunca escrita).

## Tests

`tests/unit/analytics/test_analytical_snapshot.py` (5 tests),
`tests/unit/analytics/test_analytics_cache.py` (11 tests) — 16 tests nuevos,
todos verdes.

## Pendiente

- `AnalyticalSnapshotWorker` (productor real de `AnalyticalSnapshot`,
  consumiendo `SALE_CREATED`/`STOCK_UPDATED`/etc.) — fase futura, reemplaza a
  `AnalyticsEngine`.
- Persistencia de `AnalyticalSnapshot` (tabla `analytical_snapshots` o
  similar) — solo cuando exista el worker que la llene.
- Migrar `BiDashboardService` a `AnalyticsCache` canónico — no se hizo aquí
  para no tocar dos veces el mismo archivo recién movido en BI-4 sin un
  motivo funcional nuevo.
