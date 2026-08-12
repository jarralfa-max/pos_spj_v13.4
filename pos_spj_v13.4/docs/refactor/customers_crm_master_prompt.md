# CRM / Customers — Master Prompt (fuente de verdad de diseño)

> Pegado por el usuario el 2026-08-08 como especificación maestra para la
> transformación enterprise del bounded context Clientes/CRM. Se conserva
> **verbatim** aquí porque excede lo que cabe de forma fiable en el contexto
> de conversación a lo largo de las ~23 fases (CRM-0..CRM-23) que va a tomar
> construir esto. Toda fase futura debe releer este archivo, no asumir que el
> contenido sigue "vivo" en la conversación.
>
> **Nota de truncamiento:** el mensaje original se cortó a la mitad de la
> §94 ("QSS inli…"). Las secciones 95–101 (fases CRM-0..CRM-23, tests de
> seguridad/funcionales, guardrails §98, Definición de Terminado §99, Reporte
> Final §100, Regla Final §101) fueron entregadas por el usuario en un
> mensaje **anterior** de esta misma conversación y están resumidas en
> `docs/architecture/CRM_0_CUSTOMER_MASTER_AUDIT.md`. Si en una sesión futura
> falta contexto de qué viene después de la §94, pedir al usuario el resto
> del prompt antes de asumir contenido.

Relación con otros documentos:
- `docs/architecture/CRM_0_CUSTOMER_MASTER_AUDIT.md` — auditoría CRM-0 (qué existe hoy, qué está duplicado, qué falta).
- `docs/refactor/MODULE_QUEUE.md` — cola de módulos del *otro* pipeline (`SPJ_REFACTOR_SKILL.md`, ejecutado por Codex). `CLIENTES` ahí ya está `DONE`, pero se refiere solo a sacar SQL/commit de la UI y UUIDv7 — **no** a la transformación CRM enterprise descrita en este archivo. No confundir ambos pipelines ni marcar `CLIENTES` como pendiente en `MODULE_QUEUE.md` por este trabajo; el CRM enterprise es una iniciativa nueva y separada, con su propia numeración `CRM-0`..`CRM-23`.
- Cada fase `CRM-N` debe producir su propio `docs/refactor/CRM-N_<tema>.md`, siguiendo la convención ya usada por `CASH-N_*.md`, `LOSS-N_*.md`, `TRF-N_*.md`.

---

## 1. Regla principal: preservación funcional completa

No eliminar, reducir, simplificar ni ocultar ninguna función válida del módulo original.

Antes de modificar código se debe inventariar: pantallas, páginas, diálogos, pestañas, acciones, botones, campos, búsquedas, filtros, tablas, historiales, reportes, exportaciones, importaciones, reglas, validaciones, permisos, eventos, integraciones, atajos, automatizaciones.

Clasificar cada elemento como: `PRESERVE`, `MOVE`, `REFACTOR`, `MERGE`, `REWRITE`, `DELETE_DUPLICATE`, `BLOCKED`.

Una función solo puede eliminarse cuando: (1) existe implementación canónica equivalente o superior, (2) está protegida por tests, (3) se confirmó que no quedan consumidores, (4) no existen imports dinámicos, (5) no existen rutas ocultas, (6) no rompe CI, (7) la función sigue disponible para el usuario.

Crear:
- `docs/refactor/customers_crm_feature_inventory.md`
- `docs/refactor/customers_crm_legacy_inventory.md`
- `docs/refactor/customers_crm_ui_inventory.md`
- `docs/refactor/customers_crm_permission_inventory.md`
- `docs/refactor/customers_crm_integration_map.md`
- `docs/refactor/customers_crm_legacy_removal_report.md`

Tabla obligatoria: `| Función original | Ubicación actual | Destino canónico | Acción | Evidencia |`

## 2. Principio rector

- **Customer Master** — identidad maestra.
- **CRM** — relación comercial.
- **Customer Service** — seguimiento y atención.
- **Customer Credit** — perfil comercial de crédito.
- **Customer Privacy** — consentimiento y derechos de datos.
- **Customer Intelligence** — proyecciones operativas y segmentación.

Regla: Clientes identifica. CRM relaciona. Ventas vende. Fidelidad recompensa. Finanzas contabiliza. WhatsApp conversa. Delivery entrega. BI analiza. Clientes/CRM no debe replicar responsabilidades de otros bounded contexts.

## 3. Separación definitiva entre Clientes y Fidelidad

Clientes y Fidelidad permanecen como módulos globales independientes.

**Clientes/CRM es dueño de:** identidad, expediente, cuentas comerciales, contactos, prospectos, leads, oportunidades, actividades, tareas, interacciones, casos de atención, direcciones, datos fiscales, preferencias, consentimientos, segmentación, propietarios comerciales, territorios, perfil de crédito, calidad de datos, duplicados, fusiones.

