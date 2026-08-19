# SALES-19 — UI decomposition (POS-19 del master prompt)

Fecha: 2026-08-17
Fase anterior: `SALES-18_fiscal.md`.

## Alcance ejecutado

Master prompt §67, fase POS-19: "Cashier bar. Catalog panel. Product grid. Checkout panel.
Customer panel. Cart. Totals. Actions. Dialogs. Tests." — la primera fase de las 19 que toca
presentación en vez de backend puro.

## Decisión de alcance, confirmada explícitamente con el usuario

Investigué primero (agente de research) el precedente real ya establecido en este repositorio
para "descomponer un monolito PyQt5 legacy": `frontend/desktop/modules/customers_crm/`
(construido en fases CRM anteriores) — un módulo NUEVO y paralelo al legacy
`modulos/clientes.py`, nunca conectado a él, con su propio composition root/presenter/páginas,
enrutado a través de un wrapper delgado (`modulos/clientes_crm.py`) que `interfaz/main_window.py`
trata igual que cualquier módulo legacy.

A diferencia de CRM, Ventas/POS SÍ tiene un contrato de fidelidad visual pixel-a-pixel (SALES-1,
"Regla Visual No Negociable") — y las 18 pruebas golden-master existentes construyen la clase
`modulos.ventas.ModuloVentas` REAL directamente. Esto significa que una descomposición genuina
"en el lugar" habría requerido editar el archivo de producción viva que usan los cajeros hoy —
un riesgo cualitativamente distinto a cualquier fase anterior (todas agregaron código nuevo y
aislado, cero riesgo para la app en vivo).

Dado ese riesgo, pregunté al usuario explícitamente cómo abordar esta fase antes de escribir
código. Opciones presentadas: (a) descomposición en el lugar dentro de `modulos/ventas.py`
preservando el árbol de widgets exacto, (b) un módulo nuevo paralelo sin conectar, siguiendo el
precedente de `customers_crm`, o (c) una porción de prueba de concepto acotada. El usuario eligió
**(b) — módulo nuevo paralelo, sin conectar** — la misma disciplina de "nunca tocar
`modulos/ventas.py` salvo arreglos quirúrgicos" que cada fase anterior ya seguía, extendida a
esta.

## Entregables

### `frontend/desktop/modules/sales_pos/` — estructura nueva, paralela

Mirrors exactamente las convenciones reales de `customers_crm` (leídas directamente del código,
no adivinadas):

- `composition.py` — el ÚNICO lugar que recibe una `connection`/`session_context`/
  `printer_service` reales y los conecta a los 25+ casos de uso/query services reales construidos
  en SALES-2..18. Nunca recibe el `AppContainer` completo — mismo guardrail CRM-1 que
  `customers_crm/composition.py` ya aplica, verificado aquí con una prueba de arquitectura nueva.
