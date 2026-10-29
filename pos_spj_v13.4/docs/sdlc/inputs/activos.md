PROMPT MAESTRO DEFINITIVO — REFACTOR ENTERPRISE DEL MÓDULO DE ACTIVOS / EAM SPJ ERP/POS/SAAS

Trabaja sobre el repositorio:

jarralfa-max/pos_spj_v13.4

Actúa como:

Arquitecto de Software Enterprise
Principal Engineer
Arquitecto DDD
Especialista en Enterprise Asset Management
Especialista en ERP
Auditor Financiero de Sistemas
Auditor de Seguridad
Auditor UI/UX
Auditor de Integridad de Datos

El objetivo es auditar, rediseñar, consolidar e implementar el bounded context empresarial canónico de:

Activos
Enterprise Asset Management
Fixed Asset Operations
Asset Lifecycle Management
Asset Registry
Asset Custody
Asset Assignment
Asset Location Management
Preventive Maintenance
Corrective Maintenance
Maintenance Work Orders
Asset Inspections
Asset Metering
Asset Warranty Management
Asset Insurance
Asset Documentation
Asset Transfers
Asset Capital Improvements
Asset Disposal
Asset Physical Inventory
Asset Tagging / QR
Asset Operational Cost
Asset Financial Projection

El módulo debe evolucionar del actual catálogo de equipos/mantenimientos hacia un EAM enterprise completo integrado al ERP, sin perder ninguna funcionalidad válida existente.

⸻

1. RESULTADO DE LA AUDITORÍA INICIAL

La implementación actual presenta como mínimo los siguientes problemas:

modulos/activos.py
    monolítico
    recibe AppContainer completo
    accede a container.db
    usa componentes UI legacy
    usa QTableWidget
    usa QTabWidget como navegación
    usa emojis como iconos
    usa QDoubleSpinBox para dinero
    mezcla presentación con coordinación de dominio
    genera PDF directamente
    maneja etiquetas directamente

Actualmente también existe:

core/services/asset_service.py

que mezcla:

CRUD
SQL
commit / rollback
mantenimiento
Tesorería
Finanzas
depreciación
capitalización
lecturas de UI

Esto viola separación de responsabilidades.

El servicio actual conecta directamente los costos de mantenimiento con Tesorería y puede registrar asientos financieros.

Esto debe eliminarse.

⸻

2. CONTRADICCIÓN ARQUITECTÓNICA A RESOLVER

Existe documentación/guardrails legacy que tratan Activos como parte del bounded context financiero.

La arquitectura nueva debe establecer definitivamente:

ACTIVOS
    dueño del activo físico y su ciclo operativo
FINANZAS
    dueño del reconocimiento financiero y contable

Por tanto:

Activos es dueño de

activo
clasificación
identificación
ubicación
custodia
responsable
condición física
mantenimiento
órdenes de trabajo
inspecciones
garantías
documentación
medidores
transferencias
inventario físico de activos
etiquetas
QR
baja operativa
evidencia de disposición
mejoras capitalizables propuestas

Finanzas es dueño de

valor contable
depreciación contable
depreciación acumulada financiera
asientos
CAPEX contable
OPEX contable
CxP
pagos
tesorería
conciliación
impairment financiero
ganancia/pérdida por disposición

Compras es dueño de

orden de compra
proveedor
recepción comercial
factura de proveedor

RRHH es dueño de

empleado

Inventario es dueño de

refacciones
consumibles
stock

No volver a mezclar estos dominios.

⸻

3. PRINCIPIO RECTOR

La arquitectura debe seguir:

AssetsView
    ↓
AssetsPresenter / ViewModel
    ↓
Application UseCases / QueryServices
    ↓
Assets Domain
    ↓
Repository Ports / Gateways
    ↓
Infrastructure

Integraciones:

Assets
    ↓ events/contracts
Finance
Purchases
HR
Inventory
Document Output
Notifications
BI

Regla:

Activos administra el activo.
Mantenimiento administra el trabajo operativo.
Finanzas contabiliza.
Compras adquiere.
Tesorería paga.
Inventario suministra refacciones.
Document Output imprime.
BI analiza.

⸻

4. REGLA DE PRESERVACIÓN FUNCIONAL

No perder ninguna función válida actual.

Antes de modificar código inventariar:

activos
categorías
número de serie
valor de adquisición
vida útil
depreciación configurada
ubicación
estado
notas
mantenimiento preventivo
mantenimiento correctivo
mantenimiento interno
mantenimiento externo
proveedor
técnico
fecha programada
fecha real
costo
pago
capitalización
depreciación acumulada
etiquetas
exportación PDF
bajas
ediciones
reportes

Clasificar:

PRESERVE
MOVE
REFACTOR
MERGE
REWRITE
DELETE_DUPLICATE
BLOCKED

Crear:

docs/refactor/assets_feature_inventory.md
docs/refactor/assets_legacy_inventory.md
docs/refactor/assets_business_logic_map.md
docs/refactor/assets_finance_boundary_map.md
docs/refactor/assets_ui_inventory.md
docs/refactor/assets_permission_inventory.md
docs/refactor/assets_legacy_removal_report.md

Tabla:

| Función actual | Archivo | Destino canónico | Acción | Evidencia |

⸻

5. CONTEXTO NO NEGOCIABLE

No conservar:

modulos/activos.py monolítico
AssetService monolítico
container
container.db
SQL en UI
repositories en UI
commit/rollback en UI
commit/rollback dispersos por services
QTableWidget
QTabWidget como navegación principal
QSS local
design_tokens legacy
ui_components legacy
emojis
PDF directo
pagos desde Activos
asientos desde Activos
cuentas contables en Activos
float monetario
IDs int
UUID4 persistente
hardcodes financieros
hardcodes de categorías
hardcodes de estados
lectura dual
escritura dual
legacy_id
fallbacks legacy

El resultado debe ser:

born-clean
born-UUIDv7
Decimal-only
domain-driven
event-driven
workflow-driven
permission-aware
scope-aware
multi-sucursal
multi-ubicación
multi-responsable
offline-aware
audit-ready
Design-System-only
sin legacy

⸻

6. SKILLS OBLIGATORIOS

Leer:

docs/skills/SPJ_REFACTOR_SKILL.md
docs/skills/SPJ_UI_UX_ARCHITECTURE_SKILL.md
docs/skills/SPJ_BUGFIX_AUDIT_CORRECTION_SKILL.md

y todos los Skills aplicables.

Prioridad:

SPJ_REFACTOR_SKILL
SPJ_UI_UX_ARCHITECTURE_SKILL
SPJ_BUGFIX_AUDIT_CORRECTION_SKILL
skills específicos

⸻

7. MÓDULO GLOBAL

Activos debe permanecer como bounded context global independiente:

Inicio
Punto de Venta
Pedidos y Delivery
Clientes / CRM
Fidelidad
WhatsApp
Productos
Inventario
Transferencias
Compras
Procesamiento Cárnico
Mermas
Caja
Finanzas
RRHH
Activos
Inteligencia y Reportes
Configuración

No integrar Activos dentro de Finanzas.

⸻

8. NAVEGACIÓN INTERNA DE ACTIVOS

Usar ModuleSidebar.

Estructura:

Resumen
Activos
    Directorio
    Alta de activo
    Categorías
    Ubicaciones
    Responsables
    Custodia
    Etiquetas y QR
Mantenimiento
    Resumen
    Plan preventivo
    Órdenes de trabajo
    Agenda
    Correctivos
    Inspecciones
    Mantenimientos vencidos
    Historial
Costos y vida útil
    Costos operativos
    Mejoras
    Capitalizaciones propuestas
    Depreciación operativa
    Valor proyectado
Movimientos
    Asignaciones
    Transferencias
    Cambios de ubicación
    Préstamos
    Devoluciones
Control físico
    Inventario físico
    Conteos
    Activos no encontrados
    Diferencias
    Conciliación física
Documentación
    Facturas
    Garantías
    Manuales
    Fotografías
    Certificados
    Seguros
Bajas
    Solicitudes
    Aprobaciones
    Venta
    Donación
    Desecho
    Pérdida / robo
    Historial
Control
    Alertas
    Indicadores
    Auditoría
    Configuración

⸻

9. RUTAS CANÓNICAS

Crear:

assets.overview
assets.directory
assets.create
assets.detail
assets.categories
assets.locations
assets.custody
assets.assignments
assets.tags
assets.maintenance.overview
assets.maintenance.plan
assets.maintenance.work_orders
assets.maintenance.calendar
assets.maintenance.corrective
assets.maintenance.inspections
assets.maintenance.overdue
assets.maintenance.history
assets.costs
assets.improvements
assets.capitalization_proposals
assets.depreciation_projection
assets.movements
assets.transfers
assets.loans
assets.physical_inventory
assets.physical_counts
assets.missing
assets.documents
assets.warranties
assets.insurance
assets.disposals
assets.disposal_requests
assets.disposal_history
assets.alerts
assets.audit
assets.settings

No usar índices de tabs.

⸻

10. ARQUITECTURA DE ARCHIVOS

Frontend

frontend/
└── desktop/
    └── modules/
        └── assets/
            ├── assets_view.py
            ├── assets_presenter.py
            ├── assets_view_model.py
            ├── assets_routes.py
            │
            ├── navigation/
            │   └── assets_sidebar.py
            │
            ├── pages/
            │   ├── overview/
            │   ├── registry/
            │   ├── maintenance/
            │   ├── costs/
            │   ├── movements/
            │   ├── physical_inventory/
            │   ├── documents/
            │   ├── disposals/
            │   ├── audit/
            │   └── settings/
            │
            ├── dialogs/
            ├── widgets/
            └── models/

Domain

backend/
└── domain/
    └── assets/
        ├── entities/
        ├── value_objects/
        ├── policies/
        ├── services/
        ├── repository_ports.py
        ├── events.py
        ├── enums.py
        └── exceptions.py

Application

backend/
└── application/
    └── assets/
        ├── commands/
        ├── queries/
        ├── dto/
        ├── use_cases/
        ├── authorization/
        ├── event_handlers/
        ├── notification_handlers/
        └── outbox_handlers/

Infrastructure

backend/
└── infrastructure/
    └── assets/
        ├── repositories/
        ├── document_storage/
        ├── qr/
        └── integrations/

⸻

11. ASSET AGGREGATE

Crear:

Asset

Campos:

id
asset_number
asset_tag
name
description
asset_type_id
category_id
manufacturer
model
serial_number
acquisition_date
commissioned_at
origin_branch_id
current_branch_id
current_location_id
custodian_user_id
responsible_employee_id
supplier_id
purchase_reference_id
status
condition
criticality
ownership_type
warranty_status
expected_useful_life
operational_start_date
notes
created_at
updated_at
created_by_user_id
operation_id
version

⸻

12. UUIDV7

Todas las identidades:

asset_id
asset_category_id
asset_location_id
asset_assignment_id
asset_transfer_id
asset_document_id
asset_warranty_id
asset_insurance_id
maintenance_plan_id
maintenance_work_order_id
maintenance_task_id
maintenance_execution_id
inspection_id
meter_id
meter_reading_id
asset_improvement_id
capitalization_proposal_id
physical_inventory_id
physical_count_line_id
asset_disposal_request_id
asset_disposal_id
asset_tag_id
operation_id
event_id

deben usar UUIDv7.

Prohibido:

INTEGER PRIMARY KEY
AUTOINCREMENT
lastrowid
MAX(id)+1
uuid4()
int(asset_id)
legacy_id

⸻

13. FOLIO DEL ACTIVO

El UUID interno no debe mostrarse como código comercial.

Crear:

asset_number

Ejemplo:

ACT-000001
ACT-QRO-000234
ACT-SBP-000081

El formato debe ser configurable.

No utilizar:

ACT-{uuid[:8]}

como solución definitiva.

UUID es identidad técnica.

Folio es identidad operativa.

⸻

14. ASSET TAG / QR

Crear:

AssetTag

Campos:

id
asset_id
tag_number
qr_public_token
barcode_value
status
issued_at
printed_at
replaced_at

El QR no debe exponer directamente el UUID interno.

Usar token público seguro.

Debe permitir:

QR
Code128
DataMatrix futuro

⸻

15. TIPOS DE ACTIVOS

Crear catálogo:

AssetType
AssetCategory

No hardcodear:

Equipo de Computo
Mobiliario
Vehículos
Maquinaria
Cámara Frigorífica
Báscula
Otros

Estas categorías iniciales pueden existir como seed configurable, pero no en la UI.

Ejemplos:

Tecnología
Mobiliario
Vehículos
Maquinaria
Refrigeración
Básculas
Infraestructura
Herramientas
Seguridad
Otros

⸻

16. ESTADOS DEL ACTIVO

Crear:

AssetStatus
AssetCondition

Estados sugeridos:

DRAFT
AVAILABLE
ASSIGNED
IN_USE
IN_MAINTENANCE
OUT_OF_SERVICE
LOANED
MISSING
DISPOSAL_PENDING
DISPOSED
SOLD
DONATED
STOLEN
LOST

Condición:

NEW
GOOD
FAIR
POOR
DAMAGED
UNUSABLE

No usar strings libres.

⸻

17. CRITICIDAD

Crear:

AssetCriticality

Valores:

LOW
MEDIUM
HIGH
CRITICAL

La criticidad debe impactar:

frecuencia mantenimiento
SLA mantenimiento
alertas
prioridad de work orders
inspecciones

⸻

18. UBICACIONES

Crear:

AssetLocation

Debe soportar jerarquía:

Empresa
└── Sucursal
    └── Área
        └── Cuarto
            └── Posición

Campos:

id
branch_id
parent_location_id
code
name
location_type
status

No guardar únicamente:

ubicacion = "Bodega"

como texto libre.

⸻

19. CUSTODIA Y RESPONSABILIDAD

Crear:

AssetAssignment

Campos:

asset_id
employee_id
user_id
branch_id
location_id
assignment_type
assigned_at
returned_at
assigned_by
condition_at_assignment
condition_at_return
notes

Tipos:

CUSTODY
OPERATION
TEMPORARY_LOAN
SHARED
VEHICLE_ASSIGNMENT

Debe existir historial completo.

No sobrescribir al responsable anterior.

⸻

20. TRANSFERENCIAS DE ACTIVOS

Crear:

AssetTransfer

Estados:

REQUESTED
APPROVED
PREPARED
IN_TRANSIT
RECEIVED
REJECTED
CANCELLED

Debe registrar:

source_branch
destination_branch
source_location
destination_location
requested_by
approved_by
shipped_by
received_by
condition_out
condition_in

No cambiar sucursal mediante simple UPDATE.

⸻

21. PRÉSTAMOS

Crear:

AssetLoan

Para activos temporalmente prestados.

Campos:

asset_id
borrower
checkout_at
expected_return_at
returned_at
condition_out
condition_in
authorized_by

⸻

22. MANTENIMIENTO

Separar:

MaintenancePlan
MaintenanceWorkOrder
MaintenanceExecution
MaintenanceTask
MaintenanceResource

El actual registro mantenimientos no es suficiente como modelo enterprise.

⸻

23. PLAN PREVENTIVO

Crear:

MaintenancePlan

Campos:

asset_id
maintenance_type
frequency_type
frequency_value
meter_trigger
calendar_trigger
next_due_at
priority
estimated_duration
estimated_cost
assigned_team
external_provider_id
instructions
status

Frecuencias:

DAILY
WEEKLY
MONTHLY
QUARTERLY
SEMIANNUAL
ANNUAL
METER_BASED
CUSTOM

No hardcodear.

⸻

24. ÓRDENES DE TRABAJO

Crear:

MaintenanceWorkOrder

Campos:

id
work_order_number
asset_id
maintenance_plan_id
maintenance_type
priority
status
description
reported_issue
scheduled_at
started_at
completed_at
assigned_employee_id
external_supplier_id
estimated_cost
actual_cost
downtime_minutes
resolution
root_cause
created_by_user_id
approved_by_user_id
operation_id
version

⸻

25. ESTADOS DE WORK ORDER

DRAFT
REQUESTED
APPROVED
SCHEDULED
ASSIGNED
IN_PROGRESS
PAUSED
WAITING_PARTS
WAITING_PROVIDER
COMPLETED
CLOSED
CANCELLED

No usar solo:

pendiente
completado

⸻

26. MANTENIMIENTO PREVENTIVO Y CORRECTIVO

Tipos:

PREVENTIVE
CORRECTIVE
PREDICTIVE_FUTURE
INSPECTION
CALIBRATION
SAFETY
WARRANTY
EMERGENCY

Conservar preventivo y correctivo actuales.

Ampliar sin romperlos.

⸻

27. SERVICIO INTERNO / EXTERNO

El flujo actual debe preservarse pero normalizarse.

Crear:

MaintenanceProviderType

Valores:

INTERNAL
EXTERNAL
WARRANTY_PROVIDER

Servicio interno referencia:

employee_id

Servicio externo referencia:

supplier_id

No guardar:

"Proveedor: Taller X"

como único dato.

⸻

28. PROVEEDORES

Activos no administra proveedores.

Consumir:

SupplierLookupQueryService

Compras administra proveedor maestro.

⸻

29. COSTOS DE MANTENIMIENTO

Activos registra la evidencia operativa:

estimated_cost
actual_cost
labor_cost
parts_cost
external_service_cost

Pero no registra pago.

Flujo correcto:

MaintenanceWorkOrder COMPLETED
    ↓
MaintenanceCostConfirmed
    ↓
Finance/Purchases decide tratamiento
    ↓
OPEX / CAPEX
    ↓
CxP / Treasury

Eliminar:

completar_y_pagar_mantenimiento()

como operación combinada.

⸻

30. OPEX Y CAPEX

Activos puede clasificar o proponer:

MAINTENANCE_EXPENSE
CAPITAL_IMPROVEMENT_CANDIDATE

Finanzas determina tratamiento contable final.

Crear:

AssetCapitalizationProposal

Estados:

DRAFT
SUBMITTED
UNDER_REVIEW
APPROVED
REJECTED
POSTED

⸻

31. CAPITALIZACIÓN

Eliminar lógica como:

UPDATE activos
SET valor_adquisicion = valor_adquisicion + mantenimiento

desde AssetService.

Flujo correcto:

Asset improvement
    ↓
CapitalizationProposal
    ↓
Finance approval
    ↓
Financial asset value update
    ↓
event
    ↓
Assets projection update

No cambiar valor contable directamente desde mantenimiento.

⸻

32. COSTO DEL ACTIVO

Separar:

acquisition_cost_reference
operational_cost_summary
financial_book_value_projection

Activos puede mostrar información financiera de solo lectura.

La fuente contable es Finanzas.

⸻

33. DEPRECIACIÓN

El cálculo contable no pertenece a Activos.

Eliminar de Activos:

registrar_asiento()
cuentas 6105
cuentas 1302

Crear contrato:

AssetFinancialProjectionQueryService

Finanzas es dueño de:

depreciation method
depreciable basis
salvage value
useful life accounting
period depreciation
accumulated depreciation
book value

⸻

34. PROYECCIÓN DE DEPRECIACIÓN

Activos puede mostrar:

costo original
depreciación acumulada
valor en libros
depreciación mensual
vida remanente

como proyección proveniente de Finanzas.

No recalcular con:

valor / vida / 12

dentro de la UI o AssetService.

⸻

35. MÉTODOS DE DEPRECIACIÓN

Finanzas puede soportar:

STRAIGHT_LINE
DECLINING_BALANCE
UNITS_OF_PRODUCTION
CUSTOM

Activos solo muestra el método asignado.

⸻

36. MEJORAS DEL ACTIVO

Crear:

AssetImprovement

Campos:

asset_id
description
completed_at
operational_effect
useful_life_extension
capacity_change
cost_reference
capitalization_proposal_id

⸻

37. INSPECCIONES

Crear:

AssetInspection
InspectionChecklist
InspectionResult

Tipos:

SAFETY
OPERATIONAL
QUALITY
PREVENTIVE
CALIBRATION
REGULATORY

Resultados:

PASS
PASS_WITH_OBSERVATIONS
FAIL
OUT_OF_SERVICE

⸻

38. CHECKLISTS

Los checklists deben ser configurables.

No hardcodear preguntas.

Crear:

InspectionChecklistTemplate
InspectionChecklistItem

Tipos de respuesta:

BOOLEAN
TEXT
NUMBER
PHOTO
SIGNATURE
CHOICE

⸻

39. MEDIDORES

Crear:

AssetMeter
AssetMeterReading

Tipos:

HOURS
KILOMETERS
CYCLES
ENERGY
CUSTOM

Aplicable a:

vehículos
maquinaria
compresores
equipos de refrigeración

Puede disparar mantenimiento preventivo.

⸻

40. GARANTÍAS

Crear:

AssetWarranty

Campos:

asset_id
provider_id
warranty_type
starts_at
expires_at
coverage
document_id
status

Estados:

ACTIVE
EXPIRING
EXPIRED
VOID

Alertar antes de vencimiento.

⸻

41. SEGUROS

Crear:

AssetInsurancePolicy

Campos:

asset_id
provider
policy_number
coverage
insured_value
starts_at
expires_at
document_reference
status

No gestionar póliza contablemente.

⸻

42. DOCUMENTOS

Crear:

AssetDocument

Tipos:

INVOICE
MANUAL
WARRANTY
INSURANCE
PHOTO
CERTIFICATE
SERVICE_REPORT
REGISTRATION
OWNERSHIP
OTHER

No guardar rutas arbitrarias sin abstraction.

Usar:

DocumentStorageGateway

⸻

43. FOTOGRAFÍAS

Permitir:

foto principal
evidencia de condición
evidencia mantenimiento
evidencia baja

Cada archivo debe:

validar MIME
validar tamaño
calcular hash
tener metadata

⸻

44. INVENTARIO FÍSICO DE ACTIVOS

Crear:

AssetPhysicalInventory
AssetPhysicalInventoryLine

Estados:

DRAFT
IN_PROGRESS
REVIEW
COMPLETED
CANCELLED

Debe permitir escaneo:

QR
barcode

Resultados:

FOUND
MISSING
WRONG_LOCATION
WRONG_CUSTODIAN
DAMAGED
UNREGISTERED

⸻

45. DIFERENCIAS

No corregir automáticamente.

Crear:

AssetPhysicalDiscrepancy

Workflow:

Detectada
    ↓
Revisión
    ↓
Investigación
    ↓
Resolución
    ↓
Aprobación cuando aplique

⸻

46. BAJA DE ACTIVOS

Crear:

AssetDisposalRequest
AssetDisposal

Motivos:

SALE
DONATION
SCRAP
LOSS
THEFT
OBSOLESCENCE
DAMAGE
REPLACEMENT
OTHER

Estados:

REQUESTED
UNDER_REVIEW
APPROVED
REJECTED
IN_PROGRESS
COMPLETED
CANCELLED

No cambiar directamente:

estado = baja

sin workflow.

⸻

47. VENTA DE ACTIVO

Assets documenta la disposición física.

Finance administra:

valor contable
resultado por venta
asiento

Sales/POS no debe usarse necesariamente para vender activos fijos salvo diseño explícito.

⸻

48. PÉRDIDA / ROBO

Requerir:

motivo
fecha
responsable de reporte
última ubicación
último custodio
evidencia
autorización

Generar alerta de auditoría.

⸻

49. ETIQUETAS

Conservar capacidad actual de etiquetado.

Pero usar:

AssetTagRenderDataDTO
    ↓
Document Output
    ↓
PrintJob

No imprimir desde módulo.

⸻

50. FORMATO DE ETIQUETA

Configurable:

logo
asset_number
nombre
sucursal
ubicación
QR
barcode
serial opcional

No exponer UUID técnico.

⸻

51. EXPORTACIÓN PDF

Conservar la función de reporte.

Pero mover a:

AssetReportQuery
    ↓
Document Output
    ↓
PDFRenderer

Eliminar:

FPDF

de la UI.

⸻

52. INTEGRACIÓN CON COMPRAS

Flujo:

Purchase received
    ↓
item classified as capital asset
    ↓
ASSET_REGISTRATION_REQUESTED
    ↓
Assets creates draft asset
    ↓
user completes asset metadata

No crear activo simplemente por cada compra.

Debe existir policy.

⸻

53. INTEGRACIÓN CON FINANZAS

Events:

ASSET_REGISTERED
ASSET_COMMISSIONED
ASSET_IMPROVEMENT_COMPLETED
ASSET_CAPITALIZATION_PROPOSED
ASSET_DISPOSAL_APPROVED
ASSET_DISPOSED
MAINTENANCE_COST_CONFIRMED

Finanzas decide:

asset recognition
CAPEX
OPEX
depreciation
impairment
disposal gain/loss
journal entries

⸻

54. INTEGRACIÓN CON TESORERÍA

Activos nunca debe llamar:

registrar_gasto_opex()

directamente.

La cadena debe ser:

WorkOrder
    ↓
Supplier invoice / Expense request
    ↓
Finance / Accounts Payable
    ↓
Treasury

⸻

55. INTEGRACIÓN CON INVENTARIO

Las refacciones usadas en mantenimiento:

MaintenanceWorkOrder
    ↓
PartsRequest
    ↓
Inventory
    ↓
reservation
    ↓
consumption

Activos no disminuye stock.

⸻

56. INTEGRACIÓN CON RRHH

Para:

custodios
responsables
técnicos
conductores

consumir:

EmployeeLookupQueryService

No duplicar empleados.

⸻

57. INTEGRACIÓN CON CONFIGURACIÓN

Device Management administra dispositivos físicos.

No confundir:

activo fijo "báscula"

con:

configuración técnica del driver de báscula

Asset puede referenciar:

device_registration_id

pero no gestionar puerto COM.

⸻

58. INTEGRACIÓN CON BI

Exponer:

activos por categoría
activos por sucursal
activos por condición
valor de adquisición
valor libro proyectado
mantenimiento preventivo
mantenimiento correctivo
downtime
costo mantenimiento
MTBF
MTTR
edad de activos
activos próximos a reemplazo
garantías por vencer

BI realiza análisis avanzado.

⸻

59. MTBF / MTTR

Crear QueryServices para:

Mean Time Between Failures
Mean Time To Repair

No calcular en UI.

⸻

60. ASSET HEALTH SCORE

Puede existir:

AssetHealthScore

basado en:

edad
fallas
mantenimiento vencido
condición
downtime
inspecciones

Debe ser explicable.

No usar ML opaco inicialmente.

⸻

61. CAPEX / REEMPLAZO

Crear proyección:

AssetReplacementCandidate

Basada en:

edad
vida útil
costo mantenimiento
downtime
criticidad
valor libro
condición

Activos propone.

Finanzas aprueba inversión.

⸻

62. CONFIGURACIÓN

Secciones:

General
Tipos
Categorías
Estados
Condiciones
Criticidad
Ubicaciones
Numeración
Etiquetas
QR
Mantenimiento
Prioridades
SLA
Inspecciones
Garantías
Seguros
Bajas
Integraciones
Permisos
Auditoría

Toda configuración:

scope-aware
versioned
effective-dated cuando aplique
audited

⸻

63. QUERY SERVICES

Crear como mínimo:

AssetDirectoryQueryService
AssetDetailQueryService
AssetDashboardQueryService
AssetLocationQueryService
AssetAssignmentQueryService
AssetMaintenanceQueryService
MaintenanceWorkOrderQueryService
MaintenanceCalendarQueryService
AssetInspectionQueryService
AssetCostSummaryQueryService
AssetFinancialProjectionQueryService
AssetWarrantyQueryService
AssetDocumentQueryService
AssetPhysicalInventoryQueryService
AssetDisposalQueryService
AssetAuditQueryService
AssetLookupQueryService

UI solo consume DTOs.

⸻

64. USE CASES — ACTIVOS

CreateAssetUseCase
UpdateAssetUseCase
CommissionAssetUseCase
SuspendAssetUseCase
ReactivateAssetUseCase
ChangeAssetConditionUseCase

⸻

65. USE CASES — ASIGNACIÓN

AssignAssetUseCase
ReturnAssetUseCase
TransferAssetUseCase
ReceiveTransferredAssetUseCase
LoanAssetUseCase
ReturnLoanedAssetUseCase

⸻

66. USE CASES — MANTENIMIENTO

