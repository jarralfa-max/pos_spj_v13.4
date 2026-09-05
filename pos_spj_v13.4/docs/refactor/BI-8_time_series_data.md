# BI-8 — Time Series Data

Estado: **DONE** (una serie canónica real, con lectura SQLite funcionando
contra las tablas de producción; más series se agregan cuando un consumidor
real las necesite, no especulativamente)

## Alcance

BI-7 definió las formas de dominio (`TimeSeriesDefinition`/
`TimeSeriesObservation`) sin ningún productor real. BI-8 las conecta a datos
reales: un `TimeSeriesRegistry` (catálogo, mismo patrón que `MetricRegistry`
de BI-3), un `TimeSeriesDatasetBuilder` (aplica `minimum_history_days` antes
de entregar datos a un modelo), y la primera implementación real de
`TimeSeriesReaderPort` contra SQLite.

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/application/forecasting/services/time_series_registry.py` | `TimeSeriesRegistry` — catálogo en memoria de `TimeSeriesDefinition` (register/get/all), rechaza claves duplicadas. |
| `backend/application/forecasting/services/default_series_catalog.py` | `build_default_series_catalog()` — siembra **una** serie: `daily_sales_by_product` (dimensiones `product`+`branch`, grano `DAILY`, `minimum_history_days=14`). |
| `backend/application/forecasting/services/time_series_dataset_builder.py` | `TimeSeriesDatasetBuilder` — valida rango de fechas (`date_to >= date_from`), aplica `minimum_history_days` de la definición (`InsufficientHistoryError` si el rango pedido es más corto), valida que el `dimension_filter` no traiga claves no declaradas por la serie, y delega la lectura real al puerto. |
| `backend/infrastructure/db/repositories/forecasting/sqlite_time_series_reader.py` | `SqliteDailyProductSalesReader` — primera implementación real de `TimeSeriesReaderPort`. Lee `SUM(dv.cantidad)` agrupado por día desde `detalles_venta`/`ventas` (mismas tablas que `BiSalesQueryService`, BI-4), filtra `estado='completada'` + `producto_id` + opcionalmente `sucursal_id`. **Todo día del rango sin fila de venta se devuelve como `TimeSeriesObservation(value=0, is_imputed=True, imputation_reason="no_sales_recorded")`** — nunca un hueco silencioso, nunca un cero indistinguible de un día real sin ventas (§18). |

## Por qué solo una serie

`daily_sales_by_product` es exactamente lo que BI-9 (modelos baseline) y
BI-12 (Demand Planning por producto) necesitan primero. Agregar
`daily_sales_by_category`/`by_channel`/`by_supplier` ahora, sin que ningún
Use Case las consuma todavía, repetiría el error que BI-0 encontró en
`bi_branch_ranking` (tabla creada, nunca poblada) — se agregan en BI-12+
cuando el consumidor real las pida.

## Decisión de política de imputación (§18)

Se optó por la política más simple y honesta posible para el primer
consumidor real: **todo día sin venta registrada es un cero explícito**, con
`imputation_reason="no_sales_recorded"` — no se intenta inferir quiebre de
stock histórico (`stockout_probability`) porque no existe una fuente
histórica de nivel de inventario por día en el esquema actual;
inventarlo sería inventar datos. Cuando `backend/infrastructure/db/repositories/inventory/`
exponga un histórico diario real de existencias, esta política puede
refinarse a distinguir `no_sales_recorded` de `stockout` — hasta entonces,
marcar todo como imputado (en vez de como demanda-cero silenciosa) es
estrictamente más honesto que lo que hacían los 8 motores legacy, ninguno de
los cuales distinguía el caso.

## Auditoría REGLA CERO

Sin persistencia nueva, sin generación de identidad — el reader solo lee.
N/A.

## Tests

`tests/unit/forecasting/test_time_series_registry.py` (4),
`test_default_series_catalog.py` (1), `test_time_series_dataset_builder.py`
(4, con un `_FakeReader` — no toca DB), y
`tests/integration/test_time_series_reader_sqlite.py` (8, contra un SQLite
en memoria con solo las 2 tablas que el reader toca — se evitó a propósito
el bootstrap completo `fresh_db()`/`make_db()`, que tiene un bug preexistente
documentado en BI-4/`[[env_nested_git_repo_pos_spj]]`). 17 tests nuevos,
todos verdes; suite acumulada BI-7+BI-8: 47/47 verdes.

## Pendiente

- Más series (`daily_sales_by_category`, `daily_sales_by_branch`, …) cuando
  BI-12+ las necesite.
- Ningún consumidor real todavía usa `TimeSeriesDatasetBuilder` — eso es
  BI-9 (modelos baseline, que necesitan observaciones para entrenar).
