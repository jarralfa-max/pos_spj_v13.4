# CRM-17 — Expedientes: Customer 360, tabs, timeline, resúmenes

Fecha: 2026-08-13. Quinto conjunto de páginas reales en
`frontend/desktop/modules/customers_crm/` — construye `customers.profile`,
el Expediente del cliente (§27-29), y conecta el Directorio de clientes
(CRM-16) a él. Fuente de diseño:
`docs/refactor/customers_crm_master_prompt.md` §27-29.

## Cuarto hallazgo consecutivo del mismo patrón, y uno nuevo: el propio nombre del método propio choca con el guardrail

Antes de escribir código se confirmó que `CustomerSummaryHeader`,
`ContextBar`, `ActionBar` y `PageState` (§27-29) tampoco existen como
clases reales — cuarto caso consecutivo de esta discrepancia entre el
prompt maestro y el árbol de componentes real (después de `ModuleSidebar`/
`IconProvider` en CRM-14, `ChartDTO`/`ChartBridge` en CRM-15, `FilterBar`
en CRM-16). Además, `QTabWidget` — el widget PyQt crudo que resolvería
"tabs internas" gratis — está explícitamente prohibido por
`test_customers_crm_uses_canonical_design_system.py`.

Un hallazgo nuevo, no una repetición: al nombrar el método propio de
navegación de la nueva `PillTabBar` como `select(key)` (para que
`CustomerProfilePage` pudiera activar la pestaña "Resumen" al cambiar de
cliente), el guardrail de SQL crudo lo detectó — exactamente el mismo
choque que `SideNav.select()` ya había causado en CRM-14 y que la memoria
del proyecto ya documentaba como lección aprendida ("cualquier método
llamado `select` en este módulo chocará con el escáner `\bSELECT\b`"). Esta
vez el choque no vino de reutilizar un componente ajeno sino de nombrar un
método PROPIO sin recordar la lección ya registrada — vale la pena
verificar contra la memoria del proyecto antes de nombrar cualquier método
de navegación/selección nuevo en este módulo, no solo al llamar métodos
existentes. Renombrado a `activate(key)`.

## Qué se construyó

- **`pages/_pill_tab_bar.py`** — `PillTabBar`: fila horizontal de botones
  checkeables (`create_ghost_button` + `QButtonGroup` exclusivo) + señal
  `tab_changed(str)`. Mismo patrón botón-fila-más-`QStackedWidget` que el
  propio mensaje de error del guardrail de `QTabWidget` ya sugiere
  ("ModuleSidebar+PageState" como reemplazo de navegación primaria) — solo
  horizontal en vez de vertical, y interno a una página en vez de
  workspace completo.
- **`pages/customer_profile_page.py`** — `CustomerProfilePage`: `PageHeader`
  + fila de resumen (`StatusBadge` + etapa de ciclo de vida) + `PillTabBar`
  + `QStackedWidget` con las **12 pestañas exactas de §27-29**: Resumen,
  Identidad, Contactos, Direcciones, Actividad, Oportunidades, Comercial,
  Crédito, Atención, Consentimientos, Integraciones, Auditoría. Cada
  pestaña se construye UNA vez (estructura) y se repuebla en cada
  `reload()` (datos) — mismo patrón que las páginas de CRM-15/16.
  Toda la página es composición pura sobre `Customer360View` (CRM-12,
  extendido por CRM-13) — ningún dato se recalcula, ninguna tabla nueva se
  crea, ningún monto se desenmascara distinto de como el backend ya lo
  entregó.
  "Comercial" renderiza `orders_summary`/`delivery_summary` (Pedidos/
  Delivery, §49-55); "Integraciones" renderiza `whatsapp_summary`/
  `loyalty_summary` (WhatsApp/Fidelidad) — separación deliberada siguiendo
  los límites de módulo del propio §49-55, no arbitraria. "Auditoría" es
  `recent_history` — el timeline cruzado que `CustomerHistoryQueryService`
  (CRM-12) ya construye, el sub-tema "timeline" de esta fase.
- **`CustomerCrmPresenter.customer_360(customer_id)`** — a diferencia de
  `dashboard()` (CRM-15), NO degrada a un DTO vacío si no hay nada
  conectado: `Customer360View.profile` no tiene un valor por defecto
  sensato (es la identidad real de un cliente, no un conjunto de KPIs en
  cero), así que lanza una excepción — `CustomerProfilePage.reload()` ya
  atrapa cualquier excepción y muestra un estado de error, el mismo
  contrato que CRM-15/16 ya establecieron.
- **Conexión Directorio → Expediente**: `CustomerCrmDirectoryPage` (base
  compartida de CRM-16) gana una señal `entity_selected(row_id)` emitida al
  doble clic sobre una fila — una página de directorio no navega por sí
  misma (no conoce rutas ni otras páginas), solo emite; el workspace
  decide. `CustomersCrmWorkspace._open_customer_profile()` escucha esa
  señal desde `customers.directory`, navega a `customers.profile` y llama
  `CustomerProfilePage.show_customer(id)`. Solo `customers.directory` tiene
  un listener real hoy — leads/oportunidades/casos emiten la señal al
  vacío hasta que sus propias páginas de detalle existan (documentado como
  capacidad ya construida, lista para reutilizarse, no un `TODO` disperso).

## Verificación

```bash
python -m pytest tests/architecture/test_customers_crm_*.py \
  tests/unit/test_customers_crm_ui_workspace.py \
  tests/unit/test_customers_crm_overview_page.py \
  tests/unit/test_customers_crm_directory_pages.py \
  tests/unit/test_customers_crm_profile_page.py -q
# 22 guardrails + 23 + 13 + 22 + 15 = 95 passed
```

- 15 pruebas nuevas (`tests/unit/test_customers_crm_profile_page.py`):
  `PillTabBar` (primera pestaña activa por defecto, clic emite
  `tab_changed`, `activate()` no emite), `customer_360()` del presenter
  (lanza sin conectar, delega cuando está conectado), `CustomerProfilePage`
  (estado vacío antes de seleccionar cliente, cada pestaña se puebla
  correctamente incluyendo Crédito/Comercial/Integraciones, cambio de
  pestaña por clic, estado de error ante una excepción, `reload()` sin
  cliente es un no-op, encabezado muestra nombre y código), y la
  navegación Directorio→Expediente de extremo a extremo contra el
  workspace real.
- Un detalle de la propia suite de pruebas atrapado y corregido antes de
  dar por buena la cobertura: `SimpleNamespace(__str__=lambda self: ...)`
  NO sobrescribe `str()` (los métodos especiales se resuelven por tipo, no
  por instancia) — el primer borrador del fixture de prueba lo intentaba
  para simular `CustomerCode`, lo que habría dejado el campo "Código" sin
  verificar realmente. Corregido con una clase auxiliar mínima con
  `__str__` real, y se agregó una aserción que efectivamente lo ejercita.
- Los 22 guardrails de CRM-1 (incluyendo, otra vez, el escáner de SQL
  crudo que atrapó el choque de `select`) pasan en verde.
- 827 tests combinando toda la suite `customers`/`crm` + las cuatro fases
  de UI (CRM-14/15/16/17) pasan juntos — cero regresión.
- Sintaxis limpia en todo el repositorio.

## Pendiente (próximas fases)

- **Detalle/expediente para Leads/Oportunidades/Casos** (`crm.lead_detail`,
  `crm.opportunity_detail`, `crm.case_detail`) — `entity_selected` ya está
  emitiéndose desde sus propias páginas de directorio (CRM-16); solo falta
  que el workspace escuche y una página de detalle exista para cada uno.
- **Acciones de mutación en el Expediente** (suspender, bloquear, asignar
  propietario, capturar consentimiento, etc.) — esta fase es
  deliberadamente de solo lectura ("Customer 360, tabs, timeline,
  resúmenes"); el `ActionBar` de §27-29 sigue sin construirse.
- **Conexión real a `query_services["customer_360"]` con una conexión de
  base de datos viva** — sigue pendiente de la misma decisión de registro
  en el menú global que CRM-14/15/16 ya dejaron documentada.