CreateMaintenancePlanUseCase
UpdateMaintenancePlanUseCase
GenerateMaintenanceWorkOrderUseCase
CreateCorrectiveWorkOrderUseCase
ApproveMaintenanceWorkOrderUseCase
AssignMaintenanceWorkOrderUseCase
StartMaintenanceWorkOrderUseCase
PauseMaintenanceWorkOrderUseCase
CompleteMaintenanceWorkOrderUseCase
CloseMaintenanceWorkOrderUseCase
CancelMaintenanceWorkOrderUseCase

⸻

67. USE CASES — INSPECCIÓN

CreateInspectionUseCase
RecordInspectionResultUseCase
FailInspectionUseCase
CreateWorkOrderFromInspectionUseCase

⸻

68. USE CASES — CAPITALIZACIÓN

CreateAssetImprovementUseCase
SubmitCapitalizationProposalUseCase
CancelCapitalizationProposalUseCase

Finanzas posee:

ApproveCapitalizationUseCase
PostCapitalizationUseCase

⸻

69. USE CASES — INVENTARIO FÍSICO

StartAssetPhysicalInventoryUseCase
ScanAssetUseCase
RecordAssetDiscrepancyUseCase
CompleteAssetPhysicalInventoryUseCase
ResolveAssetDiscrepancyUseCase

⸻

70. USE CASES — BAJA

RequestAssetDisposalUseCase
ReviewAssetDisposalUseCase
ApproveAssetDisposalUseCase
RejectAssetDisposalUseCase
ExecuteAssetDisposalUseCase
CancelAssetDisposalUseCase

⸻

71. PERMISOS — ACCESO GENERAL

ASSETS_ACCESS
ASSETS_DASHBOARD_VIEW
ASSETS_SEARCH
ASSETS_GLOBAL_SEARCH
ASSETS_AUDIT_VIEW
ASSETS_SETTINGS_VIEW
ASSETS_SETTINGS_MANAGE

⸻

72. PERMISOS — ACTIVOS

ASSETS_VIEW
ASSETS_VIEW_OWN
ASSETS_VIEW_BRANCH
ASSETS_VIEW_COMPANY
ASSETS_CREATE
ASSETS_EDIT
ASSETS_EDIT_SENSITIVE
ASSETS_COMMISSION
ASSETS_SUSPEND
ASSETS_REACTIVATE
ASSETS_CHANGE_CONDITION

⸻

73. PERMISOS — CUSTODIA

ASSETS_ASSIGN_VIEW
ASSETS_ASSIGN
ASSETS_REASSIGN
ASSETS_RETURN
ASSETS_LOAN
ASSETS_LOAN_RETURN
ASSETS_CUSTODY_HISTORY_VIEW

⸻

74. PERMISOS — TRANSFERENCIAS

ASSETS_TRANSFER_VIEW
ASSETS_TRANSFER_REQUEST
ASSETS_TRANSFER_APPROVE
ASSETS_TRANSFER_PREPARE
ASSETS_TRANSFER_SHIP
ASSETS_TRANSFER_RECEIVE
ASSETS_TRANSFER_REJECT
ASSETS_TRANSFER_CANCEL

⸻

75. PERMISOS — MANTENIMIENTO

ASSETS_MAINTENANCE_VIEW
ASSETS_MAINTENANCE_PLAN_VIEW
ASSETS_MAINTENANCE_PLAN_CREATE
ASSETS_MAINTENANCE_PLAN_EDIT
ASSETS_WORK_ORDER_VIEW
ASSETS_WORK_ORDER_CREATE
ASSETS_WORK_ORDER_APPROVE
ASSETS_WORK_ORDER_ASSIGN
ASSETS_WORK_ORDER_START
ASSETS_WORK_ORDER_PAUSE
ASSETS_WORK_ORDER_COMPLETE
ASSETS_WORK_ORDER_CLOSE
ASSETS_WORK_ORDER_CANCEL
ASSETS_MAINTENANCE_COST_VIEW
ASSETS_MAINTENANCE_COST_EDIT

⸻

76. PERMISOS — INSPECCIÓN

ASSETS_INSPECTION_VIEW
ASSETS_INSPECTION_CREATE
ASSETS_INSPECTION_EXECUTE
ASSETS_INSPECTION_APPROVE
ASSETS_INSPECTION_OVERRIDE

⸻

77. PERMISOS — COSTOS / FINANZAS

ASSETS_COST_VIEW
ASSETS_FINANCIAL_PROJECTION_VIEW
ASSETS_CAPITALIZATION_PROPOSAL_VIEW
ASSETS_CAPITALIZATION_PROPOSAL_CREATE
ASSETS_CAPITALIZATION_PROPOSAL_SUBMIT
ASSETS_CAPITALIZATION_PROPOSAL_CANCEL

No otorgar a Activos permisos para:

FINANCE_JOURNAL_POST
TREASURY_PAYMENT_EXECUTE

automáticamente.

⸻

78. PERMISOS — INVENTARIO FÍSICO

ASSETS_PHYSICAL_INVENTORY_VIEW
ASSETS_PHYSICAL_INVENTORY_CREATE
ASSETS_PHYSICAL_INVENTORY_COUNT
ASSETS_PHYSICAL_INVENTORY_COMPLETE
ASSETS_DISCREPANCY_VIEW
ASSETS_DISCREPANCY_RESOLVE

⸻

79. PERMISOS — DOCUMENTACIÓN

ASSETS_DOCUMENT_VIEW
ASSETS_DOCUMENT_UPLOAD
ASSETS_DOCUMENT_DOWNLOAD
ASSETS_DOCUMENT_DELETE
ASSETS_WARRANTY_VIEW
ASSETS_WARRANTY_MANAGE
ASSETS_INSURANCE_VIEW
ASSETS_INSURANCE_MANAGE

⸻

80. PERMISOS — BAJAS

ASSETS_DISPOSAL_VIEW
ASSETS_DISPOSAL_REQUEST
ASSETS_DISPOSAL_REVIEW
ASSETS_DISPOSAL_APPROVE
ASSETS_DISPOSAL_REJECT
ASSETS_DISPOSAL_EXECUTE
ASSETS_DISPOSAL_CANCEL

⸻

81. PERMISOS — ETIQUETAS

ASSETS_TAG_VIEW
ASSETS_TAG_CREATE
ASSETS_TAG_PRINT
ASSETS_TAG_REPRINT
ASSETS_TAG_REPLACE

⸻

82. ROLES SUGERIDOS

Los roles agrupan permisos.

No autorizar por nombre.

Roles sugeridos:

ASSET_VIEWER
ASSET_OPERATOR
ASSET_CUSTODIAN
ASSET_TECHNICIAN
ASSET_MAINTENANCE_SUPERVISOR
ASSET_MANAGER
ASSET_PHYSICAL_AUDITOR
ASSET_DISPOSAL_APPROVER
ASSET_DATA_STEWARD
ASSET_AUDITOR
ASSET_ADMINISTRATOR

⸻

83. SCOPES

Soportar:

OWN
ASSIGNED
BRANCH
REGION
COMPANY
ALL

Ejemplos:

custodio:
    activos asignados
técnico:
    work orders asignadas
gerente sucursal:
    activos de sucursal
asset manager:
    empresa
auditor:
    lectura global autorizada

Crear:

AssetDataScopeResolver

⸻

