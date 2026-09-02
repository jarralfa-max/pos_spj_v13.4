# LOY-22 — Impresión

Fecha: 2026-08-31
Alcance: master prompt §50-51 ("PrintJob integration, reprints"), fase LOY-22.

## Renderizado PDF real, no simulado

Antes de escribir código se verificó qué librerías de generación de contenido gráfico están realmente
instaladas: `reportlab` (PDF), `qrcode` (QR) y `python-barcode` (CODE128/CODE39) — las tres presentes.
`backend/infrastructure/loyalty_cards/print_renderer.py::render_batch_pdf()` produce un PDF real,
multi-página (una página por `sheet_number`), con códigos QR y de barras REALMENTE escaneables — no cajas de
relleno. Se verificó con una prueba de humo manual generando un PDF válido antes de escribir ningún test
formal. El único elemento sin contenido real es `IMAGE` (dibuja un recuadro con la etiqueta "[IMAGE]") — no
existe todavía un almacén de assets de donde traer una imagen real, hueco señalado explícitamente, no
disimulado.

Cada elemento del `design_schema_json` (LOY-18) se escala proporcionalmente del tamaño de canvas del diseño
al tamaño real de tarjeta de la imposición (`scale_x = card_width_mm / canvas_width_mm`), por si ambos
difieren. La posición de cada tarjeta dentro del pliego se calcula directamente de
`sheet_number`/`position_in_sheet` (LOY-21, ya derivados, nunca recalculados aquí) más los márgenes/sangrado/
calles del perfil de imposición (LOY-20) — ninguna de esas cuatro fases anteriores tuvo que cambiar para que
esto funcionara, señal de que las abstracciones se diseñaron con la granularidad correcta.

## Un giro real de diseño: NO se pudo reutilizar `document_output.PrintJob`

El primer borrador de esta fase intentó reutilizar la entidad `PrintJob` YA CONSTRUIDA y probada en
`backend.domain.document_output` (de la transformación SET-11, con máquina de estados PENDING→RENDERING→
READY→PRINTING→PRINTED, reintentos, dead-letter, y su propio `create_reprint()` con motivo obligatorio) en
vez de inventar una paralela — el `DocumentType.LOYALTY_CARD` incluso ya existía en su enum, sin usar hasta
ahora. El docstring de esa entidad dice explícitamente que `source_module`/`source_document_id` son
"referencias opacas... nunca resueltas ni validadas contra otro bounded context", lo que sugería que
`template_version_id` también podía pasarse como una referencia libre.

**Eso resultó ser falso a nivel de esquema**, descubierto por un `sqlite3.OperationalError: no such table:
main.devices` real al correr el primer test bajo `PRAGMA foreign_keys = ON` (no por leer el docstring):
`print_jobs.template_version_id` tiene una FK real y forzada hacia `document_template_versions(id)` — una
tabla completamente distinta, con un modelo de plantillas de texto (ESC_POS/HTML/PDF/ZPL) ajeno al esquema
declarativo visual de LOY-18. Reutilizar esa tabla habría requerido materializar una fila espejo en
`document_template_versions` por cada `LoyaltyCardTemplateVersion` — una integración cruzada mucho más
grande y semánticamente incorrecta, fuera de alcance de esta fase.

**Lección**: que el docstring de una entidad describa un campo como "opaco" describe la validación de la
CAPA DE DOMINIO, no las foreign keys del ESQUEMA PERSISTIDO — hay que revisar el DDL real antes de asumir
que un campo cruzado es una referencia libre. Corregido construyendo `LoyaltyCardPrintJob`, una entidad
propia dentro de `backend/domain/loyalty_cards/`, que replica DELIBERADAMENTE la forma de la máquina de
estados de `PrintJob` (PENDING→RENDERING→READY, FAILED, y el mismo patrón de reimpresión con motivo
obligatorio) para consistencia conceptual, pero vive enteramente en el esquema propio de Tarjetas — sin
riesgo de FK cruzada. Esto costó reescribir `print_use_cases.py` una vez, antes de que ningún test hubiera
sido reportado como pasando — el descubrimiento ocurrió durante el primer intento real, no después.

## Alcance del `LoyaltyCardPrintJob`: solo el renderizado

`LoyaltyCardPrintJob` rastrea si el PDF se generó correctamente — NO si una tarjeta física específica ya se
imprimió de verdad (eso ya lo cubre `LoyaltyCardBatchItem.status`, LOY-21). Los dos conceptos se mantienen
deliberadamente separados: renderizar el PDF es un paso técnico (¿el esquema de diseño y los valores de
placeholder produjeron un archivo válido?); confirmar que una tarjeta salió de la impresora es una acción
física del operador, ya modelada.

## Qué se construyó

`PrintUnit` (par de datos plano) + `render_batch_pdf()` en infraestructura (sin entidades de dominio, sin
acceso a otro bounded context — los valores de placeholder ya resueltos los provee el llamador, mismo
aislamiento que cada pieza cruzada de esta sesión). Entidad `LoyaltyCardPrintJob`, esquema
`loyalty_card_print_jobs` (migración 240), repositorio, `LoyaltyCardsUnitOfWork` extendido, y
`backend/application/loyalty_cards/use_cases/print_use_cases.py`:
`RenderLoyaltyCardBatchUseCase` (permiso `BATCH_PRINT`, soporta `only_sheet_number` para renderizar/
reimprimir un solo pliego) y `ReprintLoyaltyCardBatchUseCase` (permiso `REPRINT`, siempre motivo
obligatorio, siempre un job nuevo enlazado al original).

## Alcance honesto

- `IMAGE` no renderiza contenido real — recuadro de relleno, sin almacén de assets todavía.
- Nada conecta el PDF generado con una impresora física real ni con `LoyaltyCardBatchItem.mark_printed()`
  automáticamente — ese enlace (confirmar impresión física tras generar el PDF) queda para una integración
  futura, posiblemente LOY-24.
- `card_placeholder_values` debe ser resuelto y suministrado por el llamador (nombre real del cliente, nivel
  de membresía, etc.) — esta fase no cruza a Clientes/Fidelidad para resolverlos, mismo aislamiento de
  bounded context de siempre.

## Tests

16 tests nuevos (`test_print_renderer.py`: 9; `test_print_use_cases.py`: 7), todos pasando tras la
corrección del diseño de `PrintJob`. Verificado con bootstrap real completo — migración 240 corre limpia,
las 10 tablas `loyalty_card*` existen juntas.

499 tests de todo el dominio Fidelidad/Comercial/Sorteos/Tarjetas corridos juntos, sin regresión.

## Pendiente para fases futuras

- LOY-23 (Tarjeta digital): `LoyaltyDigitalCardProjection` para tarjetas `DIGITAL` (que no pasan por este
  flujo de impresión física).
- Confirmación automática de impresión física → `LoyaltyCardBatchItem.mark_printed()`.
- Almacén de assets real para elementos `IMAGE`.
