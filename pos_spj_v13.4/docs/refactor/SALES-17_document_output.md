# SALES-17 — Document Output (POS-17 del master prompt)

Fecha: 2026-08-17
Fase anterior: `SALES-16_cancelaciones_devoluciones.md`.

## Alcance ejecutado

Master prompt §67, fase POS-17: "Receipt DTO. PrintJob. Reprint. PDF. Tests."

SALES-12 (Hardware) ya había construido `SalesReceiptClient` envolviendo el `PrinterService`
real — pero como un dict crudo (`ticket_data`), no como un DTO tipado, y sin capacidad de
reimpresión ni de consultar el estado real de un trabajo de impresión. Esta fase completa
exactamente esos tres huecos, más un documento plano real (sin duplicar el diseñador de
plantillas de la UI).

## Investigación previa

Leí `core/services/printer_service.py::PrintQueue` completo (no solo `PrinterService`, ya cubierto
en SALES-12). Hallazgo real: **`_log_job_to_db` ya escribe cada trabajo de impresión a una tabla
real, `print_job_log`** (migración 056, con índice por `job_id`) — columnas `job_id`, `estado`,
`folio`, `reintentos`, `error_msg`, `finished_at`. Esto significa que "PrintJob" no requiere
construir ningún mecanismo de seguimiento nuevo — ya existe uno real, solo sin consumidor del
lado de Ventas.

También leí `modulos/ventas.py::generar_html_ticket` (la función que el botón "guardar PDF" de la
UI llama) — es una función grande y fuertemente acoplada a la UI: lee `self._ticket_settings_qs`
en vivo, logo/QR embebidos, tipografía configurable.

