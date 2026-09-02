# ORD-13 — Empaque

Fecha: 2026-08-31. Alcance: master prompt §29 (paquetes, peso, sellado).

## Qué se construyó

- `PackageType` (BAG/BOX/INSULATED_BOX/COOLER/CRATE/TRAY/OTHER) y `PackageStatus`
  (OPEN/SEALED/CANCELLED) enums.
- `backend/domain/orders_delivery/package.py` — `OrderPackage`, entidad independiente (no
  embebida en `CustomerOrder`, mismo criterio que `OrderAddress`/`DeliveryZone`, ORD-7):
  `net_weight` SIEMPRE derivado (`gross_weight - tare`), nunca almacenado — mismo criterio
  que `CustomerOrderLine.line_total`/`final_subtotal`.
- `CustomerOrderLine.package_id` (columna nueva) + `set_package()` — una línea pertenece a
  lo sumo a un paquete.
- `OrderPackageRepository`, wireado en `OrdersDeliveryUnitOfWork`.
- `CreatePackageUseCase` (valida que todas las líneas pertenezcan al pedido antes de
  crear), `SealPackageUseCase`.

## Decisiones

- **Reutiliza `PREPARATION_COMPLETE`** — no existe un permiso "empaque.*" en el catálogo
  de ORD-1 ni en el propio §63 del prompt maestro; empacar es el último paso de
  preparación antes de quedar listo para despacho, mismo nivel que completarla.
- **`gross_weight < tare` es un error de validación**, no solo una advertencia — un
  paquete con peso neto negativo es un dato corrupto, no un caso de negocio válido.
- **Sellar es irreversible dentro de esta fase**: no existe "reabrir paquete sellado" — un
  paquete sellado solo puede seguir su curso (despacho, ORD-18) o cancelarse ANTES de
  sellar. Consistente con el criterio de no introducir estados/transiciones que el prompt
  maestro no pidió explícitamente.

## Tests

14 tests nuevos (9 dominio + 5 integración). Suite acumulada ORD-1..13: **188/188
pasando** (134 unitarios + 54 de integración, verificados por separado).

## Pendiente

- Temperatura: el campo existe (`OrderPackage.temperature`) pero no hay política de
  validación de cadena de frío todavía (ej. rango aceptable por tipo de paquete) — el
  prompt maestro lo menciona como campo, no como regla de negocio propia en esta fase.
- Etiquetas de paquete (impresión) — pertenece a la capa de infraestructura de impresión
  (ORD-28/UI), no a esta fase de dominio/aplicación.
