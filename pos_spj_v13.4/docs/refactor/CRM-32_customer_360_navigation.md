# CRM-32 — Customer 360: primer NavigationIntent real (Expediente → Nueva venta)

Fecha: 2026-08-16. Quinta fase del cut-over completo (mapa Fase 0 §3
"Customer 360 + conectividad entre ventanas").

## Contexto

`CustomersCrmWorkspace` (CRM-14) ya tenía navegación INTRA-módulo real
(`select_route(route_id)` + `QStackedWidget`) — CRM-15 a CRM-18 la
construyeron página por página. Lo que faltaba, exactamente como describe
la Fase 3 del prompt maestro, era poder saltar DESDE el Expediente del
cliente HACIA otro módulo (Ventas, WhatsApp, Finanzas...) sin que el
usuario tuviera que volver a buscar al mismo cliente ahí.

`interfaz/main_window.py` ya tenía la primitiva de la que este mecanismo
es una extensión: cualquier módulo con una señal `abrir_modulo` se
auto-conecta en `_conectar()` para cambiar `self.stack` — el mismo patrón
que ya usa el Dashboard (`_DASH_NAV`). Esa señal es `pyqtSignal(str)` —
solo un código de módulo, sin espacio para contexto. Cambiar su firma
habría roto cada módulo ya conectado a ella.

## Qué se construyó

- `frontend/desktop/navigation/navigation_intent.py` (nuevo): dataclass
  simple, sin dependencia de Qt — `NavigationIntent(route: str, context:
  dict)`. Coincide casi literal con el ejemplo del prompt maestro
  (`NavigationIntent(route="sales.new", context={"customer_id": ...})`).
- `CustomerProfilePage`: nueva acción "Nueva venta" en el header (junto a
  "Editar"/"Actualizar"), nueva señal `navigation_requested =
  pyqtSignal(object)` — hermana aditiva de `edit_requested`, no la
  reemplaza.
- `CustomersCrmWorkspace`: expone su propia `navigation_requested`,
  relayed desde `CustomerProfilePage` — este es el objeto real que
  `main_window.py` agrega a su `QStackedWidget` (vía
  `modulos/clientes_crm.py`'s factory), así que es el nivel correcto para
  que `_conectar()`'s auto-wiring lo vea.
- `interfaz/main_window.py`: `_conectar()` ahora también conecta
  `navigation_requested` (cuando existe) a un nuevo
  `_handle_navigation_intent(intent)`, que resuelve `intent.route` → código
  de módulo vía `_NAVIGATION_ROUTES` (hermano aditivo de `_DASH_NAV`),
  llama `manejar_navegacion` (mismo chequeo de permisos que cualquier otra
  navegación) y, si el destino implementa `aplicar_contexto(context)`, se
  lo entrega.
- `ModuloVentas.aplicar_contexto(context)`: primer y único receptor real
  hoy. Resuelve `customer_id` (Customer Master) → `clientes.id` (legacy)
  vía el bridge de CRM-21 (`customers.legacy_customer_id`) y preselecciona
  ese cliente en checkout, igual que si el cajero lo hubiera buscado.

## Limitación real, no oculta

El bridge CRM-21 solo resuelve legacy → nuevo. Un cliente creado
ÚNICAMENTE desde la página "Nuevo cliente" del CRM (nunca bridgeado desde
`clientes`) todavía no tiene fila legacy — Ventas no puede seleccionarlo
todavía. `aplicar_contexto` lo detecta y muestra un mensaje claro en vez
de fallar en silencio o crashear. Construir el bridge en la otra
dirección (crear una fila `clientes` al crear un customer nativo) es una
fase futura, no se fabricó aquí a medias.

## Explícitamente NO tocado en esta fase

- Solo una ruta (`sales.new` → Ventas) está conectada — el prompt maestro
  pide también crédito, CxC, cobranza, WhatsApp, caso de servicio,
  delivery, fidelidad. `_NAVIGATION_ROUTES` está diseñado para crecer una
  entrada a la vez, cada una con su propio `aplicar_contexto` real en el
  módulo destino — no se fabricaron destinos decorativos sin
  implementación.
- `CustomerWorkspaceContext` (actor/branch/company) — ya vive de forma
  global en `SessionContext`/`container.session`, accesible por cualquier
  módulo sin necesidad de pasarlo por el intent; el intent solo transporta
  lo específico del salto (`customer_id`).

## Verificación

```bash
python -m pytest tests/unit/test_crm_32_navigation_intent.py \
  tests/unit/test_customers_crm_profile_page.py \
  tests/unit/test_customers_crm_ui_workspace.py \
  tests/test_ventas_customer_dialog_regression.py \
  tests/architecture/test_customers_crm_ui_does_not_receive_app_container.py \
  tests/architecture/test_customers_crm_ui_has_no_sql.py -v
```
51 tests pasando (8 nuevos de esta fase + 43 preexistentes, cero
regresiones, guardrails de arquitectura de la UI de Clientes/CRM siguen
verdes).
