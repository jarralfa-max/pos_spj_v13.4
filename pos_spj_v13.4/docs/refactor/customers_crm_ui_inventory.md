# Clientes y CRM — inventario de UI (CRM-43, 2026-10-09)

Antes de CRM-43: 9 rutas con página (tablero, directorio, alta, expediente, edición y
cuatro directorios de sólo lectura) y 53 «sección en construcción». Hoy: 62/62 rutas con
página real; la navegación es `SideNav` por grupos con `route_id` estable y cada ruta exige
su propio permiso (antes bastaba el del grupo).

Bases comunes: `pages/_workbench.py` (`CrmWorkbenchPage`), `forms.py` (`CrmFormDialog`),
`pages/customer_sections.py` (`CustomerScopedPage` + secciones editables reutilizadas en el
expediente), `pages/_work_items.py` (seguimiento de cualquier registro), `pages/_kanban.py`,
`labels.py`, `formatting.py`.

| Ruta | Grupo | Etiqueta | Página | Permiso |
|---|---|---|---|---|
| `customers.overview` | Resumen | Resumen | `CustomersCrmOverviewPage` | `CLIENTES.acceso` |
| `customers.directory` | Clientes | Directorio | `CustomersDirectoryPage` | `CLIENTES.ver` |
| `customers.create` | Clientes | Alta rápida | `CreateCustomerPage` | `CLIENTES.crear` |
| `customers.profile` | Clientes | Expedientes | `CustomerProfilePage` | `CLIENTES.ver` |
| `customers.edit` | Clientes | Editar cliente | `EditCustomerPage` | `CLIENTES.editar` |
| `customers.duplicates` | Clientes | Duplicados | `DuplicatesPage` | `CLIENTES.duplicados.ver` |
| `crm.leads` | Prospectos | Prospectos | `LeadsPage` | `CRM.leads.ver` |
| `crm.lead_detail` | Prospectos | Detalle de lead | `LeadDetailPage` | `CRM.leads.ver` |
| `crm.lead_qualification` | Prospectos | Calificación | `LeadQualificationPage` | `CRM.leads.ver` |
| `crm.lead_conversion` | Prospectos | Conversión | `LeadConversionPage` | `CRM.leads.ver` |
| `crm.leads_discarded` | Prospectos | Leads descartados | `DiscardedLeadsPage` | `CRM.leads.ver` |
| `crm.pipeline` | Oportunidades | Pipeline | `PipelinePage` | `CRM.pipeline.ver` |
| `crm.opportunities` | Oportunidades | Oportunidades | `OpportunitiesPage` | `CRM.oportunidades.ver` |
| `crm.opportunity_detail` | Oportunidades | Detalle de oportunidad | `OpportunityDetailPage` | `CRM.oportunidades.ver` |
| `crm.forecast` | Oportunidades | Pronóstico comercial | `ForecastPage` | `CRM.forecast.ver` |
| `crm.lost_opportunities` | Oportunidades | Oportunidades perdidas | `LostOpportunitiesPage` | `CRM.oportunidades.ver` |
| `crm.calendar` | Actividades | Agenda | `AgendaPage` | `CRM.actividades.ver` |
| `crm.tasks` | Actividades | Tareas | `TasksPage` | `CRM.tareas.ver` |
| `crm.calls` | Actividades | Llamadas | `CallsPage` | `CRM.actividades.ver` |
| `crm.meetings` | Actividades | Reuniones | `MeetingsPage` | `CRM.actividades.ver` |
| `crm.visits` | Actividades | Visitas | `VisitsPage` | `CRM.actividades.ver` |
| `crm.activities` | Actividades | Notas | `NotesPage` | `CRM.notas.ver` |
| `crm.followups` | Actividades | Seguimientos | `FollowUpsPage` | `CRM.actividades.ver` |
| `crm.service_cases` | Atención al cliente | Casos | `CasesPage` | `CRM.casos.ver` |
| `crm.case_detail` | Atención al cliente | Detalle de caso | `CaseDetailPage` | `CRM.casos.ver` |
| `crm.complaints` | Atención al cliente | Quejas | `ComplaintsPage` | `CRM.casos.ver` |
| `crm.requests` | Atención al cliente | Solicitudes | `RequestsPage` | `CRM.casos.ver` |
| `crm.incidents` | Atención al cliente | Incidencias | `IncidentsPage` | `CRM.casos.ver` |
| `crm.sla` | Atención al cliente | SLA | `SlaPage` | `CRM.sla.ver` |
| `crm.escalations` | Atención al cliente | Casos escalados | `EscalationsPage` | `CRM.casos.ver` |
| `crm.quotes` | Cotizaciones | Cotizaciones | `QuotesPage` | `COTIZACIONES.ver` |
| `crm.quote_approvals` | Cotizaciones | Por aprobar | `QuoteApprovalsPage` | `COTIZACIONES.aprobar` |
| `crm.quote_detail` | Cotizaciones | Detalle de cotización | `QuoteDetailPage` | `COTIZACIONES.ver` |
| `customers.credit_requests` | Crédito | Solicitudes | `CreditRequestsPage` | `CLIENTES.credito.ver` |
| `customers.credit_profiles` | Crédito | Perfiles de crédito | `CreditProfilesPage` | `CLIENTES.credito.ver` |
| `customers.credit_exposure` | Crédito | Exposición | `CreditExposurePage` | `CLIENTES.credito.ver` |
| `customers.accounts_receivable` | Crédito | Cuentas por cobrar | `AccountsReceivablePage` | `CLIENTES.credito.ver` |
| `customers.credit_history` | Crédito | Historial | `CreditHistoryPage` | `CLIENTES.credito.historial.ver` |
| `customers.credit_alerts` | Crédito | Alertas | `CreditAlertsPage` | `CLIENTES.credito.ver` |
| `customers.segments` | Segmentación | Segmentos | `SegmentsPage` | `CRM.segmentos.ver` |
| `customers.tags` | Segmentación | Etiquetas | `TagsPage` | `CRM.etiquetas.ver` |
| `customers.territories` | Segmentación | Territorios | `TerritoriesPage` | `CRM.territorios.ver` |
| `customers.portfolios` | Segmentación | Carteras | `PortfoliosPage` | `CRM.carteras.ver` |
| `customers.ownership` | Segmentación | Propietarios | `OwnershipPage` | `CRM.propietario.ver` |
| `customers.whatsapp_summary` | Comunicaciones | WhatsApp | `CustomerScopedPage(WhatsAppSection)` | `CLIENTES.whatsapp.ver` |
| `customers.privacy_requests` | Privacidad | Solicitudes | `PrivacyRequestsPage` | `CLIENTES.privacidad.solicitud.ver` |
| `customers.retention` | Privacidad | Retención | `RetentionPage` | `CLIENTES.configuracion.ver` |
| `customers.anonymization` | Privacidad | Anonimización | `AnonymizationPage` | `CLIENTES.privacidad.solicitud.ver` |
| `customers.data_exports` | Privacidad | Exportaciones | `DataExportsPage` | `CLIENTES.exportar` |
| `customers.data_quality` | Control | Calidad de datos | `DataQualityPage` | `CLIENTES.calidad.ver` |
| `customers.imports` | Control | Importaciones | `ImportsPage` | `CLIENTES.importar` |
| `customers.audit` | Control | Auditoría | `AuditPage` | `CLIENTES.auditoria.ver` |
| `customers.settings` | Control | Configuración | `SettingsPage` | `CLIENTES.configuracion.ver` |

