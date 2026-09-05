# PROC-18 — Trazabilidad: Procesamiento Cárnico

Estado: **DONE** (grafo de genealogía entre orden origen y orden destino +
consulta de trazabilidad ascendente/descendente/recall)

## Alcance y decisión de arquitectura

§38 pide poder responder "qué lotes/insumos entraron a qué salida" y, para
recall, "qué salió de un lote dado, aguas abajo". Dentro de **una misma**
orden, `MaterialConsumption` y `ProcessOutput` ya comparten
`processing_order_id` — no hace falta un enlace explícito para esa relación.
Lo que sí falta es la relación **entre órdenes**: `ChainOutputAsConsumptionUseCase`
(PROC-12) ya crea el `MaterialConsumption` downstream a partir de un
`ProcessOutput` upstream, pero antes de PROC-18 esa relación solo quedaba
implícita en los valores compartidos (`product_id`, `lot_id`,
`quantity`/`weight`) — no era consultable como grafo.

## Entidad nueva: `ProcessGenealogyLink`

`backend/domain/meat_processing/entities/process_genealogy_link.py`. Arista
inmutable y polimórfica: `(upstream_entity_type, upstream_entity_id) →
(downstream_entity_type, downstream_entity_id)`, más `product_id`, `lot_id`
opcional, `quantity`/`weight`, `linked_by_user_id`. Sin FK en
`upstream_entity_id`/`downstream_entity_id` (es polimórfico — hoy solo
`ProcessOutput`/`MaterialConsumption`, pero el esquema no lo restringe para
no tener que migrar si en el futuro se enlazan otros tipos, p. ej. lotes de
Inventario). Se rechaza un enlace a sí mismo (mismo tipo + mismo id en
ambos lados).

## Punto de captura: `ChainOutputAsConsumptionUseCase`

Único punto donde PROC-18 escribe: cada vez que un output se encadena como
consumo de otra orden (PROC-12), además de crear el `MaterialConsumption` se
crea un `ProcessGenealogyLink` en la misma transacción
(`upstream=ProcessOutput`, `downstream=MaterialConsumption`), con el mismo
`operation_id`, `product_id`, `lot_id`, `quantity`/`weight` del output
origen.

## Consulta: `ProcessGenealogyQueryService`

`backend/application/meat_processing/queries/process_genealogy_query_service.py`
— servicio de solo lectura (no un Use Case: no autoriza, no muta, no abre
`MeatProcessingUnitOfWork`; construye directo sobre
`ProcessGenealogyLinkRepository`, igual que otros query services del repo).
No está sujeto al guardrail de
`tests/architecture/test_meat_processing_use_cases_are_authorized.py` porque
vive fuera de `use_cases/` (ese test solo recorre ese directorio).

- `get_upstream_links` / `get_downstream_links` — un salto.
- `trace_upstream` / `trace_downstream` — BFS multi-salto sobre
  `list_by_downstream`/`list_by_upstream`, con `max_depth` (default 10) para
  no recorrer un grafo corrupto/cíclico indefinidamente.
- `trace_lot_downstream(lot_id)` — recall (§38): parte de todos los enlaces
  que tocan ese lote y traza aguas abajo desde cada uno.

**Límite conocido y documentado, no un bug**: como el grafo solo enlaza
across-order (ver arriba), `trace_downstream` desde un `ProcessOutput` llega
hasta el `MaterialConsumption` que lo consumió y ahí se detiene — no sigue
automáticamente hacia los outputs que esa orden destino produjo después,
porque esa segunda relación (consumo de la orden B → outputs de la orden B)
no genera un enlace (comparten `processing_order_id`, por diseño). Un
recall end-to-end completo a través de varias órdenes requiere combinar
`ProcessGenealogyQueryService` con una consulta a
`MaterialConsumptionRepository.list_by_order`/`ProcessOutputRepository` por
cada orden intermedia — no implementado aquí porque no hay todavía un caso
de uso real que lo necesite (evitar over-engineering especulativo).

## Tests

`tests/unit/meat_processing/test_meat_processing_rework_and_genealogy_entities.py`
(parte de genealogía: 4 tests — tipos de entidad requeridos, rechazo de
auto-enlace, cantidad negativa rechazada, mismo id con tipos distintos
permitido).
`tests/integration/meat_processing/test_meat_processing_genealogy_query_service.py`
(6 tests): el enlace se guarda con la dirección correcta; upstream/downstream
de un salto; upstream/downstream cuando el mismo output se reutiliza en dos
cadenas distintas; sin enlaces devuelve vacío; recall por lote encuentra lo
esperado; lote sin enlaces devuelve vacío.
`tests/integration/meat_processing/test_meat_processing_output_use_cases.py::TestChainOutputAsConsumption`
actualizado (migración 251 añadida a su fixture) para cubrir que el enlace
se crea junto con el consumo.

## Migraciones

- `250_meat_processing_rework_schema` — tabla `rework_orders` (PROC-17, ver
  ese doc).
- `251_meat_processing_genealogy_schema` — tabla `process_genealogy_links`:
  índices en `upstream_entity_type+id`, `downstream_entity_type+id`,
  `lot_id`, `product_id`; sin FK (polimórfico).

## Pendiente

- Recall multi-orden end-to-end (ver límite conocido arriba) — no
  implementado hasta que exista un caso de uso real que lo requiera.
- Sin UI de trazabilidad todavía (fuera de alcance de esta fase).
- PROC-17 no crea enlaces de genealogía para el reproceso en sí (ver
  "Pendiente" en `PROC-17_reprocesos.md`).
