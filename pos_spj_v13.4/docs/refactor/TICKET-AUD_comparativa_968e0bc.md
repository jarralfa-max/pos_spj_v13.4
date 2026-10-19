# TICKET-AUD — Respuesta a la comparativa del ticket de venta (main ↔ ERP 968e0bc)

Fecha: 2026-10-16. Documento recibido: «Comparativa del ticket de venta: `main`
frente a la rama ERP». Todo lo que señala se confirmó contra el código actual y
se midió en la base real. Migración **342**.

## Decisiones del usuario

| Tema | Decisión |
|---|---|
| Logo | Empresa + sucursal opcional: cada sucursal puede tener el suyo; sin él hereda el de la empresa. |
| QR | URL configurable en la plantilla con `{folio}` (y `{sucursal}`, `{fecha}`, `{total}`); sin URL no se imprime. Nunca datos del cliente. |
| Reimpresión | El original, marcado «REIMPRESIÓN»: se guarda la foto del ticket al imprimirlo por primera vez. |

## Medido en la base real (antes)

* Plantilla «POS-01» de `SALE_TICKET` v1 con el texto «Productos, unidad, cantidad,
  costo», pendiente de aprobación: alguien intentó diseñar el ticket; nada de eso
  podía llegar a la impresora.
* `company_profiles.logo_asset_id` vacío: la pantalla pedía teclear «el UUID de un
  asset de otro sistema» que no existía.
* `print_jobs`: 0 filas — sin versión ACTIVA no se registraba ninguna impresión.
* No hay ruta de impresión «Ticket de venta» configurada (Configuración →
  Dispositivos): el POS responde «no hay impresora» — es configuración, no defecto.

## Qué se hizo

| Punto de la comparativa | Resultado |
|---|---|
| P0 — la plantilla no gobernaba los bytes | El contenido de una versión de `SALE_TICKET`/`SWEEPSTAKES_TICKET` **es** el diseño por bloques (`backend/domain/document_output/ticket_layout.py`, JSON `ticket_layout/1`). `SalesTicketPrinter` imprime el diseño de la versión ACTIVA (`TicketDesignQueryService`); el `PrintJob` registra la versión **realmente usada**. Texto libre se rechaza al crear, enviar, aprobar o activar. Un solo diseño activo por tipo de ticket. La 342 siembra el diseño por omisión como versión activa. |
| P0 — logo / QR / barras | Renderizador por bloques (`ticket_layout_renderer.py`): logo rasterizado al % del ancho, Code128 del **folio comercial** (nunca el id interno), QR con la URL configurada. Si algo gráfico falla: texto de respaldo + aviso visible (nunca un ticket incompleto en silencio). |
| P1 — configuración coherente | Diseñador en Configuración → Documentos (al crear plantilla de ticket o «Nueva versión»): bloques con casilla y orden, alineación, tamaño del logo, precio unitario, máximo de mensajes por categoría (antes fijo en código), URL/leyenda del QR, textos, papel 58/80/según impresora, líneas finales y corte. **Vista previa con los bytes del renderizador real** (`escpos_preview.py`) con el logo y datos reales de la sucursal, en 58 y 80 mm. «Imprimir prueba». Guardar = nueva versión borrador con el flujo de aprobación de siempre. |
| P1 — branding y quitar fondo | Configuración → Empresa y sucursales: «Logo para tickets» (empresa) y «Logo de la sucursal…». Antes/después, «Quitar fondo» con el removedor local de Productos (fondo conectado al borde) y tolerancia ajustable (0 = automática), conservar fondo, «Usar el de la empresa». El ORIGINAL se guarda siempre; el derivado térmico se aplana sobre blanco. |
| P1 — ticket histórico | `sale_receipt_snapshots`: diseño, versión, encabezado, logo, renglones, puntos y mensajes del momento. La reimpresión usa la foto (marcada); una promoción nueva no aparece en un ticket viejo. |
| P2 — boleto de sorteo | Diseño propio (`SWEEPSTAKES_TICKET`): nombre del sorteo, número en doble tamaño, premio, fecha, código/QR del número, texto legal. **Defecto adicional encontrado**: el impresor leía `folio`/`nombre_sorteo` y Sorteos manda `ticket_number`/`raffle_name` — el boleto salía sin número. |
| Precaución sobre `main` | No se copió el diseñador anterior: cada control tiene prueba de efecto en bytes (`test_ticket_design_main_vs_erp.py`). |

## Verificación

* `tests/integration/document_output/test_ticket_design_main_vs_erp.py` (25):
  reglas del diseño, efecto de cada opción en bytes (visibilidad, orden, logo con
  PNG transparente, sin logo, Code128 = folio, QR = URL con folio, sin librería
  gráfica → texto, límites de mensajes), vista previa 58/80 sin comandos
  desconocidos, boleto propio, sólo lo ACTIVO cambia el ticket (borrador no),
  un diseño activo por tipo, 342 idempotente, logo de sucursal/herencia, quitar
  fondo conserva el original, impresor con diseño + logo, boleto con número.
* `tests/integration/sales/test_sales_ticket_snapshot.py` (2): reimpresión
  idéntica y marcada tras cambiar el diseño; venta nueva usa el diseño nuevo.
* `tests/integration/configuracion/test_ticket_designer_ui.py` (3): controles del
  diseñador → diseño guardado; imprimir prueba; logo antes/después.
* Copia de la base real: 342 ×2; ticket real V-COR-000007 por la ruta de verdad
  (entrega interceptada): original + reimpresión marcada, una foto guardada.

## Pendiente / a configurar

* Configurar la ruta de impresión «Ticket de venta» en Configuración →
  Dispositivos: hoy no hay, así que no se imprime ni se registra `PrintJob`.
* Cargar el logo y activar el bloque «Logo» en el diseño (versión nueva →
  aprobación por otra persona → activar).
* El documento guardado en archivo (`save_receipt_document`, HTML) sigue con su
  plantilla HTML propia, no con el diseño térmico.