**Fidelidad es dueño de:** programas, membresías, puntos, niveles, recompensas, retos, misiones, cupones, vales, sorteos, tarjetas físicas/digitales, QR de fidelidad.

Clientes puede mostrar una proyección resumida de Fidelidad, pero no administrar sus entidades. Prohibido dentro de Clientes: `points_balance`, `points_ledger`, `loyalty_card_template`, `loyalty_card_batch`, `loyalty_qr`, `coupon_ledger`, `voucher_ledger`, `tier_history`.

## 4. Contexto no negociable

SPJ ERP/POS sigue en desarrollo activo; no hay datos productivos que obliguen a conservar arquitectura incorrecta. Por tanto, prohibido conservar: código muerto, módulos/services/repositories paralelos, tablas paralelas, `CustomerService` monolítico genérico, IDs enteros funcionales, `AUTOINCREMENT`, `lastrowid`, casts `int(..._id)`, UUID4 persistente, `legacy_id`, lectura/escritura dual, fallback UUID→entero, SQL en PyQt, commit/rollback en UI, `AppContainer` completo en vistas, `container.db`, lógica CRM en widgets, autorización por nombre de rol, estilos inline, colores hardcodeados, emojis como iconos, Design System paralelo, mezcla Clientes/Fidelidad, mezcla CRM/BI, mezcla oportunidades/cotizaciones, mezcla casos de atención/conversaciones WhatsApp.

Resultado esperado: born-clean, born-UUIDv7, modular, domain-driven, workflow-driven, configuration-driven, multi-branch, multi-channel, offline-first, privacy-aware, consent-aware, event-driven, audit-ready, responsive, touch-ready, sin legacy, sin hardcode.

## 5. Skills obligatorios

Leer (orden de prioridad ante conflicto, gana el primero):
1. `docs/skills/SPJ_REFACTOR_SKILL.md`
2. `docs/skills/SPJ_UI_UX_ARCHITECTURE_SKILL.md`
3. `docs/skills/SPJ_BUGFIX_AUDIT_CORRECTION_SKILL.md`
4. Los demás skills aplicables en `docs/skills/`

## 6. Responsabilidad del bounded context

**Es dueño de:** `Customer`, `CustomerAccount`, `CustomerContact`, `CustomerAddress`, `CustomerTaxProfile`, `CustomerCommercialProfile`, `CustomerCreditProfile`, `CustomerConsent`, `CustomerCommunicationPreference`, `CustomerSegment`, `CustomerTag`, `CustomerRelationship`, `CustomerOwnership`, `CustomerTerritory`, `Lead`, `LeadQualification`, `Opportunity`, `OpportunityStage`, `OpportunityActivity`, `CRMActivity`, `CRMTask`, `CRMNote`, `CRMInteraction`, `CustomerServiceCase`, `ServiceCaseActivity`, `CustomerDuplicateCandidate`, `CustomerMergeRecord`, `CustomerPrivacyRequest`, `CustomerDataQualityIssue`.

**No es dueño de:** `Sale`, `Order`, `Quote`, `Payment`, `AccountsReceivable`, `LoyaltyAccount`, `LoyaltyCard`, `WhatsAppConversation`, `DeliveryOrder`, `Invoice`, `JournalEntry` — se muestran vía proyecciones/enlaces.

## 7. Módulos globales

Catálogo global (entradas independientes): Inicio, Punto de Venta, Pedidos y Delivery, **Clientes y CRM**, Fidelidad, WhatsApp, Productos, Inventario, Transferencias, Compras, Procesamiento Cárnico, Mermas, Caja, Finanzas, RRHH, Activos, Inteligencia y Reportes, Configuración.

Nombre visible: "Clientes" o "Clientes y CRM". **Identidad interna canónica: `customers_crm`.**

## 8. Navegación interna enterprise (`ModuleSidebar`, grupos expandibles)

```text
Resumen
Clientes: Directorio, Expedientes, Cuentas comerciales, Contactos, Direcciones, Datos fiscales, Duplicados
Prospectos: Prospectos, Leads, Calificación, Conversión, Leads descartados
Oportunidades: Pipeline, Oportunidades, Pronóstico comercial, Actividades pendientes, Oportunidades perdidas
Actividades: Agenda, Tareas, Llamadas, Reuniones, Visitas, Notas, Seguimientos
Atención al cliente: Casos, Quejas, Solicitudes, Incidencias, SLA, Casos escalados
Relación comercial: Compras, Pedidos, Cotizaciones, Devoluciones, Historial, Productos frecuentes
Crédito: Solicitudes, Perfiles de crédito, Límites, Exposición, Cuentas por cobrar, Historial, Alertas
Segmentación: Segmentos, Etiquetas, Clasificaciones, Territorios, Carteras, Propietarios
Comunicaciones: Preferencias, Consentimientos, WhatsApp, Notificaciones, Plantillas relacionadas
Privacidad: Solicitudes, Retención, Anonimización, Exportaciones, Evidencias
Control: Calidad de datos, Duplicados, Importaciones, Auditoría, Configuración
```

