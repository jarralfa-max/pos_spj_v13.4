# Clientes y CRM — inventario funcional y matriz de preservación (CRM-43, 2026-10-09)

Acciones: PRESERVE (se conserva tal cual), MOVE, REFACTOR, MERGE, REWRITE,
DELETE_DUPLICATE, BLOCKED. Evidencia = prueba o verificación sobre la copia de la base real.

| Función original | Ubicación actual | Destino canónico | Acción | Evidencia |
|------------------|------------------|------------------|--------|-----------|
| Alta rápida de cliente | `pages/create_customer_page.py` → `CreateCustomerUseCase` | igual | PRESERVE | `test_customers_crm_create_customer_page.py` |
| Edición de identidad + cumpleaños | `pages/edit_customer_page.py` | igual | PRESERVE | `test_customers_crm_edit_customer_page.py` |
| Directorio de clientes | `pages/customers_directory_page.py` | `CustomerDirectoryQueryService` (§57/§83) | REWRITE | `TestCustomersDirectoryPage`, `test_directory_keeps_suspended_customers` |
| Expediente 360 | `pages/customer_profile_page.py` | `Customer360QueryService` + secciones | REFACTOR | `test_customers_crm_profile_page.py`, recorrido real |
| Estado del cliente (activar/suspender/bloquear/baja/cerrar) | — (sin pantalla) | Expediente → «Estado…» | REWRITE | `flow_dir` real, `TestCustomerMaster` |
| Contactos / direcciones / datos fiscales | sólo lectura en el expediente | `customer_sections.py` (+ rutas por cliente) | REWRITE | recorrido del cajero, `test_contact_data_is_masked_by_permission` |
| Cuentas comerciales | sólo al convertir prospecto | `account_use_cases.py` + `AccountsSection` | REWRITE | `test_commercial_account_create_and_update` |
| Prospectos: alta, asignación, contacto, seguimiento, calificación, descalificación, conversión, pérdida, archivo | casos de uso sin pantalla | `pages/leads_pages.py` | REWRITE | `TestLeadPages`, `test_lead_to_won_opportunity` |
| Oportunidades, etapas, ganar/perder/pausar/cancelar/reabrir, productos de interés | casos de uso sin pantalla | `pages/opportunity_pages.py` | REWRITE | `test_lead_to_won_opportunity`, flujo real |
| Pipeline Kanban configurable | etapas sembradas sin edición | Kanban + `stage_definition_use_cases.py` | REWRITE | `TestKanban`, `TestPipelineConfiguration` |
| Pronóstico | `SalesPipelineForecastQueryService` sin pantalla | `ForecastPage` | REWRITE | flujo real |
| Actividades, tareas, notas, recordatorios, agenda | casos de uso sin pantalla | `activity_pages.py`, `_work_items.py` | REWRITE | `test_activity_scheduled_in_utc_is_not_overdue_early` |
| Casos, SLA, escalamiento, resolución | directorio de sólo lectura | `service_pages.py` + migr. 315 | REWRITE | `TestServiceCases`, `TestServiceLevelSeed`, flujo real |
| Crédito: solicitud→revisión→aprobación, límite, suspensión, bloqueo | casos de uso sin pantalla | `credit_pages.py` | REWRITE | `TestCredit` |
| Elegibilidad de venta a crédito (POS) | `CheckCreditSaleEligibilityUseCase` | igual, permiso y mensajes corregidos | REFACTOR | `test_cashier_checks_eligibility_with_spanish_reasons` |
| Consentimientos, preferencias | casos de uso sin pantalla | `privacy_pages.py` (secciones) | REWRITE | flujo real |
| Solicitudes ARCO, anonimización, retención | casos de uso sin pantalla | `privacy_pages.py` | REWRITE | `test_anonymization_needs_a_second_person` |
| Exportaciones (§48) | no existían | `ExportCustomerDataUseCase` + `DataExportsPage` | REWRITE | `TestPrivacyAndExports` |
| Segmentos, etiquetas, territorios, carteras, responsables | casos de uso sin pantalla | `segmentation_pages.py` | REWRITE | flujo real |
| Duplicados y fusión | casos de uso sin pantalla | `control_pages.DuplicatesPage` | REWRITE | flujo real |
| Calidad de datos | casos de uso sin pantalla | `control_pages.DataQualityPage` | REWRITE | flujo real |
| Importación de clientes | casos de uso sin pantalla | `control_pages.ImportsPage` (mapeo + vista previa) | REWRITE | flujo real |
| Auditoría | sólo línea de tiempo por cliente | `AuditTrailQueryService` + `AuditPage` | REWRITE | flujo real |
| Automatizaciones (§56) | motor sin pantalla; 1 de 7 disparadores por tiempo, sin programador | `SettingsPage` + ciclo de fondo (`run_crm_background_cycle`) | REWRITE | flujo real; `test_crm43_automation_background.py` |
| Recordatorios y campana de avisos | se guardaban sin entregarse; campana sin fuente | `DispatchDueCRMRemindersUseCase` + `NotificationInboxFeed` | REWRITE | `live_bg.py` sobre la base real, `test_notification_inbox_feed.py` |
| Historial comercial (§28) | sólo timeline de auditoría | `CustomerHistoryQueryService.get_*` + `commercial_pages.py` | REWRITE | recorrido del cajero |
| Proyección de compras desde Ventas | cableado en `core/events` (borrado) | `customers/integrations/sales_wiring.py` + migr. 316 | MOVE | `TestSalesProjectionWiring`, `TestSalesProjectionBackfill` |
| Tablero CRM | 6 KPI + 1 gráfica | + 6 KPI secundarios + 6 gráficas (`CRMInsightsQueryService`) | REFACTOR | captura real |
| Navegación a Ventas / CxC desde el expediente | `NavigationIntent` | igual | PRESERVE | `test_crm_32_navigation_intent.py` |
| Directorios de sólo lectura de prospectos/oportunidades/casos | `leads_directory_page.py` … `_directory_base.py` | bandejas operativas | DELETE_DUPLICATE | archivos borrados, 0 consumidores |
| Métodos `customers/leads/opportunities/cases_directory` del presentador | presentador | `presenter.read(...)` | DELETE_DUPLICATE | 0 consumidores |
| Cotizaciones (§50) | no existían (cascarones sin llamadores; tabla legacy sin escritor) | `backend/*/quotes/` + `pages/quote_pages.py` | REWRITE | `test_crm43_quotes.py`, recorrido real cajero → gerente |