84. SEGREGACIÓN DE FUNCIONES

Reglas:

quien solicita baja no debe aprobarla solo
quien ejecuta inventario físico no necesariamente resuelve sus propias diferencias
quien solicita transferencia no confirma recepción
quien ejecuta mantenimiento no aprueba capitalización
quien crea propuesta CAPEX no contabiliza
quien carga documento no puede alterar auditoría
quien administra permisos no obtiene datos financieros automáticamente

⸻

85. AUTORIZACIÓN EN CALIENTE

Crear:

RequestAssetAuthorizationUseCase
ApproveAssetAuthorizationUseCase

Aplicar a:

baja
pérdida
robo
capitalización sensible
cambio extraordinario de ubicación
override de inspección
cierre de work order crítico
reimpresión controlada de etiqueta

No PIN local.

⸻

86. AUDITORÍA

Auditar:

alta
edición
activación
asignación
custodia
devolución
transferencia
recepción
mantenimiento
inspección
costo
documentos
garantía
seguro
inventario físico
diferencias
capitalización propuesta
baja
venta
donación
pérdida
robo
etiqueta
reimpresión

Guardar:

user_id
authorized_by
operation_id
asset_id
entity_type
entity_id
action
before
after
reason
branch_id
location_id
workstation_id
occurred_at
correlation_id

⸻

87. EVENTOS CANÓNICOS

Activos

ASSET_CREATED
ASSET_UPDATED
ASSET_COMMISSIONED
ASSET_STATUS_CHANGED
ASSET_CONDITION_CHANGED

Custodia

ASSET_ASSIGNED
ASSET_RETURNED
ASSET_CUSTODIAN_CHANGED
ASSET_LOCATION_CHANGED

Transferencia

ASSET_TRANSFER_REQUESTED
ASSET_TRANSFER_APPROVED
ASSET_TRANSFER_SHIPPED
ASSET_TRANSFER_RECEIVED
ASSET_TRANSFER_REJECTED

Mantenimiento

MAINTENANCE_PLAN_CREATED
MAINTENANCE_WORK_ORDER_CREATED
MAINTENANCE_WORK_ORDER_APPROVED
MAINTENANCE_STARTED
MAINTENANCE_PAUSED
MAINTENANCE_COMPLETED
MAINTENANCE_CLOSED
MAINTENANCE_COST_CONFIRMED

Inspecciones

ASSET_INSPECTION_COMPLETED
ASSET_INSPECTION_FAILED

Mejoras

ASSET_IMPROVEMENT_COMPLETED
ASSET_CAPITALIZATION_PROPOSED
ASSET_CAPITALIZATION_ACCEPTED
ASSET_CAPITALIZATION_REJECTED

Inventario

ASSET_PHYSICAL_INVENTORY_STARTED
ASSET_SCANNED
ASSET_DISCREPANCY_DETECTED
ASSET_DISCREPANCY_RESOLVED
ASSET_PHYSICAL_INVENTORY_COMPLETED

Baja

ASSET_DISPOSAL_REQUESTED
ASSET_DISPOSAL_APPROVED
ASSET_DISPOSAL_REJECTED
ASSET_DISPOSED

Todos:

post-commit
event_id
operation_id
entity_id
occurred_at

⸻

88. IDEMPOTENCIA

Evitar:

doble activo
doble etiqueta
doble asignación
doble transferencia
doble work order
doble cierre
doble costo
doble capitalización
doble disposición
doble scan

Constraints:

UNIQUE(operation_id)
UNIQUE(asset_number)
UNIQUE(serial_number) cuando aplique
UNIQUE(tag_number)

⸻

89. UI/UX ENTERPRISE

Usar exclusivamente:

frontend/desktop/design_system/
frontend/desktop/components/
frontend/desktop/themes/

Prohibido:

modulos.design_tokens
modulos.ui_components
modulos.spj_styles
setStyleSheet
colores hardcodeados
emoji
QTableWidget
QTabWidget como navegación principal
QGroupBox estilizado
QFrame como card genérica

⸻

90. COMPONENTES ESTÁNDAR

Usar:

PageHeader
ModuleSidebar
ContextBar
KPIBar
SummaryCard
StandardCard
ChartCard
FilterBar
StandardTable V2
StandardDialog
StatusBadge
Tooltip
Toast
SearchInput
TextInput
IntegerInput
DecimalInput
MoneyInput
DateInput
DateTimeInput
SelectInput
EntitySearchInput
FileInput
KeyboardAwareInput
LoadingState
EmptyState
NoResultsState
ErrorState
OfflineState
PermissionDeniedState

⸻

91. DASHBOARD DE ACTIVOS

Máximo seis KPIs principales:

Activos en servicio
Valor de adquisición
Mantenimientos vencidos
Work Orders abiertas
Activos fuera de servicio
Costo mantenimiento del periodo

Secundarios:

garantías por vencer
activos críticos
activos sin custodio
activos no encontrados
MTBF
MTTR

UI no calcula KPI.

⸻

92. GRÁFICAS

Mostrar:

activos por categoría
activos por sucursal
condición
estado
mantenimientos preventivos/correctivos
costos mantenimiento
downtime
edad
valor proyectado

Usar:

ChartDTO
ChartBridge
ECharts
HtmlChartView

⸻

93. DIRECTORIO DE ACTIVOS

Usar:

PageHeader
KPIBar
FilterBar
StandardTable V2
PageState

Filtros:

folio
nombre
serial
categoría
sucursal
ubicación
custodio
estado
condición
criticidad
garantía

Columnas:

Etiqueta
Activo
Categoría
Serial
Sucursal
Ubicación
Custodio
Condición
Estado
Valor proyectado
Acciones

⸻

94. DETALLE DEL ACTIVO

Usar:

AssetSummaryHeader

Tabs internas:

Resumen
Información
Ubicación
Custodia
Mantenimiento
Inspecciones
Costos
Documentos
Garantía
Movimientos
Finanzas
Auditoría

Cada tab debe tener route_id.

⸻

95. WORK ORDER BOARD

Debe ofrecer:

Kanban
Tabla
Calendario

Kanban:

Requested
Approved
Scheduled
In Progress
Waiting
Completed

Mover tarjeta debe invocar UseCase.

No modificar estado solo en UI.

⸻

96. AGENDA DE MANTENIMIENTO

Mostrar:

día
semana
mes

Indicadores:

vencido
hoy
próximo
bloqueado
esperando proveedor

⸻

97. FORMULARIO DE ACTIVO

Secciones:

Identificación
Clasificación
Adquisición
Ubicación
Custodia
Características
Garantía
Documentación

No amontonar campos.

⸻

98. FORMULARIO DE WORK ORDER

Secciones:

Activo
Tipo
Problema / objetivo
Prioridad
Fecha
Asignación
Proveedor
Tareas
Refacciones
Costos estimados
Notas

⸻

99. MONEY INPUT

Eliminar:

QDoubleSpinBox

para dinero.

Usar:

MoneyInput + Decimal

Para:

valor de adquisición
costo estimado
costo real
costo mano de obra
costo refacciones

⸻

100. RESPONSIVE

Validar:

1366 × 768
1440 × 900
1600 × 900
1920 × 1080

No asumir Full HD.

⸻

101. TOUCH

