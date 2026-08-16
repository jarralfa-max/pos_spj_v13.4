# CRM-42 — Fase 8: verificación de Frontend/Design System (un hallazgo real, documentado, no retrofitteado)

Fecha: 2026-08-16. A petición del usuario de retomar "FASE 8 — FRONTEND /
DESIGN SYSTEM". Como CRM-39 (Fase 5), esta terminó siendo mayormente una
auditoría de verificación — la mayor parte ya estaba correctamente
construida.

## Guardrails re-verificados (incluye lo agregado esta sesión)

```bash
python -m pytest tests/architecture/test_customers_crm_uses_canonical_design_system.py \
  tests/architecture/test_customers_crm_has_no_hardcoded_colors.py \
  tests/architecture/test_customers_crm_has_no_inline_styles.py \
  tests/architecture/test_customers_crm_has_no_emoji_icons.py \
  tests/architecture/test_customers_crm_ui_has_no_repositories.py \
  tests/architecture/test_customers_crm_ui_has_no_sql.py \
  tests/architecture/test_customers_crm_ui_does_not_receive_app_container.py -v
```
9/9 pasan — incluyendo los botones "Nueva venta"/"Ver CxC" agregados en
CRM-32/CRM-37 esta misma sesión: confirmado que no introdujeron colores
hardcoded, widgets ad-hoc, SQL directo, ni acceso al `AppContainer`.

## Componentes nombrados por el prompt — confirmados reales, no aspiracionales

`AddressInput`, `CustomerSearchBox`, `KPIBar`, `KPICard`,
`TaxIdentifierInput`, `WorklistPage` existen todos como archivos reales en
`frontend/desktop/components/` — ninguno es un nombre aspiracional del
prompt sin construir (patrón ya visto varias veces en fases anteriores:
"el prompt nombra un concepto, a veces con otro nombre real").

## Touch UI — ya resuelto a nivel de componente central, no por página

`EmailInput`/`PhoneInput`/`TaxIdentifierInput` ya implementan
`setMinimumHeight(TouchTarget.INPUT_HEIGHT)` (hit target táctil) y
`attach_virtual_keyboard_action(self)` (ícono de teclado virtual)
**dentro del propio componente** — cualquier página que use estos inputs
hereda el cumplimiento automáticamente, sin que cada pantalla tenga que
reimplementarlo. Exactamente el patrón correcto que pide el prompt
("mejorar el componente central, no duplicar localmente"). Confirmado en
los tres componentes, no solo asumido de uno.

## Hallazgo real: `CustomerCrmDirectoryPage` duplica el patrón de `WorklistPage`

`WorklistPage` (`frontend/desktop/components/worklist_page.py`) es el
scaffold canónico de "página de listado": header + búsqueda/filtro +
tabla + estados vacío/error + paginación + panel maestro-detalle
opcional + KPIs opcionales. Las cuatro páginas de directorio de
Clientes/CRM (`CustomersDirectoryPage`/`LeadsDirectoryPage`/
`OpportunitiesDirectoryPage`/`ServiceCasesDirectoryPage`, CRM-16) NO
extienden `WorklistPage` — extienden `CustomerCrmDirectoryPage`
(`pages/_directory_base.py`), una base propia que reconstruye header +
búsqueda + filtro + tabla + estado vacío desde cero. El propio docstring
de ese archivo lo admite: se modeló sobre
`transfers/pages/base_page.py`, no sobre `WorklistPage`.

**Por qué no se corrigió en esta fase**: `CustomerCrmDirectoryPage`
compone ÚNICAMENTE primitivas canónicas (`SearchInput`,
`SearchableComboBox`, `StandardTable`, `PageHeader`, `ViewState`) — cero
widgets ad-hoc, cero colores hardcoded, cero estilos inline. No es una
violación de "no usar el design system"; es una segunda implementación
del MISMO patrón de scaffold con las MISMAS piezas. Migrar las cuatro
páginas de directorio (ya en producción, con tests reales) a
`WorklistPage` es un refactor real — no un fix de una hora — que tocaría
cuatro páginas vivas y su base compartida. Se documenta como deuda
identificada en vez de apurar un retrofit de alto riesgo al final de una
sesión ya larga.

## Explícitamente NO tocado (con razón)

- **`AddressInput`/`CustomerSearchBox` sin consumidores en customers_crm**:
  investigado — no es una violación. `create_customer_page.py`/
  `edit_customer_page.py` (CRM-18) no capturan dirección en absoluto
  todavía (alcance original: identidad/contacto/fiscal, no dirección) —
  no hay ninguna pantalla que debiera usar `AddressInput` y no lo hace.
  `CustomerSearchBox` está pensado para que OTROS módulos busquen y
  seleccionen un cliente (p.ej. Ventas, si se migra fuera de legacy) — el
  propio directorio de clientes no necesita "buscar un cliente para
  seleccionarlo", ya es la lista misma.
- **Consolidación completa del "Customers CRM Workspace"**: ya existe
  (`CustomersCrmWorkspace`, CRM-14) — overview/directorio/perfil/crear-
  editar/leads/oportunidades/actividades/casos ya conviven en un único
  workspace con navegación compartida, confirmado en fases anteriores de
  esta sesión (CRM-32). Nada que consolidar de nuevo.

## Conclusión

Fase 8 no requería construcción nueva: el design system para Clientes/CRM
ya está correctamente aplicado, incluyendo lo agregado esta sesión. El
único hallazgo real (`WorklistPage` vs `CustomerCrmDirectoryPage`) es
deuda de reutilización de código, no una violación de las reglas
explícitas del prompt (sin ad-hoc, sin hardcoded, sin SQL en UI) — todas
esas ya están limpias y verificadas.
