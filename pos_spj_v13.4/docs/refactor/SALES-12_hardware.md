# SALES-12 — Hardware (POS-12 del master prompt)

Fecha: 2026-08-17
Fase anterior: `SALES-11_pricing_beneficios.md`.

## Alcance ejecutado

Master prompt §67, fase POS-12: "Scanner. Printer. Scale. Terminal. Drawer. Customer
display. Tests." (el usuario añadió "Printer" explícitamente a la lista de esta fase,
además de los cinco dispositivos que el propio prompt maestro nombra en §67).

Investigué primero (agente de research, sin escritura de archivos) qué existe
realmente detrás de cada uno de los seis dispositivos antes de diseñar nada — el
resultado corrigió el propio framing de SALES-0/SALES-11 en varios puntos.

## La frontera real, confirmada por investigación

| Dispositivo | Estado real encontrado |
|---|---|
| **Cajón de dinero** | Dos rutas reales coexisten: la legacy `HardwareService.open_cash_drawer()` (booleana, sin auditoría) que `modulos/ventas.py` llama hoy, y una más completa en el bounded context de Caja — `OpenCashDrawerUseCase` (auditada, permisos `CashPermissions.DRAWER_OPEN`/`DRAWER_OPEN_WITHOUT_SALE`, evento `CASH_DRAWER_OPENED`). Se eligió envolver la segunda: es la arquitectura objetivo real, no una fachada sobre nada. |
| **Terminal de pago** | SALES-0/SALES-11 la habían clasificado "100% trabajo nuevo" — desactualizado. Existe un triple Protocol/driver/use-case real (`backend/application/cash_register/hardware.py::PaymentTerminalGateway` + `hardware_use_cases.py::ChargePaymentTerminalUseCase`), construido recientemente por una sesión concurrente (commits "Refactir de modulo de Caja"). Auditada y permisos-gateada igual que el cajón. Sigue sin existir ningún SDK de adquirente real — no se fabricó uno. |
| **Báscula** | `ScaleGateway` (Protocol nuevo, `backend/infrastructure/hardware/scale_gateway.py`) no tiene ninguna implementación real con puerto serie. El único lector real es el legacy `HardwareService.read_scale()` — confirmado que `modulos/ventas.py::leer_peso()` ya lo intenta primero (COM3 directo es un *fallback* condicional, no lo ignora, corrección al framing de SALES-0). Se construyó un adaptador que implementa el Protocol nuevo delegando la lectura real al driver legacy — un solo driver real, dos fachadas conformes al Protocol. |
| **Impresora de tickets** | `core.services.printer_service.PrinterService`/`PrintQueue` confirmado completo, en producción (`modulos/ventas.py::_imprimir_ticket_consolidado` lo llama hoy), con su propio reintento/auditoría/notificación por EventBus. No necesita integrarse con `sales_outbox` — son problemas distintos (outbox informa a otros bounded contexts que una venta cambió; la impresora es un efecto físico directo). Se reutiliza tal cual. |
| **Escáner** | Tres mecanismos paralelos reales, no dos como creía SALES-0: `LectorQR`/`LectorQRSerial` (sin uso real), `_ScanContextFilter` (solo seguimiento de foco) y un `_scanner_timer` separado (buffering/timing real, configurado desde `hardware_config`). Ninguno comparte vocabulario de despacho con los otros. Convergerlos a nivel de widget queda fuera de alcance (esta pipeline no toca `modulos/ventas.py` salvo fixes puntuales justificados) — lo que sí se construyó es el punto de despacho normalizado a nivel de aplicación. |
| **Pantalla de cliente** | 100% sin construir, cero referencias en todo el repositorio (confirmado por investigación). Master prompt §6/§50: Ventas solo PUBLICA estado para este dispositivo, nunca lo controla — no se fabricó ningún consumidor/hardware inexistente. |
| **`DeviceHealthQueryService`** | Nombrado por el prompt maestro, 100% inexistente. El vecino más cercano (`CashDeviceQueryService`) responde una pregunta distinta (lista administrativa de dispositivos, no un resumen en vivo para la barra del cajero). |

Fabricar un SDK de adquirente de pagos o un consumidor de pantalla de cliente
habría sido exactamente el tipo de infraestructura decorativa que esta pipeline ya
se ha negado a construir repetidamente sin un punto de integración real (el
dispatcher de outbox nunca construido en SALES-4/5/9, el motor de Promociones
nunca construido en SALES-11).

## Entregables

**Dominio** (`backend/domain/sales/`):
- `enums.py::ScanContext` — `PRODUCT`/`CUSTOMER_CARD`/`AUTO`, el vocabulario de
  despacho normalizado independiente de cuál de los tres mecanismos de escáner
  produjo el código crudo.
- `exceptions.py::ScanCodeNotResolvedError` — un código escaneado que no
  coincide ni con un producto vendible ni con una tarjeta de cliente/fidelidad.
  Registrado en `result.py::_ERROR_CODES` (`"SCAN_CODE_NOT_RESOLVED"`) desde el
  principio — sin repetir la omisión encontrada en SALES-9/10.

**Infraestructura** (`backend/infrastructure/integrations/`, mismo patrón que
`sales_inventory_client.py`/`sales_pricing_client.py`):
- `sales_cash_drawer_client.py::SalesCashDrawerGateway` — envuelve
  `OpenCashDrawerUseCase` de Caja (real, no la ruta legacy booleana).
- `sales_payment_terminal_client.py::SalesPaymentTerminalClient` — envuelve
  `ChargePaymentTerminalUseCase` de Caja. Docstring explícito: "hardware
  boundary only" — el resultado no muta el estado de pago de la venta aquí,
  eso es responsabilidad de una fase futura de checkout/pago (§30-36).
