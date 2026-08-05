# CASH-18 — Hardware

La aplicación usa puertos independientes para cajón, impresora y terminal. Los
drivers concretos viven en infraestructura y reciben transportes inyectados; por
ello USB, serial, ESC/POS y SDK del adquirente no contaminan dominio, casos de
uso ni UI.

## Operación segura

- Abrir cajón exige `CASH_DRAWER_OPEN`; sin venta exige además
  `CASH_DRAWER_OPEN_WITHOUT_SALE` y un motivo.
- Imprimir exige `CASH_PRINT`, contenido no vacío y entre una y tres copias.
- Cobrar en terminal exige `CASH_TERMINAL_OPERATE`, terminal activa y alcance de
  sucursal. Ventas conserva la propiedad del pago; esta capa sólo ejecuta el
  comando físico.
- La clave de operación UUIDv7 se entrega al adquirente como clave de
  idempotencia.

Cada éxito genera evento, auditoría y outbox. Cada error de driver se normaliza,
se registra como `CASH_HARDWARE_OPERATION_FAILED` y publica una alerta crítica
por outbox. La entrega a WhatsApp u otro canal pertenece al dispatcher, nunca al
driver ni al caso de uso.

## Drivers

`EscPosDrawerDriver`, `ReceiptPrinterDriver` y `PaymentTerminalDriver` son
adaptadores sustituibles. Los transportes reales se conectan exclusivamente en
el composition root de cada instalación. Las pruebas usan transportes falsos y
no requieren dispositivos físicos.