Grupos: usan `route_id`; respetan permisos y feature flags; muestran badges; persisten estado; navegables por teclado; área táctil mínima 48px; se expanden en deep links; se ocultan sin páginas visibles. No usar `QListWidget` plano.

## 9. Rutas canónicas

```text
customers.overview | customers.directory | customers.create | customers.profile
customers.accounts | customers.contacts | customers.addresses | customers.tax_profiles
customers.duplicates

crm.leads | crm.lead_detail | crm.lead_qualification | crm.lead_conversion | crm.leads_discarded
crm.pipeline | crm.opportunities | crm.opportunity_detail | crm.forecast | crm.lost_opportunities
crm.activities | crm.calendar | crm.tasks | crm.calls | crm.meetings | crm.visits | crm.followups
crm.service_cases | crm.case_detail | crm.complaints | crm.requests | crm.incidents | crm.sla | crm.escalations

customers.purchase_history | customers.order_history | customers.quote_history
customers.return_history | customers.product_affinity

customers.credit_requests | customers.credit_profiles | customers.credit_exposure
customers.accounts_receivable | customers.credit_history | customers.credit_alerts

customers.segments | customers.tags | customers.territories | customers.portfolios | customers.ownership

customers.communication_preferences | customers.consents | customers.whatsapp_summary
customers.notification_history

customers.privacy_requests | customers.retention | customers.anonymization | customers.data_exports

customers.data_quality | customers.imports | customers.audit | customers.settings
```

No usar índices de pestaña como identidad de ruta.

## 10. Arquitectura de archivos

```text
frontend/desktop/modules/customers_crm/
  customers_crm_view.py | customers_crm_presenter.py | customers_crm_view_model.py | customers_crm_routes.py
  navigation/customers_crm_sidebar.py, customers_crm_navigation_model.py
  pages/{overview,customers,leads,opportunities,activities,service_cases,commercial_history,
         credit,segmentation,communications,privacy,data_quality,audit,settings}/
  dialogs/ | widgets/ | models/ | workers/

backend/domain/{customers,crm,customer_service,customer_credit,customer_privacy}/
  entities/ value_objects/ policies/ services/ repository_ports.py events.py enums.py exceptions.py

backend/application/{customers,crm,customer_service,customer_credit,customer_privacy}/
  commands/ queries/ dto/ use_cases/ authorization/ event_handlers/ notification_handlers/ outbox_handlers/

backend/infrastructure/db/schema/
backend/infrastructure/db/repositories/{customers,crm,customer_service,customer_credit,customer_privacy}/
```

## 11. UUIDv7

`from backend.shared.ids import new_uuid`. Todas las PK/FK de dominio nuevas (`customer_id`, `lead_id`, `opportunity_id`, `crm_activity_id`, `service_case_id`, `operation_id`, `event_id`, etc.) son UUIDv7 TEXT. Prohibido `INTEGER PRIMARY KEY`, `AUTOINCREMENT`, `lastrowid`, `MAX(id)+1`, `randomblob()`, `uuid4()`, `int(customer_id)`, `legacy_id`. Folios comerciales (`customer_number`, `lead_number`, `opportunity_number`, `case_number`) son campos separados, nunca la PK.

## 12. Customer Master

Entidad `Customer` con campos de identidad/ciclo de vida (`customer_number`, `customer_type`, `display_name`, `legal_name`, nombres, `status`, `lifecycle_stage`, `source`, `origin_branch_id`, `primary_contact_id`, direcciones default, `account_owner_user_id`, `territory_id`, timestamps, `operation_id`, `version`).

Tipos: `INDIVIDUAL, BUSINESS, PUBLIC_CUSTOMER, EMPLOYEE, INTERNAL, OTHER`.
Estados: `DRAFT, PROSPECT, ACTIVE, INACTIVE, SUSPENDED, BLOCKED, CLOSED, MERGED, ANONYMIZED`.
Etapas: `PROSPECT, LEAD, QUALIFIED, CUSTOMER, REPEAT_CUSTOMER, AT_RISK, INACTIVE, LOST`.

## 13. Cuentas y contactos CRM

`CustomerAccount` (cliente empresarial) y `CustomerContactPerson` (persona de contacto), con roles de decisión `DECISION_MAKER, INFLUENCER, BUYER, USER, FINANCE_CONTACT, DELIVERY_CONTACT, OTHER`. No confundir contacto de empresa con cliente persona física.

## 14. Teléfonos, correos y direcciones

Value objects `PhoneNumber` (E.164, +52, dedupe, verificación, flag WhatsApp), `EmailAddress` (normalizado, validado, dedupe, verificación, separación operacional/marketing), `PostalAddress` (tipos fiscal/facturación/entrega/comercial/personal; campos completos + lat/lng + `validation_status`). Clientes conserva direcciones; Delivery valida cobertura/tarifa.

## 15. Datos fiscales

