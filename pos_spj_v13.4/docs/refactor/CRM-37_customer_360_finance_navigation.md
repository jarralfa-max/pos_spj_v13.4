# CRM-37 — Fase 3: segunda ruta real de NavigationIntent (Customer 360 → CxC)

Fecha: 2026-08-16. Continuación del cut-over a petición del usuario de
retomar "FASE 3 — CUSTOMER 360 + CONECTIVIDAD ENTRE VENTANAS".

## Auditoría de las 13 rutas que pide Fase 3

Antes de construir nada se verificó, una por una, cuáles de las 13
navegaciones que el prompt maestro lista (nueva venta, historial,
oportunidad, actividades, tarea, nota, WhatsApp, crédito, CxC, cobranza,
caso de servicio, delivery, fidelidad) tienen HOY un destino real al otro
lado:

- **Nueva venta**: ya conectado (CRM-32).
- **Oportunidades/Actividades/Tareas/Notas/Casos de servicio**: las
  páginas de directorio (`OpportunitiesDirectoryPage`, etc., CRM-16) son
  listados de solo búsqueda — **sin botón "crear nuevo" y sin filtro por
  cliente** (`CustomerCrmDirectoryPage`, la base compartida, no lo
  soporta). Navegar ahí hoy no ahorraría nada: el usuario llegaría a un
  listado general, no a "los datos de este cliente". Construir eso bien
  es una feature nueva (filtro + creación), no una reconexión — no se
  fabricó una navegación decorativa a una pantalla que no puede recibir
  contexto todavía.
- **CxC**: `AccountsReceivablePage` (Finanzas) ya tiene un botón real
  ("Ver resumen CRM") que muestra exactamente este resumen — pero pide el
  id legacy del cliente escrito A MANO en un `QInputDialog`. Destino real,
  con una fricción exacta a la que Fase 3 apunta ("sin volver a buscar el
  cliente"). **Implementado.**
- **Crédito actual**: ya vive DENTRO del propio Expediente (pestaña
  "Crédito", `credit_summary` — CRM-27 lo alimenta desde
  `customer_credit_profiles`) — no necesita navegación cruzada, el dato
  ya está ahí sin salir de la página.
- **WhatsApp/Delivery/Fidelidad**: sus módulos de escritorio
  (`ModuloWhatsApp`/`ModuloDelivery`/`ModuloTarjetas`) no tienen ningún
  método `aplicar_contexto`-equivalente ni una forma de recibir "muéstrame
  a este cliente" — construirlo requiere entender primero cada uno de
  esos tres módulos a fondo, no se hizo en esta pasada.
- **Cobranza / Solicitud de crédito**: cobranza es una vista distinta en
  el mismo módulo Finanzas (`CollectionsPage`) sin selector de cliente
  tampoco; solicitud de crédito es una acción de workflow
  (`RequestCustomerCreditUseCase`, CRM-8) que pertenece dentro del propio
  Expediente como botón de acción, no como salto a otro módulo — candidato
  para una fase futura, no de navegación cruzada.

## Qué se construyó

- **`AccountsReceivablePage.show_crm_summary_for(cliente_id)`** (nuevo):
  extrae la lógica de `_show_crm_summary()` (que seguía intacta, sigue
  pidiendo el id por `QInputDialog` cuando se usa desde su propio botón)
  a un método invocable directamente con un id ya conocido.
- **`FinanceView.aplicar_contexto(context)`** (nuevo): cambia a la
  sección CxC (`set_active_submodule("cxc")`, mecanismo ya existente) y
  llama `show_crm_summary_for` con `context["legacy_customer_id"]`.
  `FinanceView` nunca toca la conexión a BD ni el `AppContainer` por
  diseño explícito (ver su propio docstring) — por eso NO resuelve el
  bridge él mismo.
- **`interfaz/main_window.py::_resolve_legacy_customer_id`** (nuevo): el
  único lugar que sí puede tocar el bridge en nombre de un destino que no
  puede hacerlo. `_handle_navigation_intent` ahora resuelve
  `customer_id` → `legacy_customer_id` (vía `EnsureLegacyCustomerBridgeUseCase`,
  CRM-36 — crea el bridge inverso si hace falta) y lo agrega al `context`
  ANTES de llamar `aplicar_contexto`, para cualquier destino que lo
  necesite. `ModuloVentas.aplicar_contexto` sigue resolviendo por su
  cuenta como antes (tiene acceso al contenedor) — el campo extra en el
  contexto simplemente no lo usa, aditivo, cero riesgo.
- **`CustomerProfilePage`**: nuevo botón "Ver CxC" junto a "Nueva venta".

## Verificación

```bash
python -m pytest tests/unit/test_crm_32_navigation_intent.py \
  tests/unit/test_customers_crm_profile_page.py \
  tests/integration/finance/test_crm_37_receivables_navigation.py \
  tests/integration/finance/test_finance_ui_shell.py \
  tests/architecture/test_customers_crm_*.py -v
```
50 tests pasando (6 nuevos de esta fase), cero regresiones. Un hallazgo
real durante las pruebas: `crm_receivable_summary` NUNCA retorna `None`
para un cliente sin historial de CxC (retorna un resumen con exposición
cero, `SIN_MOVIMIENTOS`) — solo retorna `None` si la consulta lanza una
excepción real. El test inicial asumía lo contrario; se corrigió el test
para reflejar el comportamiento real (no se tocó el código de producción,
que ya era correcto, solo la prueba estaba mal planteada).

## Explícitamente NO tocado en esta fase

Ver la sección "Auditoría de las 13 rutas" arriba — cada destino no
construido tiene su razón documentada, ninguno se fabricó a medias.