Soportar:

compact
comfortable
touch

Touch:

botón principal      52–56 px
botón secundario     48–52 px
icon button          48 × 48 px
input                48–52 px
fila tabla           48–56 px
sidebar item         48–56 px

⸻

102. TECLADO VIRTUAL

Inputs compatibles:

text
integer
decimal
money

Deben usar KeyboardAwareInput.

⸻

103. ICONOGRAFÍA

Usar:

IconProvider

Keys:

asset
tools
maintenance
calendar
location
employee
transfer
inspection
document
warranty
insurance
qr
barcode
finance
dispose
warning

No emojis.

⸻

104. ACCESIBILIDAD

Auditar:

AccessibleName
AccessibleDescription
focus visible
orden de foco
teclado
contraste AA
tooltips
targets táctiles

⸻

105. OFFLINE-FIRST

Permitido offline cuando aplique:

consulta activos
scan QR
inventario físico
inspecciones
captura de condición
work order asignada

Toda mutación:

UUIDv7
operation_id
outbox
sync_status

Estados:

LOCAL_PENDING
SYNCING
SYNCED
CONFLICT
FAILED

⸻

106. CONFLICTOS OFFLINE

Crear:

AssetSyncConflict

Tipos:

ASSET_UPDATED_REMOTELY
CUSTODY_CHANGED
LOCATION_CHANGED
WORK_ORDER_CHANGED
DISPOSAL_STATE_CHANGED
PHYSICAL_COUNT_CONFLICT

No sobrescribir silenciosamente.

⸻

107. NOTIFICACIONES

Publicar alertas para:

mantenimiento próximo
mantenimiento vencido
garantía por vencer
seguro por vencer
activo crítico fuera de servicio
work order vencida
transferencia pendiente
activo faltante
baja pendiente

Notification Management decide canal.

⸻

108. EXCEPCIONES

Crear:

AssetNotFoundError
AssetAlreadyExistsError
AssetStateInvalidError
AssetConditionInvalidError
AssetAssignmentConflictError
AssetTransferNotAllowedError
MaintenancePlanNotFoundError
MaintenanceWorkOrderNotFoundError
MaintenanceStateInvalidError
MaintenanceCostInvalidError
InspectionNotFoundError
InspectionFailedError
AssetTagDuplicateError
AssetPhysicalInventoryConflictError
AssetDisposalNotAllowedError
AssetCapitalizationProposalInvalidError
AssetScopeDeniedError
DuplicateOperationError
PermissionDeniedError

Prohibido:

except Exception:
    pass

⸻

109. ELIMINACIÓN DE LEGACY

Eliminar progresivamente:

modulos/activos.py
core/services/asset_service.py monolítico
container
container.db
self.db
sqlite3 UI
QTableWidget
QTabWidget navegación
FPDF en módulo
design_tokens legacy
ui_components legacy
spj_styles
emojis
QDoubleSpinBox monetario
completar_y_pagar_mantenimiento
registrar_gasto_opex desde Assets
registrar_asiento desde Assets
cuentas contables 6105/1302
float depreciación
capitalización por UPDATE directo
estado baja directo
ubicación string libre
responsable string libre
Proveedor: texto

⸻

110. GUARDRAILS

Crear:

tests/architecture/test_assets_ui_has_no_sql.py
tests/architecture/test_assets_ui_has_no_repositories.py
tests/architecture/test_assets_ui_does_not_receive_app_container.py
tests/architecture/test_assets_use_uuidv7.py
tests/architecture/test_assets_have_no_integer_identity.py
tests/architecture/test_assets_use_decimal.py
tests/architecture/test_assets_do_not_post_journal_entries.py
tests/architecture/test_assets_do_not_execute_treasury_payments.py
tests/architecture/test_assets_do_not_own_financial_depreciation.py
tests/architecture/test_assets_maintenance_does_not_write_finance.py
tests/architecture/test_assets_parts_do_not_write_inventory.py
tests/architecture/test_assets_use_design_system.py
tests/architecture/test_assets_have_no_inline_styles.py
tests/architecture/test_assets_have_no_hardcoded_colors.py
tests/architecture/test_assets_have_no_emoji_icons.py
tests/architecture/test_assets_have_no_qtablewidget.py
tests/architecture/test_asset_routes_are_registered.py
tests/architecture/test_asset_permissions_are_granular.py
tests/architecture/test_asset_scopes_are_enforced.py
tests/architecture/test_assets_have_no_legacy_imports.py
tests/architecture/test_assets_legacy_allowlist_is_empty.py

⸻

111. TESTS FUNCIONALES

Activos

crear
editar
activar
comisionar
cambiar condición
suspender
reactivar

Custodia

asignar
reasignar
devolver
historial

Transferencia

solicitar
aprobar
enviar
recibir
rechazar

Mantenimiento

plan
generación automática
correctivo
aprobación
asignación
inicio
pausa
espera
completado
cierre

Inspección

crear
ejecutar
fallar
crear work order

Inventario físico

crear
scan
faltante
ubicación incorrecta
resolver
cerrar

Baja

solicitar
aprobar
rechazar
ejecutar
cancelar

Etiquetas

crear
imprimir
reimprimir
reemplazar
QR único

⸻

112. FASES DE IMPLEMENTACIÓN

ASSET-0 — Auditoría

funciones
UI
schema
SQL
services
finanzas
tesorería
mantenimiento
permisos
legacy

ASSET-1 — Guardrails

tests
allowlist
boundaries
UUID
Decimal
UI

ASSET-2 — Seguridad

permisos
roles
scopes
SoD
auditoría

ASSET-3 — Dominio base

Asset
Category
Location
Condition
Criticality

ASSET-4 — Custodia

Assignment
Loan
History

ASSET-5 — Transferencias

request
approval
transit
receipt

ASSET-6 — Mantenimiento

Plan
WorkOrder
Execution
Tasks

ASSET-7 — Inspecciones

Templates
Execution
Results

ASSET-8 — Medidores

Meters
Readings
Triggers

ASSET-9 — Documentación

documents
photos
warranties
insurance

ASSET-10 — Costos

operational cost
finance projection
capitalization proposal

ASSET-11 — Inventario físico

count
scan
discrepancy
resolution

ASSET-12 — Bajas

request
approve
execute

ASSET-13 — Etiquetas

tag
QR
barcode
Document Output

ASSET-14 — QueryServices

directory
detail
dashboard
maintenance
financial projection

ASSET-15 — Integraciones

Finance
Purchases
Treasury
Inventory
HR
BI
Notifications

ASSET-16 — UI Foundations

routes
sidebar
PageHeader
Design System

ASSET-17 — Dashboard

KPIs
charts
alerts

ASSET-18 — Directorio y detalle

StandardTable
filters
detail
timeline

ASSET-19 — Maintenance UI

Kanban
calendar
work orders

ASSET-20 — Responsive / Touch

resolutions
density
keyboard
accessibility

ASSET-21 — Offline

scan
inspection
count
sync
conflicts

ASSET-22 — Migración consumidores

Finance
Purchases
HR
Inventory
Config

ASSET-23 — Eliminación legacy

modulos/activos.py
AssetService monolítico
finance writes
QTableWidget
legacy UI
imports
allowlist

ASSET-24 — Validación final

