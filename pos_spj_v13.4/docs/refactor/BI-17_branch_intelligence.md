# BI-17 — Branch Intelligence (BranchRecommendation)

Estado: **DONE** (2 de 8 tipos producidos realmente: `INCREASE_STOCK`/
`REDUCE_STOCK`/`TRANSFER_STOCK`; los otros 5 quedan como vocabulario
reservado — sin señal disponible todavía)

## Alcance

§31/§77: analizar sucursales y recomendar acciones de stock/surtido/
horarios/capacidad — nunca abrir/cerrar sucursales, nunca mover stock
directamente. §74: sugerencias de transferencia entre sucursales.

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/domain/forecasting/value_objects/branch_recommendation.py` | `BranchRecommendationType` (8 valores de §77) + `BranchRecommendation` + `StockTransferRecommendation` (§74). Sin métodos de ejecución. |
| `backend/application/forecasting/services/branch_intelligence_service.py` | `BranchIntelligenceService` — `analyze_stock_risk()` agrega `InventoryForecast` (BI-13) sobre el conjunto de productos de una sucursal: si una fracción suficiente muestra riesgo de quiebre → `INCREASE_STOCK`; si domina el sobre-stock → `REDUCE_STOCK`. `recommend_transfer()` compara el mismo producto en dos sucursales — superávit en una + déficit en otra → `StockTransferRecommendation` con `suggested_quantity = min(superávit_origen, necesidad_destino)`. |

## Por qué solo 3 de 8 tipos

`CHANGE_ASSORTMENT`/`REVIEW_STAFFING`/`REVIEW_HOURS`/`REVIEW_PRICING`/
`CAPACITY_EXPANSION` requieren señales que este pipeline no tiene todavía
(rotación de personal, horarios de POS, competitividad de precio de
mercado, capacidad de piso/refrigeración) — quedan como valores de enum
reservados, no como recomendaciones fabricadas sin evidencia real. Mismo
criterio que BI-9 (familias de modelo "etapa posterior") y BI-16
(`PROMOTIONAL_DISCOUNT`/`CLEARANCE` sin señal de inventario próximo a
caducar).

## Cálculo de `StockTransferRecommendation.suggested_quantity`

```
source_surplus      = stock_disponible_origen − reorder_point_origen
destination_need     = recommended_quantity(stock_disponible_destino,
                                             reorder_point_destino,
                                             target_coverage_days,
                                             demanda_promedio_destino)
suggested_quantity   = min(source_surplus, destination_need)
```

Nunca sugiere transferir más de lo que el origen realmente tiene de sobra,
ni más de lo que el destino realmente necesita — ambos lados acotan la
cantidad.

## Auditoría REGLA CERO

Ids validados con `validate_uuidv7()` en ambos value objects; sin otra
identidad nueva. N/A para el resto.

## Tests

`test_branch_recommendation.py` (6, validación de value objects),
`test_branch_intelligence_service.py` (5: INCREASE_STOCK cuando domina
quiebre, REDUCE_STOCK cuando domina sobre-stock, ninguna recomendación
cuando todo está sano, transferencia con cantidad exacta calculada a mano
`210`, y transferencia rechazada cuando el origen tampoco tiene superávit).
**11 tests nuevos, todos verdes.**

## Pendiente

- Los 5 tipos de recomendación sin señal disponible (arriba) — se agregan
  cuando exista el puerto correspondiente (RRHH/horarios, Pricing
  competitivo, Activos/capacidad).
- `recommend_transfer()` compara un solo par origen/destino por llamada —
  un barrido de "todas las sucursales" que encuentre automáticamente los
  mejores pares superávit/déficit es trabajo de UI/orquestación futura, no
  de esta fase.
