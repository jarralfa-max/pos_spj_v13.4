# CRM-16 — Directorios: clientes, leads, oportunidades, casos (tablas, filtros)

Fecha: 2026-08-13. Segundo y tercer/cuarto/quinto conjunto de páginas reales
en `frontend/desktop/modules/customers_crm/` (CRM-15 construyó
`customers.overview`; esta fase construye `customers.directory`,
`crm.leads`, `crm.opportunities`, `crm.service_cases`). Fuente de diseño:
`docs/refactor/customers_crm_master_prompt.md` §79 (componentes canónicos,
incluyendo `FilterBar`).

## Tercer hallazgo consecutivo del mismo patrón: `FilterBar` tampoco existe con ese nombre

Antes de escribir código se buscó `FilterBar` en todo `frontend/desktop/` —
no existe bajo ese nombre literal, igual que `ModuleSidebar`/`IconProvider`
(CRM-14) y `ChartDTO`/`ChartBridge` (CRM-15). Cada página con filtros ya
construida en el repo (`frontend/desktop/modules/purchasing/pages/
direct_purchase_history_page.py`, el precedente más cercano) compone el
mismo resultado con `SearchInput` + `SearchableComboBox` en una fila —
ningún componente único "FilterBar" real existe para importar. Esta fase
usa esa misma composición en vez de inventar un componente nuevo. Tres
fases seguidas encontrando la misma clase de discrepancia entre el prompt
maestro y el código real confirma que es un patrón estructural del prompt
(nombra el concepto de diseño, no necesariamente la clase Python exacta),
no una casualidad — vale la pena asumirlo por defecto en fases de UI
futuras y verificar primero en vez de adivinar el nombre.

## Qué se construyó

- **`pages/_directory_base.py`** — `CustomerCrmDirectoryPage`, clase base
  compartida por las cuatro páginas: `PageHeader` + fila de filtros
  (`SearchInput` + `SearchableComboBox` de estado) + `StandardTable` +
  estado vacío (`ViewState.EMPTY`) + etiqueta de error. Mismo patrón de
  "atributos de clase + override" que
  `frontend/desktop/modules/transfers/pages/base_page.py`'s
  `TransferWorkspacePage` ya establece (`route_id`/`title`/`subtitle`/
  `columns`/`status_options` como atributos; `_fetch()`/`_row()` como
  hooks que cada subclase implementa) — no se inventó una jerarquía nueva,
  se extendió la que ya existía con un segundo filtro (estado).
- **Cuatro páginas concretas** (`customers_directory_page.py`,
  `leads_directory_page.py`, `opportunities_directory_page.py`,
  `service_cases_directory_page.py`) — cada una ~30 líneas: columnas,
  diccionario de traducción de estado (mismo criterio pequeño y local que
  `status_es()` ya usa en `purchasing`, no un sistema de i18n compartido
  nuevo), `_fetch()`/`_row()`.
- **Cuatro métodos nuevos en `CustomerCrmPresenter`**
  (`customers_directory()`/`leads_directory()`/`opportunities_directory()`/
  `cases_directory()`) — mismo patrón "método de negocio nombrado, degrada
  a `[]` si no hay nada conectado" que `dashboard()` (CRM-15). Cada uno
  busca `query_services["X"]`, llama `.list_directory(context, limit=200)`,
  y filtra por búsqueda/estado en Python puro.

## Decisión de diseño: filtrado en el presenter, no en el backend ni en la página

Ninguno de los `list_directory()` de CRM-3/4/5/7 acepta `search`/`status`
como parámetro — solo alcance (scope) + `limit`/`offset`. Agregar soporte
de filtro del lado del servidor habría significado tocar la capa de
repositorio de cuatro bounded contexts distintos, desproporcionado para
una fase llamada "Directorios" cuyo propio nombre es sobre *listar*, no
sobre extender los query services de otras cuatro fases. En su lugar, el
presenter trae la página ya autorizada y con alcance resuelto
(`limit=200`, el mismo default que cada `list_directory()` ya usa) y filtra
en Python — un refinamiento de presentación sobre datos ya autorizados, no
una métrica de negocio recalculada, así que no contradice "la UI no calcula
KPIs" (§90) de la misma forma que inventar un conteo o total nuevo sí lo
haría. Documentado explícitamente, no una omisión.