- `sales_pos_presenter.py::SalesPosPresenter` — el único objeto con el que hablan los
  componentes. Cada método de escritura se degrada a `SaleResult.fail(..., "NOT_WIRED")` cuando
  no está conectado — mismo contrato que `CustomerCrmPresenter` ya estableció ("un componente
  siempre debe tener algo seguro que renderizar/con que reaccionar").
- `capability_resolver.py`/`view_models.py` — mapeo de los permisos granulares `SalesPermissions`
  (ya existentes desde SALES-2, cero permisos nuevos) a un `SalesPosCapabilities` que gatea cada
  botón de acción.
- `components/`: `cashier_bar.py`, `catalog_panel.py`, `product_grid.py`, `cart_table.py`,
  `customer_panel.py`, `totals_card.py`, `actions_panel.py`, `checkout_panel.py` — cada uno un
  widget real, construido con el sistema de diseño ya existente (`StandardTable`,
  `CustomerSearchBox`, `SummaryCard`, `StatusBadge`, `create_success_button`/`create_warning_button`/
  `create_danger_button`), nunca SQL ni referencias al contenedor de la app (verificado con dos
  pruebas de arquitectura nuevas).
- `dialogs/`: `discount_dialog.py` (conectado a `ApplySaleDiscountUseCase`, SALES-8) y
  `quick_customer_dialog.py` (conectado a `QuickCreateCustomerForSaleUseCase`, SALES-10) —
  representativos, no una réplica exhaustiva de cada diálogo legacy.
- `sales_pos_workspace.py::SalesPosWorkspace` — ensambla todo en la misma regla estructural que
  protege el contrato legacy: un solo `QSplitter`, exactamente dos paneles (catálogo izquierda /
  cobro derecha), barra de cajero arriba.
- `modulos/ventas_pos.py` — wrapper delgado, mismo patrón que `modulos/clientes_crm.py` —
  **NO conectado a `interfaz/main_window.py`**. `_conectar("POS", ModuloVentas, ...)` sigue
  intacto.

### Orden real preservado, no el orden abstracto del prompt

`CheckoutPanel` ensambla Carrito → Cliente → Totales → Acciones — el orden REAL que SALES-1 ya
documentó (`sales_pos_visual_contract.md`: "Carrito → Cliente → Totales..."), no el orden que
sugiere la propia lista de viñetas §1 del prompt maestro (que implica cliente antes que carrito).
Mismo principio de reconciliación "el orden real gana sobre la lista abstracta del prompt" que
SALES-1/3/5/9 ya aplicaron repetidamente — verificado con una prueba estructural dedicada.

### Tests

20 nuevos: 2 de arquitectura (`test_sales_pos_ui_does_not_receive_app_container.py`,
`test_sales_pos_ui_has_no_raw_sql.py` — mismo patrón que los guardrails de `customers_crm`),
9 del presentador (`test_sales_pos_presenter.py` — degradación segura sin conexión, reenvío
correcto de campos, resolución de capacidades desde permisos reales de sesión), 9 estructurales
del workspace (`test_sales_pos_workspace.py` — construcción real de Qt sin backend conectado,
un solo splitter de dos paneles, catálogo izquierda/cobro derecha, barra de cajero arriba,
**orden carrito-antes-que-cliente verificado explícitamente**, Cobrar como acción dominante,
variantes de botón idénticas al contrato legacy, botones deshabilitados sin permisos). Se
re-corrió también la suite completa de 18 pruebas golden-master legacy
(`tests/visual/golden/sales_pos/`) para confirmar que `modulos/ventas.py` sigue exactamente
intacto — sigue en verde sin cambios.

**Una corrección real encontrada en la primera corrida** (no un bug de producción, un defecto de
mi propia prueba de arquitectura): el guardrail "sin SQL crudo" originalmente marcaba
`use_case.execute(...)` como una llamada SQL sospechosa por el patrón `.execute(` — un falso
positivo, ya que cada caso de uso de este repositorio expone su propio método `.execute()`. La
propia `customers_crm/composition.py` evita esto vinculando `.execute` a una variable local
(`run = ...execute`) antes de llamarlo, en vez de escribir el substring literal `use_case.execute(`
— apliqué el mismo estilo aquí, no relajé la prueba.

## Lo que esta fase NO hizo (honesto, no fabricado)

- **No se tocó `modulos/ventas.py`.** Cero cambios — la decisión explícita del usuario, no una
  omisión.
- **No se conectó `frontend/desktop/modules/sales_pos/` a `interfaz/main_window.py`.**
  `modulos/ventas_pos.py` existe como el punto de integración real y listo, pero
  `_conectar("POS", ...)` sigue apuntando exclusivamente al módulo legacy.
- **No se replicó cada diálogo legacy** (pago, devolución completa con selección de artículo,
  factura con selección de perfil fiscal, etc.) — solo dos representativos
  (descuento, cliente rápido) que prueban el patrón extremo a extremo con casos de uso reales.
- **No se persiguió fidelidad de píxel exacta con el árbol legacy** (fuera del alcance elegido:
  módulo paralelo, no descomposición en el lugar) — las pruebas estructurales nuevas protegen la
  estructura/orden/variantes de ESTE árbol nuevo, no coordenadas de píxel contra el legacy.
- **No se completó `ScanCodeRouter`/lector de código de barras en la UI** — el componente de
  catálogo tiene búsqueda por texto conectada a `SalesCatalogQueryService.search()` (que ya
  resuelve por código de barras exacto), pero no hay un manejador de escaneo por hardware
  dedicado en esta fase.

## Siguiente fase

El master prompt continúa con POS-20 (Preservación visual) — dado que esta fase deliberadamente
NO tocó el árbol legacy, confirmar con el usuario qué significa esa fase en este contexto antes
de asumir.
