# CRM-12 — QueryServices: Customer 360, Historial, Pipeline, Actividades, Casos, Crédito

Fecha: 2026-08-13. Depende de CRM-3 (`CustomerProfileQueryService`),
CRM-5 (`OpportunityDirectoryQueryService`/`SalesPipelineForecastQueryService`),
CRM-6 (`CRMActivityQueryService`/`CRMTaskQueryService`), CRM-7
(`ServiceCaseQueryService`/`SLAQueryService`), CRM-8
(`CustomerCreditQueryService`), CRM-9 (`CustomerConsentQueryService`),
CRM-10 (`CustomerOwnershipQueryService`/`CustomerPortfolioQueryService`/
`CustomerSegmentationQueryService`), CRM-11
(`CustomerDuplicateQueryService`/`CustomerDataQualityQueryService`) — esta
fase es puramente de composición, no reconstruye ninguna de ellas.
Fuente de diseño: `docs/refactor/customers_crm_master_prompt.md` §27-29, §57.

## Hallazgo inicial: la mitad de §57 ya existía

Antes de escribir código se auditó el §57 completo contra el árbol real de
`backend/application/*/queries/`. Dos servicios que parecían pendientes
resultaron ya completos:

- **`CustomerDirectoryQueryService`** — ya es literalmente
  `CustomerProfileQueryService.list_directory()` (CRM-3), con soporte
  completo de los seis ejes de alcance (OWN/TEAM/BRANCH/TERRITORY/
  PORTFOLIO/COMPANY). No se creó un archivo nuevo.
- **`CustomerCreditSummaryQueryService`** — ya es
  `CustomerCreditQueryService.get_summary()` (CRM-8), cuyo propio
  docstring ya decía "§27-29's Customer 360 'Crédito' tab" desde que se
  escribió. Confirmación de que CRM-8 fue construido anticipando esta
  fase.
- **`OpportunityPipelineQueryService`/`OpportunityForecastQueryService`**
  — ya consolidados en `SalesPipelineForecastQueryService` (CRM-5), cuyo
  propio docstring cita el mismo §19-22 de "pipeline total/ponderado...
  forecast operativo".
- **`ServiceCaseDirectoryQueryService`/`ServiceCaseDetailQueryService`**
  — ya consolidados en `ServiceCaseQueryService.list_directory()`/
  `get_profile()` (CRM-7).
- **`LeadDetailQueryService`** — ya es `LeadDirectoryQueryService.get_profile()`
  (CRM-4).

Esto redujo el alcance real de CRM-12 a: el agregador (`Customer360QueryService`),
el historial cruzado (`CustomerHistoryQueryService`), la búsqueda rápida
(`CustomerLookupQueryService`), un calendario de CRM
(`CRMCalendarQueryService`), y dos métodos aditivos (`list_for_customer`)
en servicios que ya existían pero solo sabían filtrar por propietario/
asignado, no por cliente.

## Decisiones de alcance (documentadas, no adivinadas)

- **`CustomerHistoryQueryService` es la única excepción documentada a "no
  tocar tablas de otro bounded context"** — pero solo para *lectura*. Las
  fases CRM-8/9/11 sostuvieron esa regla para *escrituras* (CxC, fusión,
  anonimización); leer para una vista agregada de solo lectura es un
  problema distinto, y el precedente ya existía
  (`CustomerAccountsReceivableSummaryQuery` lee `cuentas_por_cobrar` de
  Finanzas de forma read-only desde CRM-8). Correlaciona por
  `customer_id` cuando la tabla de auditoría de origen ya lo tiene
  (customers, customer_credit, customer_privacy) o vía join cuando no
  (`crm_audit_log` → `opportunities.customer_id`;
  `customer_service_audit_log` → `service_cases.customer_id`). **Leads
  quedan deliberadamente fuera** del historial: un Lead no tiene
  `customer_id` hasta que se convierte, y la Oportunidad resultante ya
  continúa el rastro desde ahí.
  Cada tabla de origen se verifica con `_table_exists()` antes de
  consultarla — un despliegue que no ha corrido todas las migraciones de
  CRM-8/9/10 (o un fixture de test que solo carga un schema) contribuye
  "nada" en vez de fallar.
- **`Customer360QueryService` degrada con gracia por sección, pero no en
  el perfil base.** Si el llamador no puede ver al cliente en absoluto
  (`CustomerScopeError`/`CustomerNotFoundError` en el perfil), toda la
  llamada falla — igual que cualquier otro query service. Pero cada
  sección secundaria (crédito, consentimiento, propietario, cartera,
  segmentos/etiquetas, pipeline, casos, actividades, tareas, duplicados,
  calidad, historial) está gateada por su propio permiso granular vía su
  propio servicio ya existente, y si el llamador no lo tiene, esa sección
  devuelve `None`/`[]` en vez de tumbar la vista completa — ningún rol
  del catálogo sugerido en §59-61 tiene los ~12 permisos distintos que
  esta vista compone a la vez, así que fallar todo por uno faltante
  habría hecho la pantalla inutilizable para casi cualquier rol real.
