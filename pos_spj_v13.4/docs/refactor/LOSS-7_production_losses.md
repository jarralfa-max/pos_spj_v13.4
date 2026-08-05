# LOSS-7 — Producción

Estado: implementado el 2026-08-03.

## Integración canónica

`ProductionCompletedLossHandler` transforma `MEAT_PRODUCTION_COMPLETED` en
`AnalyzeProductionLossCommand`. Conserva como UUIDv7 la producción, versión de
receta, versión del perfil, productos, actor, sucursal, almacén y operación. Los
pesos se convierten directamente de texto a `Decimal`; nunca pasan por `float`.

El repositorio acepta únicamente `recipes`/`recipe_versions` y
`yield_profiles`/`yield_profile_versions` activas. No consulta
`product_recipes`, `recetas` ni tablas de compatibilidad.

## Rendimiento y clasificación

El rendimiento esperado es la suma de outputs productivos del perfil; outputs
`WASTE` y `LOSS` no se cuentan como producto recuperado. La banda inferior es:

`expected_yield_pct - tolerance_pct`

- Dentro de banda: toda la diferencia física se registra como merma normal
  `PROCESS_LOSS`.
- Fuera de banda: la pérdida esperada queda como `PROCESS_LOSS` y el exceso como
  `YIELD_VARIANCE`.

Ambos expedientes nacen `SUBMITTED`, vinculados a la orden de producción y con
`requires_inventory_posting=0`: consumo y outputs ya fueron reflejados por el
ledger de Producción/Inventario y un posteo adicional duplicaría la salida.

Cada análisis persiste atómicamente expedientes, líneas, `yield_variances`,
outbox y operación procesada. El replay por `operation_id` devuelve el resultado
original sin duplicar pérdidas.

## Verificación

- Casos unitarios dentro y fuera de tolerancia.
- Contexto de receta/perfil versionado.
- Adaptación del evento conservando precisión decimal.
- Integración real: entrada 100, rendimiento esperado 90 %, salida 84; genera
  10 kg normales y 6 kg anormales una sola vez. Outputs declarados como
  `WASTE`/`LOSS` no se cuentan como rendimiento productivo.
- Ocho pruebas `unittest` de integración y siete unitarias/arquitectónicas
  ejecutadas correctamente. `pytest` no está instalado en el entorno.