Diálogos: todos son `CrmFormDialog` (formularios declarativos) salvo `CustomerAddressDialog`
(componente canónico `AddressInput` con búsqueda de direcciones de Integraciones).

Expediente (§27): Resumen, Identidad (+ datos fiscales y cuentas comerciales), Contactos,
Direcciones, Actividad (actividades/tareas/notas), Oportunidades, Comercial (resumen +
compras/pagos/pedidos/cotizaciones/devoluciones/productos frecuentes), Crédito, Atención,
Consentimientos (+ preferencias), Integraciones, Auditoría. Acciones: Nueva venta, Ver CxC,
Editar, Estado…, Actualizar.

`customers.quote_history` (§9) se retiró del menú el 2026-10-09: duplicaba la sección «Cotizaciones». Las cotizaciones de un cliente siguen en la pestaña «Cotizaciones» de su expediente.

También se retiraron del menú (2026-10-09) once entradas que repetían una pestaña del expediente: cuentas comerciales, contactos, direcciones, datos fiscales (pestañas Identidad, Contactos y Direcciones), consentimientos y preferencias (Consentimientos), compras, pedidos, devoluciones y productos frecuentes (Comercial); «Notificaciones» mostraba la misma sección que «WhatsApp». El menú queda en 53 entradas (cajero 22, solo lectura 37).
