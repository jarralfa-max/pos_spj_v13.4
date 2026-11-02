# SDLC-ORD-005 — "Todos los pedidos → Nuevo pedido" captura el producto por UUID y un precio libre que termina cobrándose

- **Prioridad:** P1
- **Nivel de riesgo:** T1
- **Origen:** `docs/refactor/ORD-30_validacion_final.md` → "Pendiente" §3 (selección real de producto en "Nuevo pedido"), re-verificado en código (`/sdlc-plan` Modo B, 2026-10-31)
- **Estado:** borrador
- **Depende de:** —

## Problema
El pendiente de ORD-30 se cerró solo a medias. La página "Nuevo pedido" ya busca el producto y toma el precio de Pricing. Pero la pantalla "Todos los pedidos" conserva su botón "Nuevo pedido", que abre el diálogo de ORD-28. Ese diálogo pide el **UUID del producto** escrito a mano y un **precio unitario libre**, y crea el pedido con `CreateCustomerOrderUseCase`, que respeta el precio recibido. Ese precio se congela en la línea y es el que Ventas cobra. Además el diálogo permite una sola línea y no captura dirección.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Verificado directamente el 2026-10-31 sobre `ed026f7b`.

- Cerrado: `frontend/desktop/modules/orders_delivery/pages/new_order_page.py:3-4,28,90-93` usa `ProductSearchBox` y "el precio lo fija Pricing" (`presenters/new_order_presenter.py:4`, `CaptureOrderUseCase`).
- Abierto: `frontend/desktop/modules/orders_delivery/dialogs/new_order_dialog.py:6-10` (docstring: "Product selection is intentionally MANUAL"), `:51-53,59-60` (`StandardLineEdit(placeholder="UUID del producto")`, `MoneyInput()` "Precio unitario") y `:84-86` (manda el `unit_price` capturado).
- `frontend/desktop/modules/orders_delivery/pages/orders_list_page.py:49-57`: el botón primario "Nuevo pedido" abre ese diálogo.
- `frontend/desktop/modules/orders_delivery/presenters/orders_list_presenter.py:49-56` lo pasa a `CreateCustomerOrderUseCase`.
- `backend/application/orders_delivery/use_cases/order_capture_use_cases.py:47-49`: ese caso de uso respeta el precio de la línea. Su docstring dice que es para precio **cotizado** (`quote_id`), "a diferencia de `CaptureOrderUseCase`, que tarifica en el servidor". Aquí se llama sin `quote_id`.
- `backend/infrastructure/integrations/orders_delivery_sales_client.py:96`: la venta se arma con `unit_price=line.unit_price_snapshot`, así que el precio tecleado es el que se cobra.
- No se comprobó si `CreateCustomerOrderUseCase` valida que el `product_id` exista: **no verificado**.

## Impacto
Cualquier usuario con permiso de crear pedidos puede vender a cualquier precio, sin pasar por Pricing ni por la autorización de precio mínimo (Fase 5 del pipeline ERP). Afecta margen y control. Además, la misma acción ("Nuevo pedido") se comporta distinto según la pantalla desde donde se abre.

## Objetivo
- Desde cualquier pantalla, "Nuevo pedido" usa un solo flujo de captura: búsqueda de producto, precio desde Pricing y dirección.
- `CreateCustomerOrderUseCase` sin `quote_id` no acepta un precio del cliente, o deja de estar expuesto a la UI (prueba).
- Hay una prueba de UI o de presenter que fija que ninguna pantalla de Pedidos pide UUID ni precio manual.

## Alcance
- **Incluye:** Diálogo y botón de "Todos los pedidos", la frontera del caso de uso para precio no cotizado y pruebas.
- **No incluye:** Precio por cliente (SDLC-PRICE-002) ni la falla silenciosa del motor de precios en POS (SDLC-SALES-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Usar los componentes estándar (`ProductSearchBox`, `AddressInput`); no crear una tercera variante de captura.

## Trabajo previo relacionado
`docs/refactor/ORD-28_ui_ux.md`; PASS 6 (`frontend/desktop/modules/orders_delivery/orders_delivery_routes.py:51-53`, "captura con búsqueda de producto, precio de Pricing y dirección"); SDLC-SALES-001; Fase 5 del pipeline ERP (mínimo con autorización).

## Preguntas abiertas
- ¿Se elimina el diálogo y el botón lleva a la página "Nuevo pedido", o se conserva un alta rápida desde el listado con el mismo flujo?