`CustomerTaxProfile` (`tax_identifier`, `legal_name`, `tax_regime`, `fiscal_postal_code`, `default_cfdi_use`, `billing_email`, `validation_status`). Fiscal administra CFDI; Clientes administra datos maestros; Ventas conserva snapshots históricos.

## 16–18. Leads

`Lead`, `LeadQualification`, `LeadSource`. Estados: `NEW, ASSIGNED, CONTACTED, NURTURING, QUALIFIED, UNQUALIFIED, CONVERTED, LOST, ARCHIVED`. Fuentes: `WALK_IN, POS, WHATSAPP, PHONE, REFERRAL, SOCIAL_MEDIA, WEBSITE, CAMPAIGN, IMPORT, SALES_REP, OTHER`.

`QualifyLeadUseCase`/`DisqualifyLeadUseCase` — criterios configurables (necesidad, presupuesto, autoridad, tiempo, zona, tipo, volumen, productos, crédito, consentimiento), modelos `MANUAL, SCORE_BASED, BANT_LIKE, CUSTOM_RULE`, no hardcodear metodología, dejar evidencia.

`ConvertLeadUseCase` — puede crear `Customer`/`CustomerAccount`/`CustomerContactPerson`/`Opportunity`; evita duplicados; flujo: validar → buscar coincidencias → seleccionar/crear Customer → crear cuenta/contacto → oportunidad opcional → marcar `CONVERTED` → auditar. No elimina el lead original.

## 19–22. Oportunidades y pipeline

`Opportunity`, `OpportunityStage`, `OpportunityStageHistory`, `OpportunityProductInterest`. Estados: `OPEN, WON, LOST, CANCELLED, ON_HOLD`. Pipeline configurable vía `CRMStageDefinition`/`CRMStageTransitionPolicy` (nunca hardcodeado); cada transición valida permiso, campos obligatorios, actividad mínima, motivo, probabilidad, fecha esperada.

`crm.pipeline` ofrece Kanban + Tabla + Resumen. El Kanban no confirma etapa solo por arrastrar — invoca `MoveOpportunityStageUseCase`.

`SalesPipelineForecastQueryService` — pipeline total/ponderado, por etapa, cierres esperados, vencidas, sin seguimiento. CRM calcula forecast operativo; BI hace modelos analíticos avanzados; no mezclar con forecast de abastecimiento.

## 23–26. Actividades, agenda, recordatorios

`CRMActivity`, `CRMTask`, `CRMNote`, `CRMInteraction`. Tipos: `CALL, MEETING, VISIT, EMAIL, WHATSAPP, FOLLOW_UP, TASK, NOTE, QUOTE_REVIEW, PAYMENT_FOLLOW_UP, OTHER`. Estados: `PLANNED, IN_PROGRESS, COMPLETED, CANCELLED, OVERDUE`.

Use cases: `CreateCRMTaskUseCase, CompleteCRMTaskUseCase, RescheduleCRMTaskUseCase, AssignCRMTaskUseCase, CancelCRMTaskUseCase`. Vencida se muestra con estado+icono, no solo color.

`CRMReminder` — canales `IN_APP, EMAIL, WHATSAPP_INTERNAL, PUSH_FUTURE`; Notification Management decide envío, CRM solo define recordatorio/destinatario (nunca desde widgets).

## 27–29. Customer 360 / expediente / timeline

`Customer360QueryService` consolida (vía contratos de lectura, no joins directos): identidad, contactos, direcciones, propietario, segmentos, actividad CRM, oportunidades, ventas, pedidos, cotizaciones, devoluciones, CxC, crédito, Fidelidad, WhatsApp, Delivery, casos, consentimientos, alertas.

Expediente usa `PageHeader`, `CustomerSummaryHeader`, `ContextBar`, tabs internas (cada una con `route_id`), `ActionBar`, `PageState`. Tabs: Resumen, Identidad, Contactos, Direcciones, Actividad, Oportunidades, Comercial, Crédito, Atención, Consentimientos, Integraciones, Auditoría.

`CustomerHistoryQueryService` — mínimo: `get_purchase_history, get_payment_history, get_credit_history, get_quote_history, get_order_history, get_return_history, get_activity_timeline, get_opportunity_history, get_service_case_history`. Elimina SQL directo de `DialogoHistorialCliente`/`modulos/clientes.py`. Normaliza `id_cliente`→eliminar, `cliente_id`→`customer_id` (backend canónico), `metodo_pago`→eliminar, `forma_pago`→`payment_method` (backend canónico). No "resolver" agregando `import sqlite3`.

`CustomerActivityTimeline` — tipos de entrada: `CUSTOMER_CREATED/UPDATED, LEAD_CREATED/CONVERTED, OPPORTUNITY_CREATED/STAGE_CHANGED, ACTIVITY_COMPLETED, QUOTE_CREATED, ORDER_CREATED, SALE_COMPLETED, PAYMENT_RECEIVED, RETURN_COMPLETED, CREDIT_CHANGED, CONSENT_CHANGED, WHATSAPP_INTERACTION, SERVICE_CASE_CREATED/RESOLVED`. Cada entrada: `occurred_at, event_type, title, description, source_module, source_entity_id, branch, user, status`.