- **`CustomerLookupQueryService` es el único query service de este
  paquete sin restricción de alcance (`CustomerDataScopeResolver`).** §49:
  "Ventas consume `CustomerLookupQueryService`" — un cajero necesita
  encontrar cualquier cliente activo, no solo los de su propio
  OWN/TEAM/BRANCH. Gateado por `SEARCH` (ya existente, distinto de
  `GLOBAL_SEARCH`), no por alcance.
- **`CRMCalendarQueryService` excluye recordatorios deliberadamente.**
  `CRMReminder` no tiene un "cuándo" propio más allá de la tarea/actividad
  a la que está adjunto (§26: "CRM solo define recordatorio/destinatario")
  — mostrar la tarea/actividad ya es suficiente para un calendario; el
  recordatorio es un mecanismo de entrega, no una segunda ocurrencia.
- **`list_for_customer` se agregó como método aditivo, no como servicio
  nuevo**, a `OpportunityDirectoryQueryService` (CRM-5) y
  `ServiceCaseQueryService` (CRM-7) — ambos ya sabían filtrar "lo que el
  usuario posee" (`list_owned_by`) pero no "lo que pertenece a este
  cliente, dentro de lo que el usuario puede ver". El repositorio
  correspondiente ganó su propio `list_for_customer` sin filtro de
  alcance (trae todo lo del cliente); el query service aplica
  `_in_scope()` después, mismo patrón que `get_profile()` ya usaba.
- **No se agregó ningún permiso nuevo.** Todos los servicios de esta fase
  reutilizan permisos ya existentes desde CRM-2 (`AUDIT_VIEW` para
  historial, `SEARCH` para lookup, `ACTIVITIES_VIEW`+`TASKS_VIEW` para el
  calendario). Segunda fase consecutiva sin adición retroactiva (después
  de CRM-11).

## Aplicación (extiende `backend/application/customers/` y `backend/application/crm/`)

- **`queries/customer_history_query_service.py`** — `CustomerHistoryQueryService`,
  `CustomerTimelineEntry`.
- **`queries/customer_lookup_query_service.py`** — `CustomerLookupQueryService`,
  `CustomerLookupResult`. Usa `CustomerRepository.search_lookup()` (nuevo,
  aditivo — LIKE parametrizado sobre nombre/razón social/teléfono/correo,
  nunca hidrata el agregado completo).
- **`crm/queries/crm_calendar_query_service.py`** — `CRMCalendarQueryService`,
  `CRMCalendarEntry`.
- **`queries/customer_360_query_service.py`** — `Customer360QueryService`,
  `Customer360View`. Composición pura de 12 servicios ya existentes +
  los tres nuevos de esta fase.
- **`crm/queries/opportunity_directory_query_service.py`**,
  **`customer_service/queries/service_case_query_service.py`** — ambos
  ganan `list_for_customer()`.

## Verificación

```bash
python -m pytest tests/integration/customers/test_customer_360_application.py \
  tests/architecture/test_customers_crm_*.py -v
# 15 passed (Customer 360/historial/lookup/calendario) + 21 passed, 1 skipped (guardrails)
```

- 15 tests nuevos de integración con SQLite real cargando las cinco
  schemas del módulo Clientes/CRM en una sola conexión (`full_crm_conn`,
  fixture nueva en `tests/integration/customers/conftest.py`, incluye la
  tabla legacy `cuentas_por_cobrar` mínima que `CustomerCreditQueryService`
  ya necesitaba desde CRM-8): agregación completa del 360, degradación
  por sección sin permiso, historial cruzado ordenado y correctamente
  correlacionado (una oportunidad de OTRO cliente no aparece), búsqueda
  rápida, calendario filtrado por rango de fecha, y los dos métodos
  `list_for_customer` nuevos con su propio filtro de alcance/enmascarado
  de casos sensibles.
- Los 22 guardrails de CRM-1 se re-ejecutaron completos y siguieron en
  verde sin ajustes.
- 707 tests de `tests/unit/{customers,crm,customer_credit,customer_privacy,
  customer_service}/` + sus contrapartes de integración pasan juntos
  (692 previos + 15 nuevos) — cero regresión por los dos métodos aditivos.
- Sintaxis limpia en todo el repositorio.

## Pendiente (próximas fases)

- **`CustomerIntegrationSummaryQueryService`** (§57) — necesita datos de
  WhatsApp/Fidelidad/Pedidos que CRM-13 (Integraciones) todavía no expone
  de forma consumible desde este módulo; explícitamente diferido, no
  implementado.
- **`CustomerDashboardQueryService`** (§57) — no nombrado por el usuario
  al invocar esta fase ("Customer 360, historial, pipeline, actividades,
  casos, crédito"); un dashboard es más una composición de UI sobre los
  query services ya existentes que un nuevo agregador de backend —
  diferido a cuando exista una pantalla real que lo consuma (CRM-14+).
- **Exportación (§48)** sigue sin consumidor — no nombrada por el usuario
  en ninguna fase invocada hasta ahora.
- `Customer360QueryService`/`CustomerHistoryQueryService` son el
  consumidor natural de una futura tab de UI "Expediente del cliente"
  (CRM-14+) — hoy solo existen como servicios de aplicación, sin UI.
