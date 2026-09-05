# BI-18 — Decision Intelligence Engine (BusinessRecommendation)

Estado: **DONE** (unificación de los 4 tipos de recomendación de BI-14..17
bajo un solo lifecycle; sin motor de reglas propio todavía — no hace falta,
las reglas viven en cada servicio de origen)

## Alcance

El memory file de esta transformación dejaba abierta la pregunta desde
BI-12: *"¿deberían Purchase/Production/Pricing/Branch unificarse bajo un
solo `BusinessRecommendation` con workflow de aprobación compartido?"* BI-18
responde que sí y lo construye: un bounded context nuevo,
`backend/domain/decision_intelligence/`, separado de
`backend/domain/forecasting/` (§7).

## Componentes creados

| Archivo | Responsabilidad |
|---|---|
| `backend/domain/decision_intelligence/enums.py` | `BusinessRecommendationType` (16 valores de §38) + `RecommendationStatus` (8 de §39). |
| `backend/domain/decision_intelligence/value_objects/business_recommendation.py` | `BusinessRecommendation` (§37: los 16 campos exactos) + `is_terminal()`. Todos los campos de explicabilidad (§40) son obligatorios: `evidence` no puede estar vacío, `model_reference` opcional pero presente en los 5 adaptadores. |
| `backend/domain/decision_intelligence/services/recommendation_transitions.py` | Máquina de estados pura (§39): `acknowledge`/`start_review`/`approve`/`reject`/`dismiss`/`expire`/`mark_executed_externally` — cada una devuelve una instancia nueva (`dataclasses.replace`, el value object es inmutable), nunca muta in-place. **`mark_executed_externally()` es la única función que llega a `EXECUTED_EXTERNALLY`** — modela que BI nunca marca una recomendación como ejecutada por sí sola (§39), solo al recibir la señal correspondiente del bounded context ejecutor. Requiere pasar por `UNDER_REVIEW`→`APPROVED` antes de `EXECUTED_EXTERNALLY` — no hay atajo. |
| `backend/application/decision_intelligence/adapters.py` | 5 funciones puras: `from_purchase_recommendation`, `from_production_recommendation`, `from_price_recommendation`, `from_branch_recommendation`, `from_stock_transfer_recommendation` — convierten cada value object de BI-14..17 a `BusinessRecommendation`, preservando toda la evidencia original como `evidence` (stringificada). |

## Mapeo de tipos (y lo que deliberadamente no se mapea)

| Fuente | `BusinessRecommendationType` |
|---|---|
| `PurchaseRecommendation` | `PURCHASE_MORE` |
| `ProductionRecommendation` | `INCREASE_PRODUCTION` |
| `PriceRecommendation.INCREASE_PRICE` | `PRICE_INCREASE` |
| `PriceRecommendation.DECREASE_PRICE` | `PRICE_DECREASE` |
| `PriceRecommendation.HOLD_PRICE/REVIEW_MARGIN/REVIEW_REQUIRED` | **sin mapeo** — `UnsupportedRecommendationSourceError` explícito |
| `BranchRecommendation.INCREASE_STOCK` | `PURCHASE_MORE` |
| `BranchRecommendation.REDUCE_STOCK` | `PURCHASE_LESS` |
| `BranchRecommendation.{CHANGE_ASSORTMENT,...}` (los 5 sin señal de BI-17) | **sin mapeo** — `UnsupportedRecommendationSourceError` explícito |
| `StockTransferRecommendation` | `TRANSFER_STOCK` |

Un resultado "hold"/"needs review" es informativo — no necesita workflow de
aprobación (no hay nada que aprobar en "mantener el precio igual"). Elevar
esos casos a `BusinessRecommendation` habría inflado la cola de revisión con
ruido sin acción posible. `PriceRecommendation` no trae su propio campo
`priority` (a diferencia de los otros 3 tipos) — el adaptador lo deriva de
`confidence` usando los mismos umbrales que BI-16 ya fijó para sus buckets
de `EstimateConfidence`.

## Auditoría REGLA CERO

`BusinessRecommendation.id` validado con `validate_uuidv7()`; los
adaptadores generan un `id` nuevo por cada conversión vía `new_uuid()` (la
`BusinessRecommendation` es una entidad distinta de su fuente, con su
propio ciclo de vida de aprobación). N/A para el resto.

## Tests

`test_business_recommendation.py` (12), `test_recommendation_transitions.py`
(9, incluye el camino feliz completo NEW→ACKNOWLEDGED→UNDER_REVIEW→
APPROVED→EXECUTED_EXTERNALLY, verificación de inmutabilidad, y que los 4
estados terminales no aceptan ninguna transición), `test_adapters.py` (7,
las 5 conversiones + los 2 casos de `UnsupportedRecommendationSourceError`).
**33 tests nuevos, todos verdes.**

## Pendiente

- Sin motor de reglas basado en umbrales (eso es BI-20, Alert Engine —
  conceptualmente relacionado pero es un tipo de artefacto distinto,
  alertas no recomendaciones) que genere `BusinessRecommendation`
  directamente sin pasar por un adaptador de forecasting.
- Sin persistencia — `BusinessRecommendation` vive solo en memoria por
  ahora, igual que `ForecastModelDefinition` antes de BI-11; se construye
  cuando exista un caller real (UI de aprobación, BI-27).
- Sin wiring de eventos (`BUSINESS_RECOMMENDATION_CREATED/APPROVED/
  REJECTED/EXPIRED`, ya definidos en BI-2) — se conecta cuando exista un
  Use Case real que dispare las transiciones desde un caso de uso, no antes.
