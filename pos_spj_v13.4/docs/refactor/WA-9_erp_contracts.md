# WA-9 — ERP Contracts (canal WhatsApp)

Ejecutado: 2026-09-01. §52-53 del prompt maestro. **Decisión de producto
confirmada por el usuario antes de empezar esta fase** (pregunta directa,
dado el hallazgo de WA-0 de tres pipelines paralelas de pedidos por
WhatsApp): la pipeline autoritativa es el **microservicio oficial**
(`whatsapp_service/`, el que WA-1..8 vienen reconstruyendo), escribiendo
contra `ventas`/`detalles_venta`/`cotizaciones`/`anticipos`/`clientes` —
las mismas tablas que `ERPBridge` ya escribe hoy en producción. El stack
legacy ERP-embedded y Rasa quedan sin tocar, candidatos a retiro en una
fase posterior (WA-21).

## Hallazgo clave que cambió el alcance de la fase

`whatsapp_service/erp/gateways/*.py` y, sobre todo, `ERPBridge`
(`erp/bridge.py`) **ya son la implementación real** de casi todo lo que
§52 pide — `find_by_phone`/`create_minimal` (Customers),
`create`/`update_status`/`get_by_folio` (Orders),
`create`/`convert_to_order` (Quotes), `register_advance`/`confirm_payment`
(Payments), `check_stock`/`schedule` (Inventory/Delivery) — todos ya con
firmas de parámetro en `str` (no enteros), ya con manejo REST-first +
fallback SQLite (WA-1) documentado. `ProductMatcher`
(`parser/product_matcher.py`) ya hace búsqueda exacta→por-palabra→fuzzy
con stock/precio por sucursal. **WA-9 no construye contratos ERP desde
cero — envuelve lo que ya existe y funciona**, con dos aportes reales:

1. Puertos formales en `domain/whatsapp/erp_ports.py` (§52 — nombres en
   inglés: `CustomersApiClient`, `CatalogApiClient`, `OrdersApiClient`,
   `QuotesApiClient`, `PaymentsApiClient`, `DeliveryApiClient`,
   `LoyaltyApiClient` sin implementación) con `Ref` tipados
   (`CustomerRef`/`ProductRef`/`OrderRef`/`QuoteRef`) en vez de `Dict`
   crudo.
2. Adaptadores (`infrastructure/erp_clients/erp_bridge_clients.py`) que
   solo traducen forma — parámetros en inglés del puerto hacia los
   nombres en español que `ERPBridge` ya usa, `Dict` hacia `Ref` — nunca
   reimplementan una regla de negocio.

Sin puerto separado de Pricing/Inventory: `ProductRef.price`/`.stock` ya
cubre la necesidad real. `LoyaltyApiClient` queda solo como contrato — no
existe ningún gateway de fidelidad real en `erp/` para envolver.

## Degradación explícita, nunca silenciosa

`ERPBridge` abre su propia conexión SQLite (recibe una ruta, no una
conexión). `WhatsAppCompositionRoot._try_build_erp_bridge()` deriva esa
ruta de la MISMA conexión que el root ya tiene (`PRAGMA database_list`,
nunca de una constante global desconectada) y verifica que la tabla
`clientes` exista ahí antes de confiar en el bridge. Si algo falla —
típicamente en tests, que solo montan el esquema WA-3, sin `clientes`/
`ventas` — los 6 clientes ERP se registran como `UnavailableErpClient`:
cualquier método invocado lanza `ErpClientUnavailableError` explícito.
Nunca se omiten del registro en silencio (`dependency_graph_validator`
seguiría exigiéndolos) ni fingen un resultado vacío.

Verificado con **dos** escenarios reales, no solo mockeados:
- Conexión `:memory:` con solo el esquema WA-3 → los 6 clientes son
  `UnavailableErpClient`.
- Conexión a archivo temporal con esquema WA-3 **más** una tabla
  `clientes` mínima → `ERPBridge` real se construye, `root.customers` es
  `ErpBridgeCustomersApiClient` de verdad.
- Smoke test contra la base bootstrapeada completa (243 migraciones,
  `main.py` real): `root.customers`/`root.catalog` son las
  implementaciones reales, no el fallback.

CompositionRoot: +6 servicios — `REQUIRED_SERVICES` pasó de 14 a 20.

## Tests

38 tests nuevos, todos en verde: `test_unavailable_erp_client.py` (4),
`test_erp_bridge_clients.py` (17 — cada adaptador contra un `bridge`/
`matcher` falso, verificando solo la traducción de forma, no reprobando
lógica de negocio que ya vive en `ERPBridge`), `test_composition_root.py`
(+3 — degradación sin esquema legacy, construcción real con esquema
legacy presente). Suite completa: **443 passed, 11 failed** (mismos
preexistentes). Smoke test real: `/health` 200, y confirmado que
`root.customers`/`root.catalog` son las clases reales contra la base
bootstrapeada completa.

## Siguiente fase

WA-10 — Pedidos: Draft, selección de producto (ya tiene `CatalogApiClient`
para apoyarse), cantidad, método de entrega, confirmación, idempotencia
(`whatsapp_business_operation_idempotency`, WA-3, todavía sin
repositorio propio — construirlo es candidato natural de esta fase).
