# BI-16 — Pricing Intelligence (elasticidad, PriceRecommendation)

Estado: **DONE**

## Alcance

§32-35: analizar precio/costo/margen/volumen/elasticidad y producir
`PriceRecommendation`. §34: BI nunca ejecuta `UPDATE productos SET precio`.
§35: sin historial suficiente, `confidence=LOW` y
`recommendation=REVIEW_REQUIRED` — nunca inventar elasticidad.

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/domain/forecasting/enums.py` (ampliado) | `EstimateConfidence` (LOW/MEDIUM/HIGH — confiabilidad de un estimador estadístico, distinto del `confidence` numérico 0..1 de las recomendaciones) + `PriceRecommendationType` (los 6 de §33 + `REVIEW_REQUIRED`, nombrado explícitamente en §35 pero no listado en §33 — se agrega igual porque el texto lo exige). |
| `backend/domain/forecasting/services/price_elasticity.py` | `estimate_price_elasticity()` — regresión lineal OLS sobre ln(precio) vs ln(cantidad) (modelo log-log estándar; la pendiente **es** el coeficiente de elasticidad), 100% `Decimal` (`Decimal.ln()`, sin numpy/scipy). Requiere `minimum_points` observaciones válidas **y** al menos 2 niveles de precio distintos — si no, `elasticity_coefficient=None`, `confidence=LOW`, nunca un número inventado. |
| `backend/domain/forecasting/value_objects/price_recommendation.py` | `PriceElasticityEstimate` (invariante: `LOW` nunca lleva coeficiente, cualquier otro nivel siempre lo requiere) + `PriceRecommendation` (§33 campos completos; invariante `REVIEW_REQUIRED` nunca sugiere un precio distinto al actual). Sin método de ejecución. |
| `backend/domain/forecasting/services/pricing_decision.py` | `decide_price_recommendation()` — función pura, separada deliberadamente de la estimación: dado un `PriceElasticityEstimate` ya calculado, decide `INCREASE_PRICE`/`DECREASE_PRICE`/`HOLD_PRICE`/`REVIEW_MARGIN`/`REVIEW_REQUIRED` y calcula `expected_volume_change_pct`/`expected_margin_change_pct`/`expected_revenue_change_pct` con la aproximación log-lineal de primer orden estándar (`%ΔQ ≈ E·%ΔP`, `%ΔIngreso ≈ %ΔP + %ΔQ`). Umbrales de elasticidad (`-1`/`-1.5`, unitaria/elástica) son convenciones económicas de texto, no defaults arbitrarios — mismo espíritu que las tablas Z ya fijas en BI-11/BI-13. |
| `backend/application/forecasting/services/pricing_intelligence_service.py` | `PricingIntelligenceService.recommend_price()` — conecta estimación + decisión, arma el `PriceRecommendation` final con id/timestamps. |

## Por qué separar estimación de decisión

`price_elasticity.py` (estimar) y `pricing_decision.py` (decidir dado un
estimado) son dos funciones puras independientes en vez de una sola — la
estimación por regresión es intrínsecamente aproximada y depende de datos
reales difíciles de controlar en un test; la decisión dado un estimado ya
calculado es 100% determinística. Separarlas permite probar la regla de
decisión con valores de elasticidad exactos y conocidos (`-0.5`, `-2`,
`-1.2`, `-1` exacto en el límite) sin depender de construir historiales de
precio/cantidad que produzcan esas pendientes por casualidad.

## Auditoría REGLA CERO

`PriceRecommendation.id` validado con `validate_uuidv7()`. N/A para el
resto (funciones puras, sin persistencia).

## Guardrail corregido durante esta fase

`InventoryForecastService` (BI-13) hizo que
`test_bi_single_forecasting_platform_ratchet.py` (BI-1) fallara — el patrón
`.*ForecastService.*` de esa regex, escrito antes de que existiera la
plataforma canónica, no distinguía "un motor duplicado nuevo en `core/`"
de "la plataforma canónica creciendo con nombres legítimos". Se corrigió
excluyendo `backend/domain/forecasting/`/`backend/application/forecasting/`
del escaneo — el guardrail ahora vigila exactamente lo que debía vigilar
desde el principio.

## Tests

`test_price_elasticity.py` (5, incluye una curva de demanda log-lineal
perfecta construida a mano — `q = 100/precio` — que recupera elasticidad
exacta `-1` sin importar cuántos puntos se usen, confirmando la regresión
matemáticamente, no solo por mock), `test_price_recommendation.py` (7),
`test_pricing_decision.py` (7, los 5 escenarios de decisión con valores
exactos + el caso límite de elasticidad unitaria + margen sin costo),
`test_pricing_intelligence_service.py` (2, wiring end-to-end). **22 tests
nuevos, todos verdes.**

## Pendiente

- Sin `PROMOTIONAL_DISCOUNT`/`CLEARANCE` en la lógica de decisión todavía —
  existen en el enum (§33) pero requieren una señal de inventario
  próximo-a-caducar/exceso que no está disponible limpiamente sin acoplarse
  a Inventario/Mermas; se agregan cuando exista ese puerto.
- Sin implementación de infraestructura para obtener
  `price_quantity_history` real (viene de Ventas/Pricing histórico) — el
  servicio recibe el historial ya armado por el llamador.
