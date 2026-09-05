# BI-27 — Decision Intelligence (Recommendations UI)

Estado: **DONE**, alcance deliberadamente limitado a recomendaciones de
precio (ver justificación abajo)

## Alcance

§14/§32-40: página "Decision Intelligence" — generar una recomendación con
evidencia, y aplicarle el ciclo de vida real (§39: NEW→ACKNOWLEDGED→
UNDER_REVIEW→APPROVED/REJECTED, +DISMISSED/EXPIRED).

## Decisión central: solo Precios tiene un camino real de extremo a extremo

BI-18 unificó 4 tipos de recomendación fuente
(Purchase/Production/Price/Branch) en `BusinessRecommendation`, pero cada
uno necesita datos reales distintos para construirse:

| Fuente | Qué necesita | ¿Existe una query real hoy? |
|---|---|---|
| `PurchasePlanningService` (BI-14) | `InventoryPosition` (existencia, reservado, **entrante**, fecha de llegada, **lead time del proveedor**) | No — requeriría cruzar compras en tránsito + acuerdos de proveedor, no existe como agregado |
| `ProductionPlanningService` (BI-15) | `InventoryPosition` + capacidad/rendimiento (`ProductionCapacityPort`) | No — mismo problema |
| `BranchIntelligenceService` (BI-17) | Recorrer el catálogo de productos de una sucursal completa | Parcial — requeriría iterar N productos por sucursal, no una sola consulta |
| `PricingIntelligenceService` (BI-16) | `current_price`/`current_cost`/historial (precio, cantidad) | **Sí** — `detalles_venta`/`ventas`/`product_cost`, las mismas tablas que `BiSalesQueryService` ya lee |

Construir Purchase/Production/Branch con datos inventados o una agregación
SQL nueva sin mandato claro habría sido exactamente la "infraestructura sin
consumidor real" que esta transformación ha evitado en cada fase (mismo
criterio que BI-17 con sus 5/8 tipos no producidos, BI-25 con Producción/
Precios/Sucursales). Se documenta como brecha honesta, no se fabrica.

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/application/analytics/queries/price_history_query_service.py` | `PriceHistoryQueryService` — nueva query real (lectura pura, mismo estilo que `BiSalesQueryService`): `price_quantity_history()` (pares precio/cantidad observados), `latest_price()`, `current_cost()`. No es lo mismo que `PricingReadService.list_price_history()` (esa lee `price_change_log`, ediciones de lista de precios; esta lee lo que el cliente realmente pagó). |
| `frontend/desktop/modules/business_intelligence/presenters/price_recommendation_presenter.py` | `PriceRecommendationPresenter` — `generate()` construye un `PriceRecommendation` real vía `PricingIntelligenceService` (BI-16) y lo adapta a `BusinessRecommendation` vía `from_price_recommendation` (BI-18); cuando la decisión es informativa (HOLD_PRICE/REVIEW_REQUIRED) captura `UnsupportedRecommendationSourceError` y devuelve el `reason` en su lugar. `apply_transition()` aplica las funciones puras reales de `recommendation_transitions.py` (BI-18). |
| `frontend/desktop/modules/business_intelligence/pages/price_recommendation_page.py` | `PriceRecommendationPage` — producto+sucursal (búsqueda, §20) + umbral de margen (`PercentInput`, default de `BiSettingsService.threshold_margen_bajo_pct` — reutilizado, no un nuevo umbral inventado, §3/§64) + vigencia en días + botón "Generar recomendación" → KPI bar + tabla de evidencia (`StandardTable`) + botones de ciclo de vida (Reconocer/Iniciar revisión/Aprobar/Rechazar/Descartar). |
| `business_intelligence_routes.py` (editado) | `bi_recommendations` ahora construye `PriceRecommendationPage` cuando hay `connection`. |

## Por qué las transiciones de ciclo de vida no persisten

`BusinessRecommendation` no tiene tabla/repositorio propio en todo el
repositorio (brecha documentada desde BI-22: los endpoints de
recomendaciones sirven listas vacías hoy). Los botones de ciclo de vida
aplican las funciones puras reales de BI-18 (validación de transición
incluida — un salto inválido como NEW→APPROVED directo se rechaza con el
mismo `InvalidRecommendationTransitionError` real, no una simulación) sobre
la copia en memoria de la página; se pierde al refrescar. Documentado, no
oculto — la persistencia real es trabajo futuro.

## Auditoría REGLA CERO

`BusinessRecommendation.id`/`PriceRecommendation.id` ya validan UUIDv7 en su
propio `__post_init__` (BI-18/16) — el presenter solo los invoca, no genera
identidad nueva por su cuenta. N/A.

## Tests

`test_price_recommendation_presenter.py` (11: mapeo KPI, degradación sin
filas, validación de producto/sucursal/vigencia, sin historial → error legible,
un solo precio → resultado informativo (REVIEW_REQUIRED), un historial de
demanda elástica real (`q=1024/precio²`, elasticidad exactamente -2, misma
construcción que el propio test de elasticidad de BI-16) → recomendación
real DECREASE_PRICE + secuencia completa de transiciones válidas, y una
transición inválida + una acción desconocida rechazadas),
`test_price_recommendation_page.py` (6: construcción, defaults desde
settings, selección de producto/sucursal, transición sin recomendación
(mensaje, no crash), transición con recomendación en memoria, ruteo).
**17 tests nuevos, todos verdes** (83 en el paquete `business_intelligence`
completo).

## Pendiente

- Purchase/Production/Branch recommendations sin página propia — esperan a
  que exista una consulta agregada real de inventario/capacidad/sucursal
  (no inventada aquí).
- Sin persistencia de `BusinessRecommendation` — cada generación y cada
  transición viven solo en la sesión de la página.
- BI-28 construye Alertas; BI-29 Escenarios.
