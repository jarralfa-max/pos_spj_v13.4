# PROC-27 — Trazabilidad y Resumen: dos rutas que dejan de ser placeholder

Estado: **rutas reales 14 → 16 de 29** (el resto, medido abajo). Esta fase no
construye dominio nuevo: conecta a la UI dos servicios que ya existían y uno de
los cuales no tenía **ningún** consumidor en producción.

## Punto de partida (medido, no supuesto)

`tests/architecture/test_placeholder_routes_ratchet.py` contaba 14 rutas reales
para `meat_processing` contra 29 declaradas en `MEAT_PROCESSING_NAV`. De las 15
restantes, 10 son de sacrificio (detrás de `slaughter_features_enabled`, sin
tablas) y 5 eran pantallas operativas sin página: Resumen, Plan de producción,
Trazabilidad, Alertas y Análisis.

## Trazabilidad (`mp_traceability`)

`MeatLotTraceabilityQueryService` **compone**, no reimplementa:

| Pregunta | Quién la responde |
|---|---|
| ¿Qué lotes produjo esta sucursal? | `processing_output_results` (la misma tabla de Rendimientos → Por corte) |
| ¿De qué lote de entrada salió? | `processing_output_results.input_lot_id` |
| ¿A dónde fue el lote? | `TraceabilityQueryService` de **Inventario** (`recall_report` + `trace_upstream`) |
| ¿Qué otra orden lo consumió? | `ProcessGenealogyQueryService` de Cárnico (PROC-18) |

Dos decisiones que conviene no revertir:

1. **La genealogía de lotes es de Inventario.** Es quien guarda
   `inventory_traceability_link` y quien recibe los enlaces que registra el
   adaptador de recepción de producción. Un segundo grafo en Cárnico habría
   dado dos respuestas distintas a la misma pregunta.
2. **El grafo entre órdenes de PROC-18 sí es de Cárnico**, y estaba a oscuras:
   `ProcessGenealogyQueryService` existía desde PROC-18 con pruebas propias y
   **cero llamadores en producción**. La sección "Se consumió en otra orden" es
   su primer consumidor real. La ORDEN la decide la búsqueda del consumo en
   `material_consumptions`, no el `downstream_entity_type` declarado en el
   enlace: el grafo es polimórfico a propósito y lo que no es un consumo no se
   traduce a una orden inventada.

Un lote que no produjo la sucursal **no se traza**: la pantalla lo dice, en vez
de enseñar la producción de otra sucursal.

## Resumen (`mp_overview`)

`MeatProcessingOverviewQueryService` reusa
`MeatProcessingBadgeQueryService` para los cinco contadores de "por atender", de
modo que el badge del sidebar, la lista del registro y la tarjeta del Resumen
**no pueden decir tres números distintos del mismo hecho**. Lo propio del
Resumen es la foto del periodo: órdenes por estado (en el orden del ciclo de
vida, no alfabético) y peso por tipo de salida en los últimos N días.

Los pesos se suman con `Decimal` en Python y no con `SUM(CAST(... AS REAL))`:
el esquema guarda los decimales como TEXTO justamente para no perder precisión,
y una prueba fija que tres salidas de `0.1` suman `0.3`.

No se revalida el vocabulario de estados ni de tipos de salida: el `CHECK` del
esquema ya lo restringe. Una prueba fija esa garantía, para que si la base
dejara de restringirlo se note.

`ORDER_STATUS_LABELS` (antes `_STATUS_ES`, privado de
`processing_order_presenter`) se hizo público para que Órdenes y Resumen llamen
igual al mismo estado. El nombre viejo queda como alias.

## Lo que sigue pendiente (medido)

| Ruta | Por qué no se construyó |
|---|---|
| `mp_alerts` | No hay productor de alertas: `critical_alerts` no se calcula y las excepciones sólo quedan en auditoría, sin estado de "atendida". Una pantalla vacía sería funcionalidad falsa. |
| `mp_production_plan` | No hay persistencia del plan. |
| `mp_analytics` | Requiere un servicio de tendencias que no existe. |
| 10 rutas de sacrificio | Sin tablas; `SLAUGHTER_ENABLED = False`. |

## Hallazgos que NO se tocaron

- **Los tipos de proceso se llaman distinto en dos pantallas**:
  `PROCESS_TYPE_LABELS` (registros) dice "Deshuese" y "Limpieza" donde
  `_PROCESS_TYPE_ES` (órdenes) dice "Deshuesado" y "Recorte". Son dos tablas
  para el mismo vocabulario y hay que elegir una redacción — es una decisión de
  terminología, no de código.
- `mark_pending_settlement` sigue sin llamadores y el badge `open_incidents`
  sigue sin productor (ver PROC-26).
- PROC-23 y PROC-25 dicen que el botón del sidebar global todavía abre el
  legacy `modulos/produccion.py`. **Ya no es cierto**: ni ese archivo ni
  `interfaz/menu_lateral.py` existen, y el módulo canónico está registrado en
  `desktop_shell_window_composition.py`. Esos dos documentos están vencidos en
  ese punto.

## Pruebas

- `tests/integration/meat_processing/test_meat_traceability.py` (16)
- `tests/integration/meat_processing/test_meat_processing_overview.py` (18)

Ambas verticales pasaron mutación completa: 16 y 18 mutaciones aplicadas una a
una, todas mueren, control verde antes y después.