## Bug real atrapado por los tests de CRM-14/15, no un bug nuevo de test

Al conectar las cuatro páginas reales a las rutas `customers.directory`/
`crm.leads`/`crm.opportunities`/`crm.service_cases` (antes placeholders),
la suite de pruebas YA EXISTENTE de CRM-14
(`test_customers_crm_ui_workspace.py::test_unbuilt_route_resolves_to_empty_state_placeholder`,
que navega explícitamente a `crm.leads`) empezó a fallar/colgarse. Causa
raíz, dos problemas reales en `_directory_base.py`, no en el test:

1. **Colisión de nombres**: `self._status` se usaba primero para una
   etiqueta de error (`QLabel`) y luego, dos líneas después, para el
   combobox de filtro de estado (`SearchableComboBox`) — el segundo
   sobrescribía silenciosamente al primero. Corregido renombrando el
   combobox a `self._status_filter`.
2. **`reload()` sin manejo de errores**: a diferencia de
   `CustomersCrmOverviewPage.reload()` (CRM-15), la primera versión de
   `CustomerCrmDirectoryPage.reload()` no envolvía la llamada al presenter
   en `try/except` — un presenter falso de prueba sin el método
   correspondiente (`AttributeError`) se propagaba sin control. Corregido
   con el mismo patrón try/except + etiqueta de estado que CRM-15 ya
   estableció — "una página siempre debe mostrar algo," ahora aplicado de
   forma consistente en las dos clases base de página que existen en el
   módulo.

## Verificación

```bash
python -m pytest tests/architecture/test_customers_crm_*.py \
  tests/unit/test_customers_crm_ui_workspace.py \
  tests/unit/test_customers_crm_overview_page.py \
  tests/unit/test_customers_crm_directory_pages.py -q
# 22 guardrails + 23 + 13 + 22 = 80 passed
```

- 22 pruebas nuevas (`tests/unit/test_customers_crm_directory_pages.py`):
  los cuatro métodos del presenter (vacío sin conectar, delega y filtra por
  búsqueda, filtra por estado, sin filtros regresa todo) y las cuatro
  páginas (tabla poblada, estado vacío, estado de error ante una excepción,
  búsqueda dispara recarga con el texto correcto, formato de fila por
  entidad, selección de filtro de estado se reenvía al presenter).
- Los 22 guardrails de CRM-1 siguen en verde.
- 812 tests combinando toda la suite `customers`/`crm` + las pruebas de UI
  de CRM-14/15/16 pasan juntos — cero regresión, incluyendo las pruebas de
  CRM-14 que originalmente atraparon el bug real descrito arriba.
- Sintaxis limpia en todo el repositorio.

## Pendiente (próximas fases)

- **Búsqueda/filtro del lado del servidor** para `list_directory()` — si el
  volumen de datos algún día supera lo razonable para `limit=200` +
  filtrado en memoria, alguna fase futura puede agregarlo a CRM-3/4/5/7 sin
  tocar estas cuatro páginas (siguen llamando al mismo método, solo con más
  parámetros).
- **Detalle/expediente por entidad** (`customers.profile`, `crm.lead_detail`,
  `crm.opportunity_detail`, `crm.case_detail`) — las cuatro tablas ya
  reportan `row_ids`, listas para que una fase futura conecte un clic de
  fila a la página de detalle correspondiente; no se construyó aquí (fuera
  del alcance nombrado: "tablas, filtros", no "detalle").
- **Conexión real a query services con vida** — sigue pendiente de la
  misma decisión de registro en el menú global que CRM-14/15 ya dejaron
  documentada.