## 30–32. Casos de atención, SLA, escalamiento

`CustomerServiceCase`, `ServiceCaseActivity`, `ServiceCaseCategory`, `ServiceCaseResolution`. Tipos: `QUESTION, REQUEST, COMPLAINT, INCIDENT, RETURN_REQUEST, DELIVERY_ISSUE, PAYMENT_ISSUE, PRODUCT_QUALITY, CREDIT_ISSUE, OTHER`. Estados: `NEW, ASSIGNED, IN_PROGRESS, WAITING_CUSTOMER, WAITING_INTERNAL, ESCALATED, RESOLVED, CLOSED, CANCELLED`. Prioridades: `LOW, NORMAL, HIGH, URGENT, CRITICAL`.

`ServiceLevelPolicy`/`SLAInstance` — `first_response_due_at, resolution_due_at, first_response_at, resolved_at, breach_status, escalation_level`; estados `ON_TIME, AT_RISK, BREACHED, PAUSED, COMPLETED`. Configurable por tipo/prioridad/segmento/sucursal/canal, nunca hardcodeado.

`EscalateServiceCaseUseCase` — criterios: SLA vencido, cliente prioritario, caso crítico, reaperturas múltiples, impacto financiero, riesgo reputacional. Registra motivo/nivel/usuario/fecha/destinatario.

## 33–36. Propietario, territorios, carteras, segmentación, etiquetas

`CustomerOwnership` (tipos `PRIMARY, SECONDARY, ACCOUNT_MANAGER, CREDIT_MANAGER, SERVICE_OWNER`, con historial de asignación — no solo `vendedor_id` plano). `SalesTerritory`, `CustomerPortfolio`, `PortfolioAssignment`. `CustomerSegment`/`CustomerSegmentMembership` (`MANUAL, RULE_BASED, IMPORTED, ANALYTICS_GENERATED`; BI puede sugerir, CRM administra el uso operativo). `CustomerTag`/`CustomerTagAssignment` (no sustituyen estatus/segmento/riesgo/consentimiento/territorio).

## 37–40. Crédito del cliente y CxC

`CustomerCreditProfile` — `status, credit_limit, current_exposure, available_credit, payment_terms_days, risk_level, authorized_at/by, suspended_at, blocked_at, review_at, version`; todo importe `Decimal`. Estados: `NOT_CONFIGURED, PENDING_APPROVAL, UNDER_REVIEW, AUTHORIZED, SUSPENDED, BLOCKED, CLOSED`.

Workflow: `RequestCustomerCreditUseCase, ReviewCustomerCreditUseCase, ApproveCustomerCreditUseCase, RejectCustomerCreditUseCase, UpdateCustomerCreditLimitUseCase, SuspendCustomerCreditUseCase, BlockCustomerCreditUseCase, CloseCustomerCreditUseCase`. Nunca autorizar crédito directo desde POS.

Reglas de venta a crédito: cliente identificado, no público, perfil autorizado, límite > 0, crédito disponible, documentos vigentes, no bloqueado, sucursal permitida, permiso — sin fallback silencioso.

CxC: Finanzas es dueño de documentos/vencimientos/pagos/saldo/reversos; CRM solo muestra exposición/saldo/vencido/próximo vencimiento vía `CustomerAccountsReceivableSummaryQuery` — **no crear ledger financiero paralelo**.

## 41–44. Privacidad, preferencias, retención

`CustomerConsent` — tipos `PRIVACY_NOTICE, WHATSAPP, EMAIL, SMS, MARKETING, PROFILING, TERMS, DATA_SHARING`; estados `PENDING, GRANTED, WITHDRAWN, EXPIRED, NOT_REQUIRED`. No inferir consentimiento por tener teléfono/correo.

`CustomerCommunicationPreference` — canal, horario, idioma, transaccional/operativo/marketing/promociones/recordatorios; WhatsApp y Notification Management la consumen.

`CustomerPrivacyRequest` — tipos `ACCESS, RECTIFICATION, CANCELLATION, OPPOSITION, EXPORT, ANONYMIZATION, CONSENT_WITHDRAWAL`; estados `RECEIVED, VALIDATING, IN_PROGRESS, COMPLETED, REJECTED, CANCELLED`. Anonimización respeta obligaciones fiscales, ventas históricas, CxC, auditoría, prevención de fraude, retención legal.

`CustomerDataRetentionPolicy` — configurable por empresa/tipo de cliente/tipo de dato/estado/obligación legal; plazos nunca hardcodeados.

## 45–46. Duplicados, fusión, calidad de datos

