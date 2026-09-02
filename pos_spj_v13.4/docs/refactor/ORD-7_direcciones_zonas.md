# ORD-7 — Direcciones y zonas

Fecha: 2026-08-30. Alcance: master prompt §20 (direcciones), §21 (zonas), §22 (tarifas).

## Qué se construyó

- `GeocodingStatus` enum + `backend/domain/orders_delivery/address.py` — `OrderAddress`,
  entidad independiente (no embebida en `CustomerOrder`, referenciada por
  `delivery_address_id`) con su propio ciclo de vida de geocodificación
  (`mark_geocoded/mark_manual/mark_geocoding_failed`).
- `backend/domain/orders_delivery/delivery_zone.py` — `DeliveryZone` (postal_codes,
  minimum_order, delivery_fee, free_delivery_threshold).
- `backend/domain/orders_delivery/policies/delivery_fee_policy.py` — `DeliveryFeePolicy`:
  resuelve zona por código postal, valida pedido mínimo, calcula tarifa (con envío
  gratis sobre umbral). Pura — recibe la lista de zonas ya cargada, no consulta la BD.
- `CustomerOrder.set_delivery_address()`/`set_delivery_fee()` — este último SOLO toca
  `delivery_fee`/`totals`, nunca `unit_price_snapshot` de una línea (§22: Delivery no
  modifica precios de producto).
- Esquema: tablas nuevas `order_addresses`, `delivery_zones` (editadas directamente en la
  migración 226, mismo criterio que ORD-6: nada la ha consumido en producción todavía).
- `OrderAddressRepository`, `DeliveryZoneRepository`, wireados en `OrdersDeliveryUnitOfWork`.
- `SetOrderDeliveryAddressUseCase` — captura la dirección, resuelve zona SOLO si el
  `fulfillment_type` la requiere (HOME_DELIVERY/BRANCH_DELIVERY/WHOLESALE_DELIVERY/
  SCHEDULED_DELIVERY/EXPRESS_DELIVERY/ROUTE_DELIVERY), asigna tarifa.

## Decisiones

- **Sin fallback silencioso cuando no hay zona que cubra el código postal**: la primera
  versión de este caso de uso capturaba `DeliveryZoneNotAvailableError` y seguía
  silenciosamente sin tarifa — se corrigió antes de terminar la fase porque el prompt
  maestro prohíbe explícitamente "fallbacks silenciosos". Ahora, si el tipo de
  cumplimiento requiere zona y ninguna cubre el código postal, el caso de uso falla de
  forma visible (`DELIVERY_ZONE_NOT_AVAILABLE`). Un pedido COUNTER/PICKUP nunca intenta
  resolver zona — no es un fallback, es una regla de negocio explícita (esos tipos de
  cumplimiento no la necesitan).
- **Sin permiso granular nuevo para "dirección"**: el prompt maestro tampoco define uno en
  su propio §63; se reutiliza `ORDER_EDIT_DRAFT` (capturar dirección es parte de editar el
  pedido mientras es mutable).
- **`latitude`/`longitude` sí usan `REAL`** (única excepción a "nunca floats" de la Regla
  Cero): son coordenadas geográficas, no un valor de negocio Decimal (dinero/cantidad/
  peso/distancia) — `maximum_distance_km`, que sí es una distancia de negocio, se guarda
  como TEXT/Decimal.

## Tests

19 tests nuevos (12 dominio + 7 integración). Suite acumulada ORD-1..7: **112/112 pasando**.

## Pendiente

- Geocoding real (proveedor de mapas) no se construyó — solo el ciclo de estados del
  dominio. ORD-25/infraestructura futura conecta un `GeocodingPort` real.
- CRUD de zonas/tarifas vía Configuración (§72) no se construyó — solo lectura
  (`list_active_for_branch`) y creación directa vía repositorio en tests.
