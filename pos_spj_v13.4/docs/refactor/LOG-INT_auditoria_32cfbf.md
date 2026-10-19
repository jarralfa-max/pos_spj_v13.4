# Integración Logística · Compras · Transferencias · Producción · POS · Instalador — Fase A (auditoría)

Rama `claude/erp-financial-bounded-context-uqxz6b`, commit `32cfbf27` + árbol de
trabajo (incluye la respuesta a la auditoría de Producción 32cfbf, sin commitear).
Auditoría leyendo código, composición y pruebas reales; nada se infirió de reportes.

## 1. Matriz (estado real → acción)

| Área | Archivo / símbolo | Estado real | Consumidor | Permiso | Dueño del dato | Acción |
|------|-------------------|-------------|------------|---------|----------------|--------|
| Logística | `application/logistics/service.py` `LogisticsApplicationService` | Implementado: tipos, contenedores, embarque, adjuntar, cargar, sellar, despachar, llegada, conteo, cierre, varianza, etiqueta | Compras («Compra en origen»), PWA | `LOGISTICA.*` | Logística | **REUSAR**; corregir `close_shipment` (op. derivada `f"{op}:{container}"`) y añadir segregación despacho≠recepción |
| Logística | `composition.py` `build_logistics_services` | Implementado; sólo lo llama la composición de Compras | Compras | sesión | — | **REUSAR** desde la nueva página |
| Logística | `wiring.py` `wire_logistics` | **Sin conectar** (nadie lo llama; nadie publica `LOGISTICS_SHIPMENT_CREATE_REQUESTED`) | — | — | — | **RETIRAR** o conectar sólo si un productor real lo necesita |
| Logística | `origin_purchase_workspace.py` | Implementado; exige documento; `receive_and_close` usa `uuid5` para la operación de cada recepción | `LogisticsRelatedPage` | `LOGISTICA.*`/`COMPRAS.*` | Logística/Compras | **EXTENDER** («Nueva recolección»: desde PO / compra directa); **reemplazar uuid5** por operación UUIDv7 persistida por (embarque, documento) |
| Logística | `queries.py` `loadable_documents` | Implementado: PO aprobada/enviada, compra directa `CONFIRMED`+`SUPPLIER_PICKUP`, requisición; SQL directo a tablas de Compras | workspace | — | Compras | **EXTENDER** (motivo por el que un documento no aparece); el SQL entre contextos queda anotado como deuda |
| Logística UI | Catálogo de contenedores | **No existe**: alta sólo dentro de un embarque abierto (`_disable_all` deshabilita «Registrar» sin embarque); sin lista, edición, historial ni reimpresión | — | `LOGISTICA.contenedor.*` | Logística | **CREAR** página Logística → Contenedores reutilizando servicio/QR/`ContainerRegisterDialog` |
| Logística UI | Módulo propio en el shell | **No existe**: Logística sólo vive como página de Compras | — | — | — | **CREAR** módulo `logistics` (Contenedores, Embarques) y **enlazar** «Compra en origen» (no duplicarla) |
| Logística | Acta provisional de custodia sin documento | **No existe** | — | — | Logística | **CREAR sólo si se decide** (ver decisiones) |
| API/PWA | `api/main.py` `create_app()` | Monta routers y PWA, **no inyecta** `mobile_session_service` ni `origin_purchase_workflow` → 503; **nadie hospeda la API** en producción | pruebas | — | — | **CREAR host** (decisión) |
| API/PWA | `logistics/mobile_workflow.py` | Implementado sólo para carga en origen (sin llegada/conteo) | router móvil | sesión móvil | Logística | **REUSAR**; extender a llegada si se despliega |
| Compras | compra directa `SUPPLIER_PICKUP` | Implementado (confirmar con recolección); se crea en Compras → Compra rápida | workspace | `COMPRAS.*` | Compras | **REUSAR**: lanzar el mismo caso de uso desde «Nueva recolección» |
| Transferencias | `application/transfers/use_cases/*` (solicitud, aprobación, surtido, empaque, despacho, recepción, recepción ciega, diferencias, devoluciones) + `CanonicalInventoryTransferGateway` | **Implementado, sin conectar a la UI** | — | `TRANSFERS_*` (planos) | Transferencias/Inventario | **EXTENDER** `transfers_factory`/presenter: cablear aprobar→surtir→despachar→recibir con su gateway; las ~16 páginas existen |
| Transferencias | `infrastructure/desktop/transfers_factory.py` | Sólo `create_transfer_request` | `TransfersPresenter` | — | — | **EXTENDER** |
| Producción | Selector, perfil-manda, transformación directa, pesos estimados | **Hecho** (auditoría 32cfbf, migr. 343) | Producción | `PRODUCCION.*` | Producción | **REUSAR**; añadir acceso contextual desde la recepción |
| POS | `SalesFulfillmentQueryService` (SALES_EXPLOSION / combo VIRTUAL) | Implementado: el combo reserva y consume componentes | `SalesInventoryClient` | `VENTAS.*` | Productos/POS | **REUSAR** |
| POS | `ReconstructBaseProductUseCase` vía `_top_up_via_reconstruction_if_short` | Implementado, **semántica física al reservar**: consume partes y produce un entero (`PRODUCTION_OUTPUT`) en DOS commits; si falla el segundo quedan partes consumidas sin salida; corre al reservar (si la venta se cancela el entero queda en existencia); postea en `to_location_id=branch_id`; ids `f"{sale}:reconstruct:{pid}"`; commitea por su cuenta dentro de la transacción del cobro | POS | `INVENTARIO.reserva.crear` | Inventario | **DECIDIR** semántica (virtual vs física) y corregir atomicidad |
| Instalador | `install_profile.py` | `LOGISTICA` pertenece a `orders_delivery`; sin capacidad `logistics` | shell/router | — | — | **EXTENDER** (capacidad `logistics`, migración de perfiles existentes sin quitar accesos) |
| Instalador | `spj.spec` | `collect_data_files("frontend")` ya incluye `frontend/web/logistics`; no empaqueta host de API | build | — | — | **EXTENDER** sólo si se decide hospedar la API |