`CustomerDuplicateCandidate`/`CustomerMergeRecord` — criterios: teléfono, correo, RFC, nombre normalizado, dirección, id externo, contacto empresarial. Estados: `DETECTED, UNDER_REVIEW, CONFIRMED_DUPLICATE, DISMISSED, MERGED`. Fusión: selecciona maestro, preserva referencias, resuelve contactos/direcciones/consentimientos/crédito/propietario, notifica bounded contexts, audita — nunca modifica tablas externas directamente.

`CustomerDataQualityIssue`/`CustomerDataQualityService` — reglas (nombre incompleto, teléfono/correo/RFC inválido, dirección incompleta, consentimiento faltante, duplicado probable, crédito inconsistente, lead sin seguimiento, oportunidad sin próxima actividad, caso sin propietario); estados `OPEN, ACKNOWLEDGED, CORRECTED, DISMISSED`.

## 47–48. Importación / exportación

`ImportCustomersUseCase`, `ImportLeadsUseCase`, `CustomerImportPreviewQuery` — CSV/XLSX vía infraestructura canónica; flujo archivo→mapeo→preview→validación→duplicados→confirmación→procesamiento→resultado; registra creados/actualizados/rechazados/duplicados/errores.

`ExportCustomersQuery`, `ExportCRMActivitiesQuery`, `ExportOpportunitiesQuery` — respetan permisos/filtros/columnas/datos sensibles/propietario/territorio/auditoría; no exportar IDs internos por defecto.

## 49–55. Integraciones

- **Ventas**: consume `CustomerLookupQueryService`, `CustomerCommercialEligibilityQuery`, `CustomerCreditEligibilityQuery`; CRM recibe `SALE_COMPLETED/CANCELLED/RETURNED` y puede actualizar proyecciones (`last_purchase_at`, `purchase_count`, `lifecycle_stage`). CRM no registra ventas.
- **Cotizaciones**: CRM administra la oportunidad, Quotes la cotización (`Opportunity → Quote`); `CreateQuoteFromOpportunityUseCase`. CRM no construye cotizaciones.
- **Pedidos/Delivery**: CRM muestra pedidos/entregas/incidencias; Orders/Delivery son la fuente; Clientes administra direcciones, Delivery administra zona/tarifa/ruta/repartidor/estado.
- **WhatsApp**: CRM muestra identidad vinculada, consentimiento, última conversación, conversaciones abiertas, handoff; WhatsApp conserva mensajes; una interacción puede generar `CRMInteraction`/`CRMTask`/`Lead`/`ServiceCase` vía handlers canónicos — no duplicar contenido completo de mensajes.
- **Fidelidad**: CRM muestra programa/nivel/puntos/tarjeta/recompensas resumidas vía `LoyaltyCustomerSummaryQuery`; acciones detalladas navegan a Fidelidad.
- **Finanzas**: CRM muestra saldo/vencido/exposición/estatus; Finanzas administra CxC/pagos/documentos/vencimientos/contabilidad; CRM no genera asientos.
- **BI**: CRM expone leads/conversiones/pipeline/actividad/oportunidades/casos/SLA/segmentos/retención/recencia/frecuencia/crédito/calidad; BI calcula CLV/churn/cohortes/propensión/forecast avanzado/ROI.

## 56. Automatizaciones

`CRMAutomationRule`/`CRMAutomationExecution` — triggers (`LEAD_CREATED`, `LEAD_IDLE`, `OPPORTUNITY_STAGE_CHANGED`, `OPPORTUNITY_IDLE`, `OPPORTUNITY_OVERDUE`, `CUSTOMER_INACTIVE`, `CASE_CREATED`, `SLA_AT_RISK`, `SLA_BREACHED`, `CREDIT_REVIEW_DUE`) → acciones (`CREATE_TASK`, `ASSIGN_OWNER`, `SEND_NOTIFICATION`, `CHANGE_PRIORITY`, `ESCALATE_CASE`, `ADD_TAG`, `ADD_TO_SEGMENT`). Reglas declarativas, no scripts arbitrarios.

## 57. Query Services (mínimo)

`CustomerDirectoryQueryService, CustomerProfileQueryService, Customer360QueryService, CustomerLookupQueryService, CustomerHistoryQueryService, CustomerCreditSummaryQueryService, CustomerConsentQueryService, CustomerAddressQueryService, CustomerDuplicateQueryService, CustomerDataQualityQueryService, CustomerDashboardQueryService, LeadDirectoryQueryService, LeadDetailQueryService, LeadPipelineQueryService, OpportunityDirectoryQueryService, OpportunityPipelineQueryService, OpportunityForecastQueryService, CRMActivityQueryService, CRMCalendarQueryService, CRMTaskQueryService, ServiceCaseDirectoryQueryService, ServiceCaseDetailQueryService, SLAQueryService, CustomerPortfolioQueryService, CustomerOwnershipQueryService, CustomerIntegrationSummaryQueryService`. La UI solo consume DTOs.

## 58. Use Cases (mínimo)