unit
integration
e2e
architecture
security
UI
visual
offline
UUIDv7
Decimal
legacy
bootstrap limpio

⸻

113. DEFINICIÓN DE TERMINADO

[ ] Activos es bounded context independiente.
[ ] Finanzas no es dueño del ciclo operativo del activo.
[ ] Activos no registra asientos.
[ ] Activos no ejecuta pagos.
[ ] Activos no administra CxP.
[ ] Existe Asset aggregate.
[ ] Existen categorías configurables.
[ ] Existe folio operativo.
[ ] Todos los IDs usan UUIDv7.
[ ] Todo dinero usa Decimal.
[ ] Existe ubicación jerárquica.
[ ] Existe custodia.
[ ] Existe historial de asignación.
[ ] Existen transferencias.
[ ] Existen préstamos.
[ ] Existe MaintenancePlan.
[ ] Existe MaintenanceWorkOrder.
[ ] Existe mantenimiento preventivo.
[ ] Existe correctivo.
[ ] Existe mantenimiento interno.
[ ] Existe mantenimiento externo.
[ ] Existe integración con proveedores.
[ ] Existen inspecciones.
[ ] Existen checklists.
[ ] Existen medidores.
[ ] Existen garantías.
[ ] Existen seguros.
[ ] Existen documentos.
[ ] Existen fotografías.
[ ] Existe inventario físico.
[ ] Existen discrepancias.
[ ] Existe workflow de baja.
[ ] Existe pérdida/robo.
[ ] Existe AssetTag.
[ ] Existe QR seguro.
[ ] Existe barcode.
[ ] Toda impresión usa PrintJob.
[ ] PDF usa Document Output.
[ ] Existe integración con Compras.
[ ] Existe integración con Finanzas.
[ ] Existe integración con Inventario.
[ ] Existe integración con RRHH.
[ ] Existe integración con BI.
[ ] Existe Notification Management.
[ ] Existe propuesta de capitalización.
[ ] Finanzas aprueba y contabiliza capitalización.
[ ] Depreciación financiera pertenece a Finanzas.
[ ] Activos muestra proyección financiera.
[ ] Existe MTBF.
[ ] Existe MTTR.
[ ] Existen indicadores.
[ ] Existen roles.
[ ] Existen permisos granulares.
[ ] Existen scopes.
[ ] Existe segregación de funciones.
[ ] Existe auditoría.
[ ] Existe idempotencia.
[ ] Existe outbox.
[ ] Existe offline-first donde aplica.
[ ] Existe ModuleSidebar.
[ ] Existe PageHeader.
[ ] Existe StandardTable V2.
[ ] Existe Kanban de work orders.
[ ] Existe calendario.
[ ] Existe Design System canónico.
[ ] No existe QTableWidget.
[ ] No existe QTabWidget como navegación principal.
[ ] No existen emojis.
[ ] No existen colores hardcodeados.
[ ] No existe QSS local.
[ ] No existe QDoubleSpinBox para dinero.
[ ] Funciona en 1366 × 768.
[ ] Funciona en 1920 × 1080.
[ ] Funciona light/dark.
[ ] Funciona touch.
[ ] Existe accesibilidad.
[ ] No existe modulos/activos.py legacy.
[ ] No existe AssetService monolítico.
[ ] No existen imports legacy.
[ ] Allowlist vacía.
[ ] Bootstrap limpio funciona.
[ ] CI verde.
[ ] Todos los tests pasan.

⸻

114. REPORTE FINAL

Entregar:

1. Funciones originales encontradas.
2. Funciones preservadas.
3. Funciones movidas.
4. Funciones reescritas.
5. SQL encontrado.
6. Acoplamientos con Finanzas encontrados.
7. Acoplamientos con Tesorería encontrados.
8. IDs incorrectos encontrados.
9. floats encontrados.
10. Componentes UI legacy encontrados.
11. Entidades creadas.
12. Policies creadas.
13. UseCases creados.
14. QueryServices creados.
15. Eventos creados.
16. Permisos creados.
17. Roles creados.
18. Scopes creados.
19. Integraciones creadas.
20. Páginas creadas.
21. Componentes UI creados.
22. Legacy eliminado.
23. Tests creados.
24. Tests ejecutados.
25. Evidencia visual.
26. Allowlist inicial.
27. Allowlist final.
28. Bootstrap limpio.
29. Riesgos pendientes.

Tabla obligatoria:

| Elemento anterior | Destino canónico | Acción | Consumidores restantes |
|-------------------|------------------|--------|------------------------|
| modulos/activos.py | AssetsView | DELETE | 0 |
| AssetService monolítico | UseCases + Repositories | DELETE | 0 |
| container | DI explícita | DELETE | 0 |
| container.db | UoW/Repositories | DELETE | 0 |
| QTableWidget | StandardTable V2 | DELETE | 0 |
| QTabWidget global | RouteRegistry + ModuleSidebar | DELETE | 0 |
| categorías hardcodeadas | AssetCategory | DELETE | 0 |
| ubicación texto | AssetLocation | DELETE | 0 |
| realizado_por texto | Employee/Supplier reference | DELETE | 0 |
| completar+y+pagar | WorkOrder + Finance flow | DELETE | 0 |
| registrar_gasto_opex | Finance integration | DELETE | 0 |
| registrar_asiento | Finance | DELETE | 0 |
| depreciación local | Finance projection | DELETE | 0 |
| capitalización UPDATE | Capitalization workflow | DELETE | 0 |
| QDoubleSpinBox money | MoneyInput + Decimal | DELETE | 0 |
| FPDF UI | Document Output | DELETE | 0 |
| emoji icons | IconProvider | DELETE | 0 |
| design_tokens legacy | Design System | DELETE | 0 |
| ui_components legacy | Standard Components | DELETE | 0 |

⸻

115. REGLA FINAL

Un solo Asset Registry.
Una sola identidad de activo.
Una sola arquitectura de custodia.
Una sola arquitectura de ubicación.
Una sola arquitectura de mantenimiento.
Una sola arquitectura de inspección.
Una sola arquitectura de transferencia.
Una sola arquitectura de inventario físico.
Una sola arquitectura de baja.
Una sola integración financiera.
Una sola arquitectura UI.
Un solo Design System.

Activos administra el ciclo físico y operativo.

Compras administra la adquisición comercial.

Inventario administra refacciones y consumibles.

RRHH administra empleados y técnicos internos.

Finanzas administra valor contable, depreciación, CAPEX, OPEX y asientos.

Cuentas por pagar administra obligaciones con proveedores.

Tesorería administra pagos.

Document Output administra etiquetas y reportes.

Notification Management administra alertas.

BI administra analítica avanzada.

La UI presenta.

Los Presenters coordinan.

Los UseCases mutan.

Los QueryServices leen.

Los Repositories persisten.

Los permisos autorizan.

Los scopes limitan datos.

Los eventos integran bounded contexts.

La idempotencia evita operaciones duplicadas.

La auditoría demuestra quién creó, recibió, asignó, transfirió, mantuvo, inspeccionó, contabilizó, dio de baja o reubicó cada activo.

El resultado final debe ser un Enterprise Asset Management integrado al ERP/POS/SaaS, no únicamente un catálogo de equipos con una agenda de mantenimiento.