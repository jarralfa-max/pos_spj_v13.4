# TRF-9 — Empaque

## Alcance implementado

- **Paquetes:** `TransferPackage` registra paquete, tipo, líneas empacadas y estado.
- **Sellos:** el paquete conserva `seal_number` sin mezclarlo con despacho.
- **Tara:** el dominio valida peso bruto positivo, tara no negativa y calcula peso neto.
- **Etiquetas:** `CreateTransferPackageUseCase` consume `TransferPackageLabelGateway` cuando se solicita impresión.
- **Peso variable:** todos los pesos y temperaturas se almacenan como `Decimal`; `float` se rechaza en dominio.
- **Seguridad:** empaque exige validación backend y permiso granular de despacho.

## Decisiones

- Empaque no mueve inventario; prepara mercancía ya pickeada para TRF-10.
- La impresión de etiqueta se delega a gateway para evitar lógica de hardware en UI.
- El sello del paquete no sustituye la custodia ni el sello de embarque.

## Tests TRF-9

- Creación de paquete con sello, tara, neto y etiqueta.
- Rechazo de `float` para peso/tara.
- Rechazo de operación duplicada y líneas ajenas a la transferencia.