**Corrección real, hecha tras una instrucción explícita del usuario ("el ticket debe ser idéntico
a como se imprime actualmente")**: mi primera versión de esta fase asumió que `generar_html_ticket`
era el ÚNICO renderizador real y, para no duplicar código acoplado a la UI, construí un documento
HTML plano y simplificado como sustituto — un error de alcance. Una segunda lectura encontró que
`generar_html_ticket` NO es el único renderizador real: `core/services/sales_service.py::
SalesService._execute_sale_core` (la ruta canónica de venta, la que de verdad se ejecuta hoy) ya
construye el HTML del ticket vía `core.engines.template_engine.TicketTemplateEngine.
generar_ticket()` — un motor genuinamente independiente de la UI (constructor recibe un `db_conn`
crudo, sin QWidget), que lee la MISMA plantilla guardada en `configuraciones.ticket_template_html`
y usa el MISMO template por defecto (`SalesService._default_ticket_template()`) que la producción
ya usa cuando no hay plantilla configurada. `save_receipt_document()` ahora reutiliza ese motor
real y ese fallback real — no un documento simplificado — así que el documento generado coincide
con lo que `SalesService` ya produciría para la misma venta.

**Hallazgo curioso, no corregido (fuera de alcance)**: pese a su nombre, `save_ticket_pdf(html,
filepath)` solo escribe el HTML crudo al archivo indicado — nunca convierte a PDF real. Documentado,
no es un bug de esta fase.

## Entregables

### Aplicación — DTOs

`backend/application/sales/dto.py`:
- `SaleReceiptLineDTO`/`SaleReceiptDataDTO` — el DTO tipado, Decimal de punta a punta, que §46
  pide explícitamente. Reemplaza el dict crudo que `SalesReceiptClient` construía internamente
  desde SALES-12 (la conversión a float sigue ocurriendo, pero ahora solo en la frontera hacia
  `PrinterService`, nunca antes).
- `PrintJobStatusDTO` — proyección tipada de una fila real de `print_job_log`.

### Infraestructura

`SalesReceiptClient` extendido:
- `build_receipt_data()` — igual que antes (SALES-12), ahora retorna el DTO tipado en vez de un
  dict.
- `build_receipt_data_from_sale()` — **nuevo**, para reimpresión: deriva `forma_pago`/
  `efectivo_recibido`/`cambio` directamente de `Sale.payments` (SALES-13) en vez de pedirle al
  llamador que los recuerde — una reimpresión no tiene el contexto del diálogo de pago original,
  solo la venta histórica.
- `get_job_status(job_id)` — consulta real contra `print_job_log`.
- `save_receipt_document(receipt, filepath)` — renderiza vía el `TicketTemplateEngine` REAL, el
  mismo que `SalesService._execute_sale_core` ya usa en producción, con el mismo fallback por
  defecto — el documento guardado coincide con el ticket real, no es una versión simplificada.

### Aplicación — Casos de uso

`backend/application/sales/use_cases/receipt_use_cases.py`:
- `ReprintReceiptUseCase` — el hueco real que esta fase cierra: no existía ningún equivalente en
  `backend/application/sales` antes. Exige `SalesPermissions.RECEIPT_REPRINT`, funciona para
  CUALQUIER venta completada por id (el legacy `_reimprimir_ultima_venta` solo reimprime la última
  venta), rechaza explícitamente una venta que nunca completó el cobro
  (`ReceiptNotAvailableError`, nueva excepción), emite `SaleEvents.RECEIPT_REPRINT_REQUESTED`
  (reservado desde SALES-3, nunca publicado hasta ahora).
- `SaveReceiptDocumentUseCase` — el "PDF": compone el DTO y guarda el documento plano.

**Permisos**: cero cambios — `SalesPermissions.RECEIPT_REPRINT` (`"POS.ticket.reimprimir"`) ya
existía desde SALES-2.

### Tests

14 nuevos en `tests/unit/test_sales_receipts.py` (348 en total en la suite SALES-0..17, un solo
failure preexistente no relacionado ya documentado desde SALES-9), todos verdes tras la
corrección: derivación correcta de forma de pago/efectivo/cambio desde pagos reales (efectivo
puro, mixto, solo tarjeta sin componente de efectivo), consulta de `print_job_log` real (fila
encontrada/no encontrada, exige connection), permiso de reimpresión exigido, falla explícita
para una venta que nunca completó, reimprime y deriva el pago original correctamente, emite el
evento al outbox, documento guardado exige permiso `VIEW`, documento real generado con la
plantilla por defecto REAL (`{{cajero}}`/`{{total}}`/`items_html` verificados en el contenido),
**una plantilla personalizada configurada en `configuraciones` se respeta y aparece en el
documento generado** (prueba directa de que ya no es una plantilla simplificada propia), falla
para venta no completada. Se re-corrió también la suite completa de SALES-12
(`test_sales_hardware.py`, 18 tests) para confirmar que el refactor de `SalesReceiptClient` no
rompió su contrato público (`print_receipt()`) — sigue en verde.

## Lo que esta fase NO hizo (honesto, no fabricado)

- **El documento generado coincide con el contenido real que `SalesService` ya produce
  (`ticket_final_html`, vía `TicketTemplateEngine`), pero NO incluye el logo/QR/código de barras
  embebidos que `modulos/ventas.py::generar_html_ticket` agrega como una capa adicional
  exclusiva de la UI** (esa embellecedora sí es territorio de Document Output, §46) — el
  contenido/texto del ticket es idéntico, la imagen del logo no. La impresión térmica real
  (`print_receipt`/`print_receipt_data`, vía `TicketESCPOSRenderer`) ya incluye logo/QR desde
  SALES-12, sin cambios en esta fase.
- **No se corrigió que `save_ticket_pdf` en realidad no genera PDF** (escribe HTML crudo) —
  hallazgo honesto, no es un bug introducido por esta fase ni de su alcance corregirlo.
- **No se conectó ningún dispatcher/reintento para trabajos de impresión fallidos** — `PrintQueue`
  ya tiene su propio reintento interno (confirmado en SALES-12); esta fase solo consulta el
  resultado, no construye infraestructura de reintento adicional.
- **Nada de esto se conectó a `modulos/ventas.py`.** El botón de reimpresión legacy
  (`_reimprimir_ultima_venta`) sigue funcionando exactamente igual, sin cambios.

## Siguiente fase

El master prompt continúa con POS-18 (Fiscal) — confirmar alcance con el usuario antes de asumir.