Ver lista completa en el prompt original; agrupados por: Clientes (crear/actualizar/activar/suspender/bloquear/cerrar, incl. alta rápida), Contactos y direcciones, Leads, Oportunidades, Actividades, Atención, Crédito, Privacidad, Calidad (dedupe/merge/import).

## 59–61. Roles, scopes, permisos generales

Roles son agrupaciones administrables, **nunca** `if role == "admin"`. Roles sugeridos: `CRM_VIEWER, CRM_AGENT, CRM_SALES_REPRESENTATIVE, CRM_SALES_SUPERVISOR, CRM_SALES_MANAGER, CRM_ACCOUNT_MANAGER, CRM_CUSTOMER_SERVICE_AGENT, CRM_CUSTOMER_SERVICE_SUPERVISOR, CRM_CREDIT_ANALYST, CRM_CREDIT_MANAGER, CRM_DATA_STEWARD, CRM_PRIVACY_OFFICER, CRM_MARKETING_OPERATOR, CRM_AUDITOR, CRM_ADMINISTRATOR`.

Scopes: `OWN, TEAM, BRANCH, TERRITORY, PORTFOLIO, COMPANY, ALL`, resueltos por `CustomerDataScopeResolver`/`CRMDataScopeResolver`.

Permisos de acceso general: `CUSTOMERS.CRM.ACCESS, CUSTOMERS.CRM.DASHBOARD.VIEW, CUSTOMERS.CRM.SEARCH, CUSTOMERS.CRM.GLOBAL.SEARCH, CUSTOMERS.CRM.AUDIT.VIEW, CUSTOMERS.CRM.SETTINGS.VIEW, CUSTOMERS.CRM.SETTINGS.MANAGE`.

## 62–71. Catálogo de permisos por dominio

Ver prompt original para el listado exhaustivo. Familias: `CUSTOMERS.*` (clientes, contactos, direcciones, fiscal, crédito, consentimiento, privacidad, calidad/duplicados/import/export), `CRM.*` (leads, oportunidades/pipeline/forecast, actividades/tareas/notas, casos/SLA, segmentos/tags/territorios/carteras/propietario).

Nota de compatibilidad: el catálogo canónico actual (`core/security/permission_catalog.py`) usa el formato `MODULO.accion` en minúscula con puntos (p.ej. `CAJA.turno.abrir`), no `MODULO.RECURSO.ACCION` en mayúsculas como en este prompt. CRM-2 debe decidir explícitamente si el catálogo CRM adopta el formato ya establecido en el resto del código (`CUSTOMERS.credito.aprobar`) o si se introduce un formato nuevo — no mezclar ambos.

## 72. Matriz de roles sugerida

Ver prompt original: CRM Viewer, Representante comercial, Supervisor comercial, Gerente comercial, Agente de atención, Supervisor de atención, Analista de crédito, Gerente de crédito, Data Steward, Responsable de privacidad, Auditor, Administrador CRM — con su alcance descrito.

## 73. Segregación de funciones

Quien solicita crédito no aprueba su propia solicitud; analista de crédito no necesariamente modifica el límite final; quien importa no aprueba importación sensible; quien propone fusión no la aprueba solo; quien anonimiza no borra auditoría; administrar permisos no da acceso automático a datos sensibles; configurar pipeline no autoriza marcar ganada sin permiso; quien crea un caso no borra su historial; reasignar cartera requiere motivo; exportar datos sensibles deja evidencia.

## 74. Autorización en caliente

`RequestCRMAuthorizationUseCase`/`ApproveCRMAuthorizationUseCase` para: aumento extraordinario de crédito, fusión de clientes, exportación sensible, anonimización, reasignación masiva, cambio forzado de etapa, cierre de caso crítico, reapertura protegida. Sin PIN local ni predefinido.

## 75. Enmascaramiento

Datos protegidos: teléfono, correo, RFC, CURP, dirección, saldo, límite de crédito, notas privadas, documentos, evidencia de consentimiento. Estados de visibilidad: `MASKED, PARTIALLY_VISIBLE, VISIBLE, RESTRICTED`. Nunca mostrar sensibles en tooltips/logs/errores/breadcrumbs/notificaciones genéricas.

## 76. Auditoría

Auditar creación, edición, consulta sensible, desenmascaramiento, exportación, activación/suspensión/bloqueo/cierre, contactos, direcciones, fiscal, lead, calificación, conversión, oportunidad, etapa, actividad, tarea, caso, SLA, escalamiento, crédito, consentimiento, preferencias, segmentación, territorio, propietario, duplicado, fusión, importación, privacidad, anonimización. Campos: `user_id, authorized_by, operation_id, entity_type, entity_id, customer_id, action, before, after, reason, branch_id, workstation_id, occurred_at, correlation_id`.

## 77. Eventos canónicos

Ver prompt original para el catálogo completo por dominio (Clientes, Leads, Oportunidades, Actividades, Atención, Crédito, Privacidad, Calidad). Todos post-commit.

## 78. Idempotencia

