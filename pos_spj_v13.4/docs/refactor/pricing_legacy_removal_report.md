# PRC-8 — Reporte de eliminación de legacy de Pricing / Costing

Cierre del contexto canónico de **Precios y Costos**: se neutraliza el motor de
precio legacy y se prepara el DROP diferido de las tablas de precio legacy. Su meta
operativa: **desbloquear PROD-19 pasos 4-10** dando a los lectores de
`productos.precio`/`costo` un destino canónico (`PricingReadFacade` /
`ProductPriceQueryService` / `ProductCostQueryService`).

## 1. Motor de precio: reescrito, no parcheado

`core/services/pricing_service.py` (158 líneas, `producto_id:int`, precios float,
SQL sobre `productos.precio`/`precios_lista`/`precios_volumen`/`clientes_lista_
precio`) → **shim delgado (60 líneas)** que delega en
`ProductPriceQueryService.get_sale_price` (UUIDv7 + Money/Decimal, prioridad
volumen > lista cliente > lista > base). Conserva el contrato dict que consume
`sales_service` (`precio`/`precio_base`/`fuente`/`lista_id`/`descuento_pct`;
`fuente == 'base'` = sin override). Métodos de gestión legacy (`set_precio_lista`,
`set_precio_volumen`, `asignar_lista_cliente`, `get_listas`,
`get_precios_producto`) eran **código muerto** (sin consumidores) → eliminados.

Único consumidor vivo: `sales_service.get_precio(...)` (checkout POS) → ahora lee
del canónico. `app_container` sigue construyendo `PricingService(db)` sin cambios.

## 2. Tablas legacy de precio → DROP diferido

`migrations/deferred/legacy_pricing_drop.py` (NO registrado en `engine.py`,
env-guard `PRICING_ALLOW_LEGACY_DROP=1`) elimina:

| Tabla legacy | Reemplazo canónico |
| ------------ | ------------------ |
| `listas_precio` | `price_list` |
| `precios_lista` | `product_price` |
| `precios_volumen` | `volume_price` |
| `clientes_lista_precio` | `customer_price_list` |
| `historial_precios` (+ triggers `trg_historial_precio_venta`/`_compra`) | `price_change_log` |

Backfilladas por la migración **150** (PRC-5). Tras el shim (§1) ninguna ruta viva
las lee, por lo que el DROP es seguro y **no depende de PROD-19**.

## 3. Columnas de precio/costo en `productos` (residual → PROD-19)

`productos.precio` / `precio_compra` / `precio_minimo_venta` / `costo` /
`costo_promedio` NO se eliminan aquí: viven en el maestro `productos` y los borra el
corte de Productos (`legacy_products_drop.py`, PROD-19) al dropear `productos`.

Lectores directos restantes (BI, forecast, reportes, merma, fidelidad, delivery,
activos) siguen leyendo la **columna** `productos.precio`/`precio_compra` hasta que
PROD-19 los fuerce a repuntar a `PricingReadFacade`. El motor de precio canónico
(§1) y el facade ya existen como destino → **PROD-19 pasos 4-10 desbloqueados**.

## 4. Guardrail de refuerzo

`tests/architecture/test_no_new_legacy_pricing_reads.py`: ningún archivo **nuevo**
puede leer las 5 tablas de precio legacy; los lectores actuales (columnas de
`productos`) quedan en allowlist explícita y sólo pueden decrecer (ratchet), nunca
crecer.

## 5. Estado

- [x] `pricing_service` delega en el canónico (sin SQL legacy de precio).
- [x] DROP diferido de 5 tablas legacy de precio + 2 triggers (env-guard).
- [x] Guardrail anti-regresión + allowlist.
- [x] Suite pricing + `sales_service` verdes; bootstrap limpio.
- [ ] DROP ejecutado (manual, en el corte final junto con PROD-19).
- [ ] Repunte físico de lectores de `productos.precio` (PROD-19 pasos 4-10).