## 2. Fuentes de verdad y doble contabilización

- Inventario es la única fuente de saldo: compra → `PURCHASE_STOCK_ENTRY_REGISTERED` → `CanonicalPurchaseStockEntryHandler` (una vía). La explosión de receta al comprar ya se retiró (32cfbf). El embarque recibe por el caso de uso de Compras (una recepción por documento) → no hay doble movimiento.
- Riesgo vigente: la reconstrucción de producto base produce existencia de un entero que nunca se armó físicamente.
- Cuarentena: con la corrección de 32cfbf, el lote nace liberado sólo si el producto no exige inspección; si la exige, el saldo entra `PENDING_INSPECTION` y no es vendible ni transformable.

## 3. Identidades derivadas a corregir

`origin_purchase_workspace.receive_and_close` (`uuid5`), `LogisticsApplicationService.close_shipment` (`f"{op}:{container}"`), `ReconstructBaseProductUseCase` (`f"{op}:consume|:produce|:fulfill:{i}"`), `SalesInventoryClient` (`f"{sale}:reconstruct:{pid}"`). Se sustituyen por operaciones UUIDv7 persistidas por clave de negocio (reintento seguro sin derivar).

## 4. Plan por fases

- **B** — hecho (selector, perfil manda).
- **C** — Módulo Logística en el shell (Contenedores: lista, alta/edición, historial, reimpresión, motivo de no-cargable; Embarques) enlazando «Compra en origen»; «Nueva recolección» (desde PO / compra directa con `SUPPLIER_PICKUP` por el caso de uso de Compras); operaciones persistidas en lugar de uuid5/concatenación; segregación despacho≠recepción.
- **D** — Transferencias: cablear aprobar→surtir→despachar→recibir (+diferencias) con `CanonicalInventoryTransferGateway`; prueba de que no genera compra ni CxP.
- **E** — hecho; añadir «Transformar» contextual desde la recepción.
- **F** — POS: semántica de producto base según decisión; atomicidad dentro de la transacción del cobro.
- **G** — capacidad `logistics` en el instalador (migración de perfiles); host de API/PWA según decisión.

## 5. Implementación (2026-10-16, sin commitear)

Decisiones del usuario: producto base por **composición virtual**; API/PWA como **servicio local opcional**; **sin acta provisional** (sin documento no hay carga: siempre compra directa); `logistics` como **capacidad propia**.

### C — Logística
- Módulo propio en el shell (`frontend/desktop/modules/logistics/`, `nav.logistics`): Contenedores (lista, alta, edición, estado operativo, historial, reimpresión de etiqueta, motivo por el que no se puede cargar), Embarques, y «Compra en origen» **enlazada** (misma página de Compras vía `build_enterprise_presenter`, no una copia).
- `ContainerCatalogService` es la única puerta al catálogo; `LogisticsContainerQueryService` explica la no-cargabilidad.
- «Nueva recolección sin orden de compra» abre la compra directa de Compras y continúa con `SUPPLIER_PICKUP` (mismo caso de uso; nada nuevo en Compras).
- Identidades: recepción por clave de negocio (embarque, tipo, documento) + `new_uuid()` en lugar de `uuid5`; eventos de custodia de `close_shipment` con UUIDv7.
- Segregación: quien despacha no registra la llegada salvo `LOGISTICA.embarque.forzar`; `dispatch` deja auditoría `DISPATCHED`.
- Etiqueta de contenedor como `DocumentType.CONTAINER_LABEL` por el pipeline de impresión.

### D — Transferencias
- Ciclo completo cableado: enviar a aprobación → aprobar/rechazar → reservar → surtir → listo → despachar (con clave de quien verifica) → recibir (rechazado → cuarentena; con calidad → `PENDING_INSPECTION`).
- `CanonicalInventoryTransferGateway` con adaptadores reales (`transfers_inventory_gateway.py`); `TRANSFERS_GRANT` y `ReserveStockForTransferUseCase`.
- `TransferCycleService` (aplicación) es dueño de la atomicidad; la UI no hace commit/rollback. No genera compra ni CxP (probado).
- Devoluciones de transferencia: `TransferReturnNotWired` — explícito, no silencioso.

### F — POS
- El faltante de un producto base se surte con las partes de su esquema reversible (sin merma); la disponibilidad cuenta las reservas de la propia venta; el costo de venta se pondera por lo que realmente salió; la devolución restaura las partes.
- Todo o nada: sólo se compone si TODAS las partes alcanzan; si no, no se retiene ninguna parte y la línea queda con su faltante del producto base (autorización sin existencia en el cobro).
- Las partes las define Productos (`SalesFulfillmentQueryService.reversible_parts`); Ventas no lee el esquema de corte por su cuenta.
- `ReconstructBaseProductUseCase` retirado (ya no se fabrica un entero inexistente ni hay dos commits fuera de la transacción del cobro).

### G — Instalador y API
- Capacidad `logistics` (`CAPABILITY_CATALOG_VERSION = 2`); `orders_delivery` conserva sólo DELIVERY; instalaciones personalizadas antiguas con `orders_delivery` reciben `logistics` (no se pierde acceso). El `.iss` guarda la versión del catálogo.
- `spj_api.exe` (`backend/api/service_host.py`): servicio de Windows «SPJMobileAPI», componente **opcional** `mobile_api`, sólo en instalación para todos los usuarios; escucha en `127.0.0.1` por omisión; configuración en `<datos>/mobile_api/mobile_api.env`; secreto HMAC persistente en el almacén de secretos; login real (`DatabaseMobileCredentialVerifier`) que exige `LOGISTICA.embarque.ver`; solicitudes serializadas (una conexión SQLite por proceso).
- Corregido al probar: los permisos de la sesión llegaban en MAYÚSCULAS y el flujo móvil comparaba exacto → toda acción respondía 403.

## 6. Procedimiento operativo sin orden de compra

1. Compras/Logística → «Nueva recolección sin orden de compra».
2. Capturar la compra directa (proveedor, productos, pago) y confirmarla con **recolección en proveedor**.
3. Abrir el embarque desde esa compra, cargar contenedores (escritorio o teléfono), sellar y despachar.
4. En destino, **otra persona** registra la llegada, cuenta/pesa y cierra; la recepción de Compras genera la entrada de inventario (una sola vía) y la CxP/pago según la compra.
5. Si el producto exige inspección, el saldo queda `PENDING_INSPECTION` hasta liberarlo.

## 7. Riesgos y pendientes

- **El instalador no se ha probado en Windows** con los cambios (componente `mobile_api`, `spj_api.exe`, migración de capacidades). Requiere build + instalación real antes de publicar.
- La PWA cubre la carga en origen; **llegada/conteo desde el teléfono no existe** (se hace en escritorio).
- Devoluciones de transferencia sin cablear (`TransferReturnNotWired`).
- «Transformar» contextual desde la recepción no se agregó (la transformación directa se abre desde Producción).
- Fuera de loopback, la API debe configurarse con TLS (`SPJ_API_SSL_CERTFILE`); el host lo advierte en el log.
- `tests/integration/test_phase0_phase1_scaffolding.py` falla desde INST-0 (3983fe70): exige `backend/infrastructure/updater/version_checker.py` y `update_installer.py`, retirados en ese commit.