- `sales_scale_client.py::SalesScaleGateway` — implementa el `ScaleGateway`
  Protocol de Inventory delegando a `HardwareService.read_scale()`. Traduce el
  centinela legacy `0.0` ("sin lectura válida") a `InvalidCatchWeightError`,
  igual que `StubScaleGateway.read()` cuando su cola está vacía.
- `sales_receipt_client.py::SalesReceiptClient` — construye el dict
  `ticket_data` que `PrinterService.print_ticket()` ya espera (verificado
  contra los call sites reales en `modulos/ventas.py`, no adivinado) a partir
  de un `SaleDTO`. Única frontera Decimal→float de este archivo, mismo criterio
  que `SalesInventoryClient`/`SalesLoyaltyClient`.

**Aplicación** (`backend/application/sales/`):
- `dto.py` — `CustomerDisplayLineDTO`/`CustomerDisplayStateDTO` y
  `DeviceHealthDTO`.
- `queries/catalog_query_service.py::SalesCatalogQueryService.find_by_code` —
  resolución exacta por SKU/código de barras (distinto de `search()`, que hace
  `LIKE` difuso pensado para la grilla del catálogo).
- `use_cases/scan_use_cases.py::ScanCodeRouter` — dado un código + contexto,
  decide: `PRODUCT`/`AUTO` con match → `AddSaleLineUseCase` (cantidad 1, precio
  resuelto del catálogo); si no hay match de producto y el contexto lo permite
  → `ScanLoyaltyCardForSaleUseCase` (SALES-10, sin duplicar su lógica).
- `queries/customer_display_query_service.py::CustomerDisplayQueryService` —
  proyección de solo lectura de "qué debería mostrar la pantalla del cliente
  ahora mismo", compuesta desde el propio `Sale` (nunca desde `sales_outbox`,
  que es un log de eventos, no una proyección de estado). Un futuro consumidor
  real puede sondear esta query o suscribirse al stream de outbox ya existente
  (cada mutación de carrito ya encola `SaleEvents.LINE_ADDED` etc. desde
  SALES-6 — no se necesitó nueva plomería para esa mitad).
- `queries/device_health_query_service.py::DeviceHealthQueryService` — lee
  `hardware_config` directamente (la única fuente canónica real que ya leen
  `HardwareService`/`PrinterService`) y reporta `configured` honestamente: fila
  presente, activa, con destino de transporte. `terminal_pago`/
  `customer_display` no tienen fila sembrada en ningún lado del repositorio
  (verificado contra `migrations/m050_hardware_config_canonical.py`) — se
  reportan como no configurados, que es la verdad, no una limitación de esta
  query.

**Permisos**: cero cambios en `permission_catalog.py`. SALES-2 ya había
registrado `POS.cajon.abrir_manual`, `POS.bascula.usar` y
`POS.dispositivo.diagnostico_ver` anticipando esta fase; el cobro por terminal
y la apertura de cajón delegan enteramente en los propios permisos de Caja
(`CAJA.terminal.operar`, `CAJA.cajon.abrir`), ya registrados — ninguna
duplicación de permisos entre bounded contexts.

**Tests** (18 nuevos en `tests/unit/test_sales_hardware.py`, todos verdes en la
primera corrida; 280 en total en la suite SALES-0..12, un solo failure
preexistente no relacionado ya documentado en SALES-9): báscula traduce
lectura/lanza en centinela vacío, ticket se arma correctamente desde
`SaleDTO`, apertura de cajón y cobro por terminal delegan en los use cases
reales de Caja con esquema real (`migrations/standalone/
175_cash_register_bounded_context_schema.py`) y quedan auditados, fallo de
driver no filtra detalle de proveedor, escáner resuelve producto por código de
barras, cae a tarjeta de cliente en modo `AUTO`, falla explícito con código no
resuelto, pantalla de cliente refleja carrito activo y pantalla de
agradecimiento tras completar, salud de dispositivos reporta configurado/no
configurado/inactivo honestamente y exige el permiso de diagnóstico.

## Lo que esta fase NO hizo (honesto, no fabricado)

- **No se escribió ningún SDK de adquirente de terminal de pago.** El
  `PaymentTerminalGateway` real sigue sin una implementación de driver
  concreta en ningún lugar del repositorio; los tests inyectan un doble falso,
  igual que ya lo hace la propia suite de Caja.
- **No se construyó ningún consumidor de pantalla de cliente** (proceso,
  segundo monitor, WebSocket). `CustomerDisplayQueryService` es la proyección
  que un consumidor futuro necesitaría, no el consumidor en sí.
- **No se convergieron los tres mecanismos de escáner de `modulos/ventas.py`**
  en un solo widget — fuera de alcance de esta pipeline (UI intocada salvo
  fixes puntuales). `ScanCodeRouter` es el punto de despacho al que cualquiera
  de los tres podría alimentar un código ya normalizado, sin exigir que se
  reescriban entre sí primero.
- **`DeviceHealthQueryService` no hace ping de conectividad real.** Abrir un
  puerto serie solo para responder una pregunta de estado sería un efecto
  secundario dentro de una query — se reporta "configurado" (fila válida en
  `hardware_config`), no "conectado ahora mismo".
- **Nada de esto se conectó a `modulos/ventas.py`.** El cajón, la báscula, la
  impresora y el escáner de la UI legacy siguen usando sus rutas actuales sin
  cambios.

## Siguiente fase

El master prompt continúa con POS-13 (Pago) y POS-14 (Checkout) — confirmar
alcance con el usuario antes de asumir.
