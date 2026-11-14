# Mercado Pago — Experiencia de uso (UX)

- **Ítem:** SDLC-PAY-001 · **Fecha:** 2026-11-09
- **Contexto:** [APPFLOW](MERCADO_PAGO_INTEGRATION_APPFLOW.md)
- **Reglas:**
  - componentes del Design System: `StandardDialog`, `MessageDialog`, `MoneyInput`, `StandardLineEdit`;
  - textos en lenguaje de cajero, sin ids internos;
  - sin SQL ni reglas en widgets: el diálogo pregunta al presentador;
  - 1366×768 y 1920×1080, claro y oscuro.

## 1. Cobro manual (vigente desde `fix/lote-4`)

- Al elegir Mercado Pago, Tarjeta o Transferencia, el campo «Referencia» cambia su texto de ayuda:
  - «Número de operación (obligatorio)»;
  - «Número de autorización (obligatorio)»;
  - «Clave de rastreo o folio (obligatorio)».
- «Agregar pago» rechaza, con el motivo en la línea de ayuda y **antes** de iniciar el cobro:
  - la referencia vacía;
  - la referencia con formato inválido;
  - la referencia ya usada en otra venta, con el folio de esa venta;
  - la referencia repetida en el mismo cobro.
- **Ticket:** «Ref. Mercado Pago ****1234».
- **Corte X/Z impreso:** un renglón por medio de pago con el número de cobros y el bruto, «Ventas con
  pago mixto: n de m» y «Reembolsos a medio electrónico». Sólo lo ve quien puede ver importes.

## 2. Cobro con Point (PAY-013)

- El diálogo **no es modal bloqueante**: el cajero ve el estado y puede minimizarlo sin perder la
  intención.
- Estados visibles, uno a la vez, con icono y texto:
  - Preparando cobro;
  - Esperando terminal;
  - Esperando tarjeta;
  - Procesando;
  - Verificando;
  - Aprobado, Rechazado, Cancelado o Expirado;
  - Estado desconocido: consultar;
  - Error de comunicación.
- **Acciones según el estado:**
  - «Cancelar en terminal», sólo mientras el proveedor lo permite;
  - «Consultar estado», en `UNKNOWN`;
  - «Elegir otro medio», tras un final no aprobado.
  - Nunca «Reintentar cobro» mientras haya una intención sin resolver.
- **Barra del cajero:** indicador de la terminal (lista, ocupada, sin conexión), con el patrón de
  `ScaleMonitor`.
- **Tras reiniciar el POS:** aviso «Hay un cobro con Mercado Pago sin resolver en la venta F-123», con
  «Consultar».

## 3. Enlace y QR (PAY-015)

- **QR dinámico** en el diálogo y en el monitor del cliente (`CustomerDisplayWindow`), con importe,
  vigencia y marca de Mercado Pago.
- **Monitor del cliente:** muestra «Esperando pago» y, al aprobarse, «Pago recibido».

## 4. Reembolso electrónico (PAY-006, bloqueado)

- La devolución muestra la instrucción «Reembolsa $X desde Mercado Pago (ref. ****1234)».
- La solicitud queda en una bandeja «Reembolsos por confirmar» de Caja.
- El cajero captura la referencia del reembolso y confirma, o lo rechaza con motivo.
- La campana del gerente recibe la alerta (decisión del responsable).

## 5. Sin internet

Mercado Pago aparece deshabilitado con «Sin conexión: cobra en efectivo o con otro medio». No se oculta:
el cajero tiene que saber por qué no está.
