# Auditoría de producción cárnica 32cfbf — respuesta (2026-10-16)

Auditoría externa estática sobre el commit `32cfbf27`. Cada hallazgo se verificó
contra el código y se midió en una **copia de la base real** recorriendo el
flujo completo (`scratchpad/realdb_meat_flow.py`, `realdb_meat_direct.py`).
Migración **343**. Sin commitear.

## Medido en la base real

«Pollo Entero» tiene un perfil de rendimiento ACTIVO (8 salidas que suman
100 %) y 132.68 kg en existencia, sin esquema de corte, sin recetas y sin
órdenes. Al recorrer el flujo aparecieron **tres bloqueos que la auditoría no
vio**, cada uno suficiente para que no se pudiera producir:

1. **Ningún almacén marcado «Producción».** «Crear orden» fallaba con ese
   motivo, pero sólo DESPUÉS de cerrar el diálogo (perdiendo lo capturado).
   Es configuración del usuario: no se toca, ahora se dice al abrir.
2. **La política exigía esquema de corte** aunque el adaptador sabía despiezar
   con el perfil: un producto con perfil activo nunca podía prepararse.
3. **Los 4 lotes de compra nacieron «pendiente de inspección»** aunque ningún
   producto exige inspección, y Producción sólo reserva lotes liberados.

## Hallazgo por hallazgo

| # | Hallazgo | Estado | Qué se hizo |
|---|----------|--------|-------------|
| P0 | Selección efímera del producto; el diálogo se aceptaba incompleto | Confirmado y corregido | `SearchSelector(keep_selection=True)` retiene la opción elegida (clic o Intro), muestra su etiqueta y la olvida al volver a escribir; Intro sin renglón resaltado elige el único resultado. «Nueva orden» y «Línea del plan» validan antes de cerrar y muestran el motivo en el diálogo; sin almacén de producción el botón queda deshabilitado con el aviso. |
| P1 | Búsqueda vacía = filtro de catálogo | Verificado | En la base real el pollo sí aparece; el explicador de vacío ya existía. |
| P1 | % y kg esperados podían contradecirse | Corregido (decisión: **el perfil manda**) | Despiece exige perfil de rendimiento (no esquema). kg = entrada × % / 100 y el % mostrado es el mismo. Si hay esquema debe coincidir (±0.01 %) o la orden no se congela y se dice qué salida difiere, por nombre. |
| P1 | Falta la operación directa Compras → transformación → Inventario | Construido (decisión: **permiso propio**) | «Transformación directa»: ver abajo. |
| P1 | Doble efecto de la explosión de receta al comprar | Corregido (decisión: **quitarla**) | Se retiró `CanonicalPurchaseRecipeExplosionHandler` (explotaba recetas de cualquier tipo con negativo permitido). Compras registra lo recibido; la transformación se registra una vez, en Producción. Guardia en `test_inventory_legacy_recipe_handler_retired.py`. |
| P2 | Pesos reales precargados con lo esperado | Corregido (decisión: **vacíos; estimado explícito**) | Los campos quedan vacíos («Sin pesar»; vacío ≠ 0). «Usar lo esperado en las vacías» marca esas salidas ESTIMADO, exige motivo y queda en `processing_output_results.weight_source/estimate_reason` y en la auditoría. |
| — | Lotes de compra «pendiente de inspección» sin necesitarla | Corregido | El lote nace LIBERADO cuando el renglón entra disponible (misma regla de la recepción: el perfil de calidad pide inspección). La 343 repara los existentes. |
| — | Mensaje de Costos con UUIDs («sin precio de venta: 01a0d678…») | Corregido | El adaptador nombra los productos y dice dónde capturar el precio. |

## Transformación directa

Ruta nueva `mp_direct_transformation` (permiso
`PRODUCCION.transformacion_directa.ejecutar`, sembrado por la 343 a los roles
que pueden iniciar órdenes).

1. **Origen:** lotes disponibles en el almacén de producción de productos con
   perfil activo, con folio de recepción, proveedor, fecha y kg disponibles.
   Los que Calidad no liberó se muestran con el motivo.
2. **Captura:** kg de entrada (≤ disponible), lo esperado por salida (sólo
   lectura, de la MISMA foto que congela «Preparar»), peso real vacío, balance
   `entrada = existencia + merma + diferencia sin clasificar`.
3. **Una acción:** `ExecuteDirectTransformationUseCase` crea la orden
   (`source_type=DIRECT_TRANSFORMATION`, `source_reference_id`=lote), la autoriza
   por su permiso (sin segundo aprobador: `approved_by_user_id` queda vacío y la
   auditoría registra `APPROVED_BY_DIRECT_TRANSFORMATION`), prepara reservando
   EXACTAMENTE ese lote (`MANUAL_AUTHORIZED`), libera y ejecuta con el motor de
   siempre (consumo, cortes con lote hijo, calidad, costeo, merma, cierre).
4. **Delegación acotada:** las etapas corren con
   `DirectTransformationStageAuthorization` (lista explícita); sobrescribir
   rendimiento, consumo o peso manual, decidir calidad, cancelar o reversar
   siguen exigiendo su permiso. La desviación fuera de tolerancia la autoriza
   OTRO usuario con `YIELD_OVERRIDE`.
5. **Idempotente y reanudable:** `direct_transformations` guarda la orden y el
   UUIDv7 de cada etapa; si algo falla la orden queda en Órdenes y repetir con el
   mismo `operation_id` continúa.

Verificado en la copia real: 20 kg de pollo → orden `OP-COR-00001` CERRADA, lote
de 132.68 → 112.68 kg, 7 cortes con lote hijo, la menudencia como merma (no entra
a existencia), costeo asignado, auditoría completa. Requirió marcar el almacén
«Producción» y precio de venta en 4 cortes (reparto por valor de venta).

## Pruebas

`tests/integration/meat_processing/test_production_audit_32cfbf.py` (20). Las
fixtures de despiece (`Planta.despiece`) crean ahora esquema **y** su perfil
equivalente (`active_yield_profile`).

## Pendiente / decisiones abiertas

* **Reversa** de una transformación directa (la auditoría la propone): no
  construida; hoy se usa la reversa de la orden si existe para el caso.
* El `lot_code` de compra es `<folio>-P<uuid del producto>`; la pantalla muestra
  el folio de recepción en su lugar. Cambiar la regla del código es otra decisión.
* Dos fallas de Cárnico que ya existían en HEAD y no se tocaron:
  `test_cost_projection_updates_product_average_cost` (promedio 113.33 vs 120) y
  `test_meat_processing_overview` (la página no muestra un contador).