`UNIQUE(operation_id)` para impedir doble alta/lead/conversión/oportunidad/actividad/caso/consentimiento/autorización/fusión/importación.

## 79–90. UI/UX

Consumir solo `frontend/desktop/design_system/`, `frontend/desktop/components/`, `frontend/desktop/themes/`. Prohibido `modulos.ui_components`, `modulos.design_tokens`, `setStyleSheet` en páginas, hex locales, emojis, `QTableWidget`, `QGroupBox` estilizado, `QFrame` como card genérica.

Componentes canónicos: `PageHeader, ModuleSidebar, KPIBar, StandardCard, SummaryCard, ChartCard, FilterBar, StandardTable V2, StandardDialog, StatusBadge, SearchInput, PhoneInput, EmailInput, AddressInput, MoneyInput, DateInput, SelectInput, KeyboardAwareInput, LoadingState, EmptyState, ErrorState, PermissionDeniedState, NoResultsState, OfflineState`.

Estructura de página: `PageHeader → ContextBar? → Tabs? → KPIBar → FilterBar → contenido → PageState`.

Dashboard: máx. 6 KPIs principales (Leads nuevos, Leads por atender, Oportunidades abiertas, Pipeline ponderado, Actividades vencidas, Casos fuera de SLA) + secundarios. La UI no calcula KPIs.

Gráficas vía `ChartDTO`/`ChartBridge`/ECharts/`HtmlChartView` (ECharts empaquetado localmente).

Directorio de clientes, tabla de leads, tabla de oportunidades, bandeja de casos — columnas específicas listadas en el prompt original; SLA nunca depende solo del color.

Formularios organizados por secciones (ver detalle por entidad en el prompt original).

Touch: teclado virtual con icono en inputs compatibles; perfiles `compact/comfortable/touch`; targets 48–56px según elemento.

Responsive: validar en 1366×768, 1440×900, 1600×900, 1920×1080. Kanban con scroll horizontal + vista tabla alternativa.

Accesibilidad: `AccessibleName/Description`, foco visible, teclado, tooltips, atajos, contraste AA, targets táctiles; el color nunca es el único indicador.

## 91–92. Offline-first y conflictos

Disponible localmente: clientes permitidos, leads asignados, oportunidades asignadas, actividades, casos asignados, contactos, direcciones, configuración, permisos. Mutaciones offline llevan UUIDv7 + `operation_id` + outbox; estados `LOCAL_PENDING, SYNCING, SYNCED, CONFLICT, FAILED`.

`CustomerSyncConflict`/`CRMSyncConflict` — tipos: `CUSTOMER_UPDATED_REMOTELY, DUPLICATE_CREATED, CONTACT_CONFLICT, ADDRESS_CONFLICT, LEAD_ASSIGNMENT_CONFLICT, OPPORTUNITY_STAGE_CONFLICT, TASK_STATUS_CONFLICT, CASE_ASSIGNMENT_CONFLICT, CONSENT_CONFLICT, CREDIT_CONFLICT`. Nunca sobrescribir silenciosamente.

## 93. Excepciones de dominio

`CustomerNotFoundError, CustomerAlreadyExistsError, CustomerDuplicateDetectedError, CustomerStateInvalidError, CustomerBlockedError, LeadNotFoundError, LeadStateInvalidError, LeadAlreadyConvertedError, LeadQualificationFailedError, OpportunityNotFoundError, OpportunityStateInvalidError, OpportunityStageTransitionNotAllowedError, CRMActivityNotFoundError, CRMTaskNotFoundError, ServiceCaseNotFoundError, ServiceCaseStateInvalidError, SLABreachOverrideRequiredError, CustomerCreditNotAuthorizedError, CustomerCreditInsufficientError, CustomerConsentRequiredError, CustomerMergeNotAllowedError, CustomerPrivacyRequestInvalidError, CRMScopeDeniedError, DuplicateOperationError, PermissionDeniedError`. Prohibido `except Exception: pass`.

## 94. Eliminación de legacy (INCOMPLETA — mensaje del usuario cortado aquí)

Auditar y eliminar (lista tal como llegó, cortada a mitad de la última línea):
`modulos/clientes.py` monolítico, `DialogoHistorialCliente` con SQL, `sqlite3` en UI, `ClienteRepository` desde widgets, `container.db`, `self.conexion`, IDs enteros, `lastrowid`, `id_cliente`, `metodo_pago`, tabs por índices, `QTableWidget`, "QSS inli…" *(texto cortado — pedir confirmación/continuación al usuario si esta sección se vuelve relevante)*.

---

## 95–101 (referencia)

Entregadas en un mensaje anterior de esta conversación; ver `docs/architecture/CRM_0_CUSTOMER_MASTER_AUDIT.md` §13 y el listado de fases `CRM-0`..`CRM-23`, tests de seguridad (§96), tests funcionales (§97), guardrails de arquitectura (§98), Definición de Terminado (§99), Reporte Final (§100) y Regla Final (§101).
