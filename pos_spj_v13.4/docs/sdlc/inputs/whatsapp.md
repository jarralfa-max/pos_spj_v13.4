PROMPT MAESTRO DEFINITIVO — REFACTOR ENTERPRISE DEL MÓDULO Y CANAL WHATSAPP SPJ ERP/POS

Trabaja sobre el repositorio:

jarralfa-max/pos_spj_v13.4

El objetivo es auditar, rediseñar, consolidar e implementar la arquitectura canónica empresarial de WhatsApp para SPJ ERP/POS:

WhatsApp Channel
Conversational Commerce
Customer Messaging
Inbound Webhooks
Outbound Messaging
Conversation Management
Intent Resolution
Human Handoff
Template Management
Customer Notifications
Internal Notifications
Order Capture
Quote Capture
Payment Coordination
Delivery Coordination
Loyalty Messaging
Operational Alerts
Channel Analytics

La refactorización debe abarcar:

whatsapp_service/
pos_spj_v13.4/core/services/whatsapp_service.py
pos_spj_v13.4/services/whatsapp_service.py
pos_spj_v13.4/integrations/whatsapp_service.py
pos_spj_v13.4/core/integrations/whatsapp_client.py
pos_spj_v13.4/core/services/pedidos_whatsapp_service.py
pos_spj_v13.4/core/services/delivery_whatsapp_service.py
pos_spj_v13.4/notifications/whatsapp_channel.py
pos_spj_v13.4/modulos/whatsapp*
pos_spj_v13.4/core/use_cases/pedido_wa.py
todos los flows, routers, gateways, bridges, webhooks,
migraciones, tablas, tests e integraciones relacionadas.

El resultado debe cumplir estándares modernos de:

SaaS
ERP enterprise
omnichannel commerce
WhatsApp Business Platform
multiempresa futuro
multi-sucursal
multi-número
multi-agente
multi-canal futuro
offline-aware
event-driven
idempotent
privacy-aware
consent-aware
security-first
audit-ready
observability-ready
provider-agnostic

⸻

1. PRINCIPIO RECTOR

WhatsApp es un canal de interacción.

No es dueño de:

clientes
productos
precios
stock
ventas
pedidos
cotizaciones
pagos
delivery
crédito
fidelidad
contabilidad
inventario

WhatsApp debe:

recibir mensajes
validar autenticidad
normalizar identidad del canal
resolver intención
mantener contexto conversacional
consultar capacidades del ERP
solicitar operaciones mediante UseCases o APIs
comunicar resultados
escalar a humano
registrar trazabilidad del canal

Regla central:

WhatsApp conversa.
Los bounded contexts deciden.
WhatsApp no replica negocio.

Ejemplos:

WhatsApp solicita precio.
Pricing responde.
WhatsApp solicita disponibilidad.
Inventario responde.
WhatsApp solicita crear pedido.
Orders crea el pedido.
WhatsApp solicita cotización.
Quotes crea la cotización.
WhatsApp solicita pago.
Payments genera o valida el pago.
WhatsApp comunica seguimiento.
Delivery proporciona el estado.
WhatsApp muestra puntos.
Loyalty proporciona el resumen.

⸻

2. CONTEXTO NO NEGOCIABLE

SPJ ERP/POS continúa en desarrollo activo.

No existen datos productivos que obliguen a mantener arquitectura legacy.

Por tanto:

- No conservar dos webhooks.
- No conservar dos senders.
- No conservar dos colas.
- No conservar dos sistemas de eventos.
- No conservar ERPBridge con escrituras de negocio.
- No conservar SQL del ERP dentro de WhatsApp.
- No conservar reglas de precio en flows.
- No conservar reglas de stock en flows.
- No conservar cálculo de anticipos en flows.
- No conservar delivery dentro del bridge.
- No conservar fallbacks a SQLite.
- No mantener lectura dual.
- No mantener escritura dual.
- No mantener eventos legacy y canónicos en paralelo.
- No mantener rutas duplicadas.
- No mantener normalización de teléfonos dispersa.
- No mantener secretos en código.
- No mantener tokens en logs.
- No mantener X-Internal-Key hardcodeada.
- No mantener handlers registrados globalmente.
- No mantener sys.path hacks.
- No mantener imports ambiguos.
- No mantener idempotencia solo por message_id.
- No mantener una UI monolítica de WhatsApp.
- No mantener valores comerciales hardcodeados.

La base puede reconstruirse.

El resultado debe ser:

born-clean
born-UUIDv7
provider-agnostic
API-driven
domain-isolated
business-idempotent
conversation-stateful
outbox-driven
secret-store-backed
consent-aware
multi-number
multi-branch
multi-agent
human-handoff-ready
auditable
observable
sin legacy
sin SQL de negocio

⸻

3. SKILLS OBLIGATORIOS

Leer completamente:

docs/skills/SPJ_REFACTOR_SKILL.md
docs/skills/SPJ_UI_UX_ARCHITECTURE_SKILL.md
docs/skills/SPJ_BUGFIX_AUDIT_CORRECTION_SKILL.md

También revisar todos los Skills aplicables dentro de:

docs/skills/

Prioridad:

1. SPJ_REFACTOR_SKILL.md
2. SPJ_UI_UX_ARCHITECTURE_SKILL.md
3. SPJ_BUGFIX_AUDIT_CORRECTION_SKILL.md
4. Los demás Skills aplicables

Ante conflicto prevalece:

SPJ_REFACTOR_SKILL.md

⸻

4. FASE CERO OBLIGATORIA: AUDITORÍA

Auditar completamente:

whatsapp_service/
core/services/whatsapp_service.py
services/whatsapp_service.py
integrations/whatsapp_service.py
core/integrations/whatsapp_client.py
core/services/pedidos_whatsapp_service.py
core/services/delivery_whatsapp_service.py
notifications/whatsapp_channel.py
modulos/whatsapp/
modulos/whatsapp_module.py
core/use_cases/pedido_wa.py
core/services/microservice_launcher.py
migrations/
tests/
logs/
.env*
config/

Buscar:

WhatsAppWebhookServer
WebhookHandler
ERPBridge
BusinessOrchestrator
WAEventEmitter
MessageRouter
NumberRouter
DeliveryRouter
NotifyRouter
send_message
send_text
whatsapp_queue
wa_event_log
notification_inbox
message_log
X-Internal-Key
VERIFY_TOKEN
ACCESS_TOKEN
PHONE_NUMBER_ID
sqlite3
INSERT INTO ventas
UPDATE ventas
INSERT INTO clientes
INSERT INTO anticipos
INSERT INTO cotizaciones

Crear:

docs/refactor/whatsapp_legacy_inventory.md
docs/refactor/whatsapp_runtime_map.md
docs/refactor/whatsapp_business_logic_leakage.md
docs/refactor/whatsapp_security_audit.md
docs/refactor/whatsapp_event_inventory.md
docs/refactor/whatsapp_schema_consolidation.md

Clasificar:

REUSE
MOVE
WRAP_TEMPORARILY
REWRITE
DELETE
BLOCKED

Todo BLOCKED debe incluir:

causa
riesgo
responsable
dependencia
condición de eliminación

⸻

5. BOUNDED CONTEXTS Y RESPONSABILIDADES

WhatsApp Channel

Dueño de:

cuentas de canal
números
identidades del canal
mensajes
conversaciones
sesiones conversacionales
contexto de conversación
plantillas de mensajería
webhooks
entregas
estados de mensajes
handoff
agentes
consentimientos operativos del canal
preferencias del canal
métricas del canal
auditoría del canal

Orders and Delivery

Dueño de:

pedidos
líneas
totales
preparación
peso real
entrega
rutas
repartidores
estado de pedido

Quotes

Dueño de:

cotizaciones
vigencia
precios
aceptación
conversión

Payments

Dueño de:

links
anticipos
confirmaciones
reversos
conciliación

Customers

Dueño de:

identidad
teléfono
nombre
direcciones
consentimientos

Loyalty

Dueño de:

puntos
nivel
tarjeta digital
beneficios
cupones
vales
sorteos

⸻

6. ARQUITECTURA OBJETIVO

whatsapp_service/
├── main.py
├── bootstrap/
│   ├── application_factory.py
│   ├── composition_root.py
│   ├── service_registry.py
│   ├── dependency_graph_validator.py
│   ├── lifecycle.py
│   └── health_checks.py
│
├── domain/
│   └── whatsapp/
│       ├── entities/
│       ├── value_objects/
│       ├── policies/
│       ├── services/
│       ├── repository_ports.py
│       ├── provider_ports.py
│       ├── events.py
│       ├── enums.py
│       └── exceptions.py
│
├── application/
│   └── whatsapp/
│       ├── commands/
│       ├── queries/
│       ├── dto/
│       ├── use_cases/
│       ├── authorization/
│       ├── event_handlers/
│       ├── notification_handlers/
│       └── outbox_handlers/
│
├── infrastructure/
│   ├── providers/
│   │   └── meta_cloud_api/
│   ├── persistence/
│   ├── webhooks/
│   ├── messaging/
│   ├── ai/
│   ├── security/
│   ├── secrets/
│   ├── observability/
│   └── erp_clients/
│
├── api/
│   ├── routers/
│   ├── middleware/
│   ├── dependencies/
│   ├── schemas/
│   └── error_handlers/
│
├── conversations/
│   ├── flows/
│   ├── intents/
│   ├── state_machine/
│   ├── response_templates/
│   └── handoff/
│
└── tests/

⸻

7. main.py MÍNIMO

whatsapp_service/main.py debe limitarse a:

crear FastAPI
invocar ApplicationFactory
registrar lifespan
registrar routers canónicos

No debe:

modificar sys.path
abrir SQLite
ejecutar migraciones del ERP
crear ERPBridge
crear parsers
crear routers manualmente
registrar globals
construir lógica de negocio

Ejemplo conceptual:

app = WhatsAppApplicationFactory().create()

⸻

8. COMPOSITION ROOT DEL MICROSERVICIO

Crear:

WhatsAppCompositionRoot

Debe construir:

ProviderGateway
WebhookAuthenticator
SecretStoreGateway
ConversationRepository
MessageRepository
OutboxRepository
IdempotencyRepository
WhatsAppAccountRepository
TemplateRepository
AgentRepository
ERP API clients
IntentResolver
ConversationEngine
HandoffCoordinator
OutboundMessageDispatcher
WebhookProcessor

No exponer un contenedor completo a flows.

No utilizar globals mutables.

⸻

9. UUIDV7

Usar:

from backend.shared.ids import new_uuid

Deben usar UUIDv7:

whatsapp_account_id
channel_number_id
channel_identity_id
conversation_id
conversation_session_id
message_id
message_delivery_id
message_template_id
template_version_id
intent_resolution_id
handoff_id
agent_assignment_id
business_operation_id
idempotency_record_id
outbox_event_id
webhook_delivery_id
consent_record_id
operation_id
event_id

Prohibido:

INTEGER PRIMARY KEY
AUTOINCREMENT
lastrowid
MAX(id) + 1

Los IDs de Meta se almacenan como identificadores externos, no como PK.

⸻

10. CUENTAS Y NÚMEROS

Crear:

WhatsAppBusinessAccount
WhatsAppChannelNumber
WhatsAppProviderConfiguration

Cuenta

id
provider
business_account_external_id
display_name
status
secret_reference_id
created_at
updated_at

Número

id
account_id
phone_number_external_id
display_phone_number
normalized_phone_number
branch_id
channel_role
status
timezone
locale
created_at
updated_at

Roles:

GLOBAL_CUSTOMER_SERVICE
BRANCH_SALES
BRANCH_ORDERS
DELIVERY
INTERNAL_OPERATIONS
MARKETING

Estados:

DRAFT
ACTIVE
DEGRADED
SUSPENDED
DISCONNECTED
RETIRED

⸻

11. MULTI-NÚMERO Y ENRUTAMIENTO

Crear:

InboundNumberRoutingPolicy
OutboundNumberRoutingPolicy

Reglas:

- número por sucursal;
- número global;
- número de delivery;
- número interno;
- número promocional;
- fallback controlado;

Flujo global:

mensaje entrante
    ↓
identificar número receptor
    ↓
resolver cuenta
    ↓
resolver sucursal
    ↓
resolver rol de canal
    ↓
crear contexto

Si el número es global:

resolver sucursal por cliente, dirección,
preferencia o conversación explícita

No asumir sucursal Principal.

⸻

12. IDENTIDAD DEL CANAL

Crear:

WhatsAppIdentity

Campos:

id
wa_id
normalized_phone
customer_id opcional
identity_status
first_seen_at
last_seen_at
blocked_at
created_at
updated_at

Estados:

UNRESOLVED
RESOLVED
VERIFIED
BLOCKED
MERGED

El teléfono no es PK.

La identidad WhatsApp puede vincularse a un cliente, pero no reemplazarlo.

⸻

13. NORMALIZACIÓN DE TELÉFONOS

Crear una única capacidad:

PhoneNumberNormalizer

Debe soportar:

+52
521 legacy
whatsapp:+52
espacios
guiones
paréntesis
prefijos nacionales

Salida canónica:

E.164

No duplicar normalización en sender, bridge, flows o UI.

⸻

14. CONVERSACIONES

Crear:

WhatsAppConversation
ConversationSession
ConversationContext

Estados de conversación:

OPEN
BOT_ACTIVE
WAITING_CUSTOMER
WAITING_ERP
WAITING_PAYMENT
WAITING_APPROVAL
HANDOFF_REQUESTED
HUMAN_ACTIVE
RESOLVED
CLOSED
EXPIRED
BLOCKED

El contexto debe ser versionado y validado.

No almacenar objetos Python serializados arbitrariamente.

⸻

15. MENSAJES

Crear:

WhatsAppMessage
WhatsAppMessageDelivery

Tipos:

TEXT
IMAGE
DOCUMENT
AUDIO
VIDEO
LOCATION
CONTACT
INTERACTIVE
BUTTON_REPLY
LIST_REPLY
TEMPLATE
REACTION
SYSTEM

Dirección:

INBOUND
OUTBOUND
INTERNAL

Estados outbound:

QUEUED
VALIDATING
SENT
DELIVERED
READ
FAILED
RETRYING
DEAD_LETTER
CANCELLED

Guardar:

provider_message_id
conversation_id
direction
message_type
payload_reference
status
sent_at
delivered_at
read_at
failed_at
error_code
correlation_id
operation_id

⸻

16. PRIVACIDAD DEL CONTENIDO

No guardar indefinidamente todo el contenido sin política.

Crear:

MessageRetentionPolicy
SensitiveMessagePolicy

Configurar:

retention_days
media_retention_days
redaction_enabled
encryption_at_rest
export_allowed
deletion_policy

Enmascarar:

datos bancarios
tokens
credenciales
documentos sensibles

⸻

17. WEBHOOK OFICIAL ÚNICO

Debe existir un solo webhook canónico:

GET /webhooks/whatsapp
POST /webhooks/whatsapp

Responsabilidades:

verificación
firma
timestamp
replay protection
parseo técnico
dedupe técnico
enrutamiento a aplicación
respuesta rápida 200

No debe:

crear pedidos
calcular totales
consultar stock
generar pagos
programar delivery

⸻

18. SEGURIDAD DEL WEBHOOK

Crear:

WebhookSignatureValidator
WebhookReplayProtectionPolicy
WebhookTimestampPolicy

Validar:

firma Meta
app secret
timestamp
payload hash
provider event ID

No depender solo de verify token.

Registrar intentos inválidos.

No guardar secretos en logs.

⸻

19. IDEMPOTENCIA TÉCNICA Y DE NEGOCIO

Separar:

Idempotencia técnica

provider_message_id
provider_event_id
payload_hash

Idempotencia de negocio

business_operation_id
intent
customer/channel identity
aggregate
operation fingerprint

Ejemplo:

dos mensajes diferentes:
“confirmar pedido”
“sí, confirmar”
pueden representar la misma acción.

Crear:

BusinessOperationIdempotencyRecord

Campos:

operation_id
operation_type
aggregate_type
aggregate_id
fingerprint
status
result_reference
created_at
completed_at

⸻

20. PROCESAMIENTO ASÍNCRONO

El webhook debe:

validar
persistir mensaje
crear inbox job
responder 200

Luego un worker:

procesa intención
consulta ERP
responde

Crear:

InboundMessageJob
InboundMessageWorker

No mantener el webhook bloqueado por llamadas a IA, DB o ERP.

⸻

21. INBOX Y OUTBOX

Crear:

WhatsAppInbox
WhatsAppOutbox

Inbox:

mensaje entrante
estado
intentos
bloqueo
error

Outbox:

mensaje saliente
plantilla
payload
destino
cuenta
intentos
estado

Estados:

PENDING
PROCESSING
COMPLETED
FAILED
RETRY
DEAD_LETTER

Toda salida crítica debe ser persistida antes de enviarse.

⸻

22. PROVIDER GATEWAY

Crear puerto:

WhatsAppProviderGateway

Implementación inicial:

MetaCloudApiWhatsAppGateway

Métodos:

send_text
send_template
send_interactive
send_media
mark_read
download_media
get_message_status
health_check

No llamar directamente a requests o httpx desde flows.

⸻

23. SECRETOS

Todos los secretos deben usar:

SecretStoreGateway

Incluye:

access token
app secret
verify token
internal API secret
Mercado Pago webhook secret
encryption keys

Configuración guarda:

secret_reference_id
masked_value
last_rotated_at
status

Nunca guardar tokens en:

código
Git
JSON público
SQLite en texto plano
logs
tracebacks
QSettings

⸻

24. PLANTILLAS DE MENSAJES

Crear:

WhatsAppMessageTemplate
WhatsAppMessageTemplateVersion

Tipos:

UTILITY
MARKETING
AUTHENTICATION
INTERNAL_OPERATIONAL

Campos:

provider_template_name
provider_template_external_id
language
category
parameter_schema
status
effective_from
effective_to
version

Estados:

DRAFT
PENDING_PROVIDER_APPROVAL
APPROVED
REJECTED
PAUSED
DISABLED
ARCHIVED

No hardcodear textos en flows.

⸻

25. RESPONSE TEMPLATES INTERNAS

Diferenciar:

provider-approved templates
conversation response templates
internal notification templates

Crear:

ConversationResponseTemplate

Para mensajes dentro de ventana conversacional.

Todo texto debe poder versionarse y localizarse.

⸻

26. MOTOR CONVERSACIONAL

Crear:

ConversationEngine
ConversationStateMachine

El motor debe gestionar:

estado
intención
datos faltantes
confirmaciones
cancelación
timeout
reinicio
handoff

No implementar cada flow como secuencia informal de if/elif.

⸻

27. INTENCIONES

Crear catálogo:

IntentDefinition
IntentResolution

Intenciones:

GREETING
SHOW_MENU
SELECT_BRANCH
SEARCH_PRODUCT
CHECK_PRICE
CHECK_STOCK
CREATE_ORDER
UPDATE_ORDER
CANCEL_ORDER
CREATE_QUOTE
ACCEPT_QUOTE
REJECT_QUOTE
PAY_ORDER
CHECK_ORDER_STATUS
SCHEDULE_DELIVERY
TRACK_DELIVERY
REGISTER_CUSTOMER
UPDATE_ADDRESS
CHECK_LOYALTY
SHOW_DIGITAL_CARD
CHECK_COUPON
HUMAN_HANDOFF
OPT_OUT
HELP
UNKNOWN

⸻

28. RESOLUCIÓN DE INTENCIÓN POR CAPAS

Orden recomendado:

1. Interactive reply determinista.
2. State-machine expected response.
3. Regla/regex segura.
4. Intent classifier.
5. LLM fallback controlado.
6. Human handoff.

No permitir que el LLM ejecute operaciones directamente.

⸻

29. IA Y LLM

Crear puerto:

IntentAIProvider

La IA puede:

clasificar intención
extraer entidades
proponer respuesta
detectar ambigüedad

No puede:

crear venta
modificar stock
autorizar crédito
confirmar pago
cancelar pedido
emitir vale
ajustar puntos

Toda acción pasa por UseCase y confirmación.

⸻

30. ENTIDADES EXTRAÍDAS

Crear:

IntentEntity

Tipos:

PRODUCT
QUANTITY
UNIT
BRANCH
ADDRESS
DATE
TIME
PAYMENT_METHOD
ORDER_REFERENCE
QUOTE_REFERENCE
COUPON_CODE
CARD_REFERENCE

Toda entidad debe incluir:

value
normalized_value
confidence
source
validation_status

No confiar en entidades de IA sin validación de dominio.

⸻

31. CONTEXTO CONVERSACIONAL

El contexto puede guardar referencias:

customer_id
branch_id
active_order_draft_id
active_quote_id
delivery_address_id
expected_intent
expected_entity
last_confirmed_action

No debe guardar copias maestras de:

productos
precios
stock
saldo de crédito
puntos

Estos se consultan en el momento necesario.

⸻

32. MENÚ CONVERSACIONAL

Debe ser configurable:

Comprar
Consultar precios
Cotización
Seguimiento de pedido
Delivery
Puntos y beneficios
Hablar con una persona

No hardcodear categorías o productos.

Usar interactive lists/buttons cuando el proveedor lo permita.

⸻

33. CATÁLOGO DE PRODUCTOS

WhatsApp consume:

ProductCatalogQueryService
PricingQueryService
AvailabilityQueryService

No consulta tablas.

No calcula precios.

No mantiene catálogo duplicado.

⸻

34. PEDIDOS

WhatsApp no crea filas de ventas directamente.

Flujo:

cliente selecciona productos
    ↓
WhatsApp crea draft conversacional
    ↓
consulta catálogo y precios
    ↓
solicita CreateCustomerOrder
    ↓
Orders valida
    ↓
Orders devuelve order_id y resumen
    ↓
WhatsApp confirma al cliente

El draft conversacional no es el pedido canónico.

⸻

35. CANTIDADES Y PRODUCTOS POR PESO

Debe soportar:

kg
gramos
pieza
paquete
caja
unidad comercial

Para productos de peso variable:

cantidad estimada
peso preparado
ajuste
aprobación del cliente
total final

WhatsApp consume el workflow de Orders.

No recalcula el total final.

⸻

36. AJUSTES DE PESO

Flujo:

Orders detecta ajuste
    ↓
publica approval required
    ↓
WhatsApp solicita decisión
    ↓
cliente acepta/rechaza
    ↓
WhatsApp envía comando idempotente
    ↓
Orders actualiza

No guardar aprobación solo en contexto conversacional.

⸻

37. COTIZACIONES

Flujo:

capturar intención
    ↓
consultar precio
    ↓
solicitar CreateQuote
    ↓
Quotes genera folio y vigencia
    ↓
WhatsApp presenta

Aceptación:

AcceptQuoteUseCase

No convertir directamente mediante SQL.

⸻

38. PAGOS Y ANTICIPOS

WhatsApp consume:

CreatePaymentLinkUseCase
GetPaymentStatusQuery
RegisterPaymentIntentUseCase

No calcula anticipo.

No confirma pago por su cuenta.

Webhook de proveedor:

valida firma
dedupe
solicita ConfirmPaymentUseCase

⸻

39. WEBHOOK DE MERCADO PAGO

Debe pertenecer al bounded context Payments o a un gateway de pagos, no al dominio WhatsApp.

WhatsApp puede:

solicitar link
enviar link
comunicar confirmación

Pero no debe ser dueño del webhook financiero.

Si temporalmente comparte proceso, mantener paquetes separados y contratos explícitos.

⸻

40. CRÉDITO

WhatsApp consume:

CustomerCreditEligibilityQuery
CreditAuthorizationUseCase

No autoriza crédito.

No cambia límites.

No omite anticipo salvo decisión canónica.

⸻

41. DELIVERY

WhatsApp consume:

CreateDeliveryRequestUseCase
DeliveryTrackingQuery
CustomerDeliveryDecisionUseCase

No programa rutas.

No asigna repartidores.

No actualiza delivery_orders directamente.

⸻

42. UBICACIÓN Y DIRECCIONES

Soportar:

ubicación compartida
dirección escrita
dirección guardada
referencias
confirmación de mapa

Clientes es dueño de direcciones.

Delivery valida zona y tarifa.

WhatsApp solo captura y confirma.

⸻

43. FIDELIDAD

WhatsApp consume:

LoyaltySummaryQuery
DigitalLoyaltyCardQuery
CouponValidationQuery

Puede mostrar:

puntos
nivel
progreso
recompensas
tarjeta digital
QR
participaciones

No calcula puntos ni emite instrumentos directamente.

⸻

44. CLIENTES

Flujo de registro:

capturar datos mínimos
    ↓
mostrar aviso de privacidad
    ↓
solicitar consentimiento
    ↓
CreateCustomerUseCase
    ↓
vincular WhatsAppIdentity

No insertar clientes mediante fallback.

No crear clientes silenciosamente.

⸻

45. CONSENTIMIENTOS

Crear soporte para:

service_messages_consent
marketing_consent
whatsapp_consent
profiling_consent
consent_version
consented_at
withdrawn_at

Diferenciar:

mensajes transaccionales
mensajes operativos
marketing
campañas

STOP, BAJA, CANCELAR PROMOCIONES deben procesarse canónicamente.

⸻

46. OPT-OUT

Crear:

ProcessWhatsAppOptOutUseCase

Debe:

registrar revocación
detener marketing
mantener mensajes permitidos legalmente
auditar
confirmar al usuario

No borrar automáticamente la identidad o historial obligatorio.

⸻

47. HUMAN HANDOFF

Crear:

HandoffRequest
AgentAssignment
AgentSession

Estados:

REQUESTED
QUEUED
ASSIGNED
ACTIVE
WAITING_CUSTOMER
RESOLVED
CANCELLED
EXPIRED

Motivos:

CUSTOMER_REQUEST
LOW_CONFIDENCE
PAYMENT_ISSUE
COMPLAINT
CREDIT_REVIEW
ORDER_EXCEPTION
DELIVERY_EXCEPTION
FRAUD_RISK

⸻

48. ENRUTAMIENTO DE AGENTES

Crear:

AgentRoutingPolicy

Criterios:

sucursal
horario
cola
especialidad
carga
idioma
prioridad
cliente

No asignar agente mediante campo suelto en conversación.

⸻

49. BANDEJA DE ATENCIÓN

La UI debe incluir una bandeja enterprise:

Conversaciones
Pendientes
Asignadas a mí
Esperando cliente
Esperando ERP
Escaladas
Resueltas
Spam/Bloqueadas

Cada conversación debe mostrar:

cliente
número
sucursal
último mensaje
estado
intención
pedido activo
prioridad
agente
SLA

⸻

50. NOTIFICACIONES SALIENTES

WhatsApp puede entregar notificaciones de:

pedido confirmado
pedido en preparación
ajuste de peso
pedido listo
repartidor asignado
pedido en camino
entrega completada
pago recibido
cotización creada
cotización próxima a vencer
puntos ganados
recompensa desbloqueada
tarjeta digital
sorteo
recordatorio autorizado

Cada módulo publica eventos.

Notification Management decide canal, plantilla y destinatario.

⸻

51. ALERTAS INTERNAS

Mensajes internos pueden incluir:

stock crítico
transferencia pendiente
pedido urgente
incidencia de delivery
pago fallido
dispositivo fuera de línea
aprobación requerida

No usar WhatsApp como sustituto del Notification Center interno.

Debe existir política de severidad y escalamiento.

⸻

52. INTERNAL API

El ERP y WhatsApp deben comunicarse mediante contratos autenticados.

Crear:

ERPChannelGateway

Métodos por bounded context, no uno genérico con SQL.

Ejemplos:

OrdersApiClient
QuotesApiClient
PaymentsApiClient
CustomersApiClient
InventoryApiClient
LoyaltyApiClient
DeliveryApiClient

⸻

53. AUTENTICACIÓN INTERNA

No usar una clave hardcodeada simple.

Implementar:

HMAC request signing
timestamp
nonce
replay protection
secret rotation
service identity

Cada llamada incluye:

service_id
timestamp
nonce
signature
correlation_id

⸻

54. SERVICE IDENTITY

Crear identidad técnica:

WHATSAPP_CHANNEL_SERVICE

Debe:

tener permisos mínimos
no iniciar sesión en UI
usar SecretStore
ser revocable
ser rotatable
ser auditable

⸻

55. EVENTOS CANÓNICOS DEL CANAL

WHATSAPP_WEBHOOK_RECEIVED
WHATSAPP_MESSAGE_RECEIVED
WHATSAPP_MESSAGE_DEDUPLICATED
WHATSAPP_MESSAGE_CLASSIFIED
WHATSAPP_INTENT_RESOLVED
WHATSAPP_CONVERSATION_OPENED
WHATSAPP_CONVERSATION_STATE_CHANGED
WHATSAPP_MESSAGE_QUEUED
WHATSAPP_MESSAGE_SENT
WHATSAPP_MESSAGE_DELIVERED
WHATSAPP_MESSAGE_READ
WHATSAPP_MESSAGE_FAILED
WHATSAPP_HANDOFF_REQUESTED
WHATSAPP_AGENT_ASSIGNED
WHATSAPP_HANDOFF_RESOLVED
WHATSAPP_OPT_OUT_RECORDED
WHATSAPP_BUSINESS_OPERATION_REQUESTED
WHATSAPP_BUSINESS_OPERATION_COMPLETED
WHATSAPP_BUSINESS_OPERATION_FAILED

No emitir eventos duplicados de canal, dominio y legacy para una misma acción.

⸻

56. EVENTOS DE NEGOCIO

Los eventos como:

ORDER_CREATED
QUOTE_CREATED
PAYMENT_RECEIVED
DELIVERY_ASSIGNED
LOYALTY_POINTS_EARNED

son propiedad de sus bounded contexts.

WhatsApp puede consumirlos para comunicar.

No debe volver a emitirlos como si fuera su dueño.

⸻

57. OBSERVABILIDAD

Implementar:

correlation_id
conversation_id
provider_message_id
operation_id
customer_id
branch_id
channel_number_id

Métricas:

messages_received
messages_sent
delivery_rate
read_rate
failure_rate
response_time
intent_resolution_rate
handoff_rate
conversion_rate
abandonment_rate
duplicate_rate
dead_letter_count
provider_latency
ERP_latency

⸻

58. HEALTH CHECKS

Crear:

provider connectivity
webhook configuration
secret availability
database
inbox worker
outbox worker
ERP API
template status
number status
queue depth

Estados:

HEALTHY
DEGRADED
UNHEALTHY
UNKNOWN

El endpoint no debe devolver secretos, rutas locales ni detalles sensibles.

⸻

59. RATE LIMITING

Crear:

InboundRateLimitPolicy
OutboundRateLimitPolicy
CustomerSpamPolicy

Ámbitos:

por identidad
por número
por IP
por cuenta
por plantilla

No bloquear clientes legítimos sin registrar motivo.

⸻

60. RETRIES

Configurar:

max_attempts
initial_delay
backoff_multiplier
maximum_delay
jitter
retryable_errors

No reintentar:

payload inválido
consentimiento revocado
número bloqueado
plantilla rechazada

⸻

61. DEAD LETTER

Crear:

WhatsAppDeadLetter

Debe registrar:

message_id
operation_id
failure_type
attempts
last_error
payload_reference
created_at
resolved_at
resolved_by
resolution

No perder mensajes fallidos.

⸻

62. MEDIA

Crear:

WhatsAppMediaReference

Tipos:

IMAGE
AUDIO
VIDEO
DOCUMENT
STICKER

Flujo:

provider media ID
    ↓
descarga segura
    ↓
validación MIME
    ↓
antivirus future hook
    ↓
almacenamiento
    ↓
referencia

No guardar archivos arbitrarios dentro de la DB.

⸻

63. SEGURIDAD DE ARCHIVOS

Validar:

MIME real
extensión
tamaño
tipo permitido
hash
nombre seguro

Bloquear:

ejecutables
scripts
macros
archivos con doble extensión
rutas relativas

⸻

64. LOCALIZACIÓN Y HORARIOS

Soportar:

locale
timezone
business hours
holiday schedules
branch schedules
agent schedules

Fuera de horario:

confirmar recepción
mostrar horario
permitir pedido programado
ofrecer handoff pendiente

No hardcodear horarios.

⸻

65. CONFIGURACIÓN

WhatsApp debe aparecer como módulo global operativo:

WhatsApp

La configuración técnica también debe estar accesible desde:

Configuración → Integraciones → WhatsApp

Separación:

Módulo WhatsApp:
    conversaciones, agentes, métricas, campañas operativas
Configuración:
    cuentas, números, secrets, webhooks,
    templates, health, routing

⸻

66. NAVEGACIÓN INTERNA

Resumen
Bandeja
Conversaciones
Pedidos
Cotizaciones
Pagos
Delivery
Clientes
Handoffs
Agentes
Plantillas
Campañas autorizadas
Números y sucursales
Errores y reintentos
Dead letter
Métricas
Auditoría
Configuración

Las páginas de Pedidos, Cotizaciones, Pagos y Delivery son proyecciones del canal, no fuentes de verdad de esos módulos.

⸻

67. KPI

Máximo seis:

Conversaciones abiertas
Mensajes pendientes
Tiempo medio de respuesta
Pedidos originados
Handoffs pendientes
Fallos de envío

Otros:

tasa de entrega
tasa de lectura
conversión
abandono
duplicados
dead letters

La UI no calcula KPI.

⸻

68. UI/UX ENTERPRISE

Usar:

PageHeader
ModuleSidebar
KPIBar
DashboardGrid
ChartCard
FilterBar
StandardTable
StandardDialog
ConversationList
ConversationThread
MessageComposer
StatusBadge
AgentBadge
SlaBadge
SearchInput
EntitySearchInput

No usar:

QTabWidget como navegación principal
QGroupBox estilizados
QFrame como cards
QTableWidget
QSS local
setStyleSheet
colores hardcodeados
emojis

⸻

69. COMPOSER DE MENSAJES

Debe soportar:

texto
plantilla
imagen
documento
ubicación
respuesta rápida
nota interna
handoff

Debe validar:

ventana de conversación
consentimiento
tipo de plantilla
permisos
número emisor

⸻

70. PERMISOS

Acceso

WHATSAPP_ACCESS
WHATSAPP_DASHBOARD_VIEW
WHATSAPP_CONVERSATIONS_VIEW
WHATSAPP_AUDIT_VIEW

Conversaciones

WHATSAPP_CONVERSATION_REPLY
WHATSAPP_CONVERSATION_ASSIGN
WHATSAPP_CONVERSATION_CLOSE
WHATSAPP_CONVERSATION_REOPEN
WHATSAPP_CONVERSATION_BLOCK
WHATSAPP_INTERNAL_NOTE_CREATE

Handoff

WHATSAPP_HANDOFF_REQUEST
WHATSAPP_HANDOFF_ACCEPT
WHATSAPP_HANDOFF_REASSIGN
WHATSAPP_HANDOFF_RESOLVE
WHATSAPP_QUEUE_MANAGE

Plantillas

WHATSAPP_TEMPLATE_VIEW
WHATSAPP_TEMPLATE_CREATE
WHATSAPP_TEMPLATE_EDIT
WHATSAPP_TEMPLATE_SUBMIT
WHATSAPP_TEMPLATE_ACTIVATE
WHATSAPP_TEMPLATE_ARCHIVE

Configuración

WHATSAPP_ACCOUNT_VIEW
WHATSAPP_ACCOUNT_MANAGE
WHATSAPP_NUMBER_VIEW
WHATSAPP_NUMBER_MANAGE
WHATSAPP_WEBHOOK_MANAGE
WHATSAPP_SECRET_MANAGE
WHATSAPP_ROUTING_MANAGE
WHATSAPP_HEALTH_VIEW

Mensajes

WHATSAPP_MESSAGE_SEND
WHATSAPP_MESSAGE_RETRY
WHATSAPP_MESSAGE_CANCEL
WHATSAPP_DEAD_LETTER_VIEW
WHATSAPP_DEAD_LETTER_RESOLVE

⸻

71. SEGREGACIÓN

Separar:

Agente
Supervisor
Administrador del canal
Administrador técnico
Administrador de secretos
Administrador de plantillas
Auditor

Reglas:

- quien administra secretos no atiende conversaciones;
- quien crea plantilla no la activa solo cuando sea sensible;
- quien reasigna conversaciones registra motivo;
- quien resuelve dead letter deja evidencia;
- quien bloquea identidad registra causa;
- quien accede a mensajes sensibles requiere permiso.

⸻

72. AUDITORÍA

Auditar:

recepción
envío
reintento
fallo
dedupe
clasificación
cambio de estado
creación de pedido
solicitud de pago
handoff
asignación
respuesta humana
cierre
bloqueo
opt-out
plantilla
configuración
secreto
número
webhook
dead letter

Guardar:

user_id o service_identity_id
operation_id
conversation_id
message_id
action
before
after
reason
branch_id
channel_number_id
occurred_at
correlation_id

No incluir secretos o contenido sensible completo.

⸻

73. MANEJO DE ERRORES

Crear:

WhatsAppAccountNotFoundError
WhatsAppNumberNotFoundError
WhatsAppNumberInactiveError
WebhookSignatureInvalidError
WebhookReplayDetectedError
MessageDuplicateError
ConversationNotFoundError
ConversationStateInvalidError
IntentResolutionFailedError
BusinessOperationDuplicateError
BusinessOperationFailedError
ProviderUnavailableError
ProviderRateLimitError
TemplateNotApprovedError
ConversationWindowClosedError
ConsentRequiredError
OptOutActiveError
HandoffUnavailableError
AgentNotAvailableError
ERPServiceUnavailableError
SecretUnavailableError
MediaValidationError
PermissionDeniedError

Prohibido:

except Exception:
    pass

⸻

74. ELIMINACIÓN TOTAL DE LEGACY

Eliminar:

core/services/whatsapp_service.py
services/whatsapp_service.py
integrations/whatsapp_service.py
ERPBridge como acceso de negocio
BusinessOrchestrator con reglas ERP
sender legacy
webhook legacy
whatsapp_queue legacy
wa_event_log duplicado
events legacy
normalizadores duplicados
cálculo de precio en flows
cálculo de total en flows
cálculo de anticipo en flows
validación de stock en flows
programación de delivery en bridge
escrituras SQLite del ERP
fallbacks a SQLite
X-Internal-Key hardcodeada
sys.path manipulation
imports ambiguos
routers duplicados
migraciones legacy

No eliminar hasta confirmar cero consumidores.

⸻

75. CONSOLIDACIÓN DE TABLAS

Auditar:

conversations
message_log
whatsapp_queue
wa_event_log
notification_inbox
whatsapp_numbers
whatsapp_templates
handoff

Clasificar:

REUSE
ALTER
MERGE
REPLACE
DROP

Debe quedar una fuente canónica para:

conversaciones
mensajes
deliveries
inbox
outbox
idempotencia
handoff
cuentas
números
templates
auditoría

⸻

76. FASES DE IMPLEMENTACIÓN

WA-0 — Auditoría

1. Inventariar todo WhatsApp.
2. Inventariar webhooks.
3. Inventariar senders.
4. Inventariar flows.
5. Inventariar SQL.
6. Inventariar eventos.
7. Inventariar secretos.
8. Inventariar tests.
9. Crear plan.

WA-1 — Seguridad

1. SecretStore.
2. Webhook signatures.
3. Internal HMAC.
4. Service identity.
5. Redaction.
6. Tests.

WA-2 — Dominio base

1. Accounts.
2. Numbers.
3. Identity.
4. Conversation.
5. Message.
6. Events.
7. Tests.

WA-3 — Esquema limpio

1. UUIDv7.
2. Constraints.
3. Inbox.
4. Outbox.
5. Idempotency.
6. Dead letter.
7. Tests.

WA-4 — Bootstrap

1. ApplicationFactory.
2. CompositionRoot.
3. Lifespan.
4. Health.
5. Tests.

WA-5 — Provider Gateway

1. Meta gateway.
2. Send.
3. Status.
4. Media.
5. Health.
6. Tests.

WA-6 — Webhook

1. Verification.
2. Signature.
3. Dedupe.
4. Inbox.
5. Async worker.
6. Tests.

WA-7 — Conversation Engine

1. State machine.
2. Context.
3. Timeout.
4. Reset.
5. Tests.

WA-8 — Intent Resolution

1. Interactive.
2. Expected state.
3. Rules.
4. Classifier.
5. LLM fallback.
6. Tests.

WA-9 — ERP Contracts

1. Customers.
2. Catalog.
3. Pricing.
4. Inventory.
5. Orders.
6. Quotes.
7. Payments.
8. Delivery.
9. Loyalty.
10. Tests.

WA-10 — Pedidos

1. Draft.
2. Product selection.
3. Quantity.
4. Delivery method.
5. Confirmation.
6. Idempotency.
7. Tests.

WA-11 — Cotizaciones

1. Capture.
2. Create.
3. Accept.
4. Reject.
5. Convert.
6. Tests.

WA-12 — Pagos

1. Link.
2. Status.
3. Confirmation.
4. Duplicate webhook.
5. Tests.

WA-13 — Delivery

1. Address.
2. Zone.
3. Fee.
4. Tracking.
5. Weight adjustment.
6. Tests.

WA-14 — Clientes y consentimiento

1. Identity resolution.
2. Registration.
3. Consent.
4. Opt-out.
5. Tests.

WA-15 — Fidelidad

1. Summary.
2. Digital card.
3. Coupons.
4. Sweepstakes.
5. Tests.

WA-16 — Handoff

1. Requests.
2. Queues.
3. Agents.
4. Assignment.
5. SLA.
6. Tests.

WA-17 — Outbound Messaging

1. Templates.
2. Routing.
3. Queue.
4. Retry.
5. Dead letter.
6. Tests.

WA-18 — Notificaciones

1. Orders.
2. Delivery.
3. Payments.
4. Loyalty.
5. Internal alerts.
6. Tests.

WA-19 — UI

1. Sidebar.
2. Inbox.
3. Thread.
4. Composer.
5. Handoff.
6. Metrics.
7. Tests.

WA-20 — Observabilidad

1. Metrics.
2. Logs.
3. Correlation.
4. Health.
5. Dashboards.
6. Tests.

WA-21 — Eliminación de legacy

1. Quitar bridge.
2. Quitar SQL.
3. Quitar webhooks duplicados.
4. Quitar senders duplicados.
5. Quitar eventos duplicados.
6. Quitar rutas.
7. Quitar imports.
8. Vaciar allowlist.
9. Reporte.

WA-22 — Validación final

Ejecutar:

tests unitarios
tests integración
tests e2e
tests arquitectura
tests seguridad
tests webhook
tests idempotencia
tests provider
tests handoff
tests consentimientos
secret scanning
bootstrap limpio

⸻

77. TESTS OBLIGATORIOS

Arquitectura

WhatsApp no escribe tablas ERP
WhatsApp no importa repositories ERP
flows no calculan negocio
webhook no ejecuta negocio
UI no accede DB
un solo webhook
un solo sender
una sola outbox

Webhook

verify
firma válida
firma inválida
replay
duplicado
status event
group ignored
respuesta rápida

Idempotencia

mismo message_id
distinto message_id misma acción
pedido repetido
cotización repetida
pago repetido
delivery repetido

Conversación

inicio
estado esperado
cancelación
timeout
reset
ambigüedad
handoff

Pedidos

producto
cantidad
peso
sucursal
pickup
delivery
confirmación
cancelación

Seguridad

secretos fuera de código
logs sanitizados
HMAC
nonce
timestamp
service identity

Handoff

solicitud
asignación
reasignación
SLA
resolución
sin agentes

Consentimiento

marketing permitido
marketing rechazado
opt-out
re-consentimiento
mensaje transaccional

⸻

78. GUARDRAILS

Crear:

tests/architecture/test_whatsapp_has_single_webhook.py
tests/architecture/test_whatsapp_has_single_sender.py
tests/architecture/test_whatsapp_has_single_outbox.py
tests/architecture/test_whatsapp_does_not_write_erp_tables.py
tests/architecture/test_whatsapp_flows_have_no_business_calculations.py
tests/architecture/test_whatsapp_webhook_has_no_business_logic.py
tests/architecture/test_whatsapp_does_not_import_erp_repositories.py
tests/architecture/test_whatsapp_uses_erp_contracts.py
tests/architecture/test_whatsapp_uses_uuidv7.py
tests/architecture/test_whatsapp_has_business_idempotency.py
tests/architecture/test_whatsapp_phone_normalization_is_canonical.py
tests/architecture/test_whatsapp_secrets_use_secret_store.py
tests/architecture/test_whatsapp_logs_redact_secrets.py
tests/architecture/test_whatsapp_main_is_minimal.py
tests/architecture/test_whatsapp_has_no_sys_path_hacks.py
tests/architecture/test_whatsapp_templates_are_not_hardcoded.py
tests/architecture/test_whatsapp_ai_cannot_execute_commands.py
tests/architecture/test_whatsapp_consent_is_enforced.py
tests/architecture/test_whatsapp_has_no_legacy_imports.py
tests/architecture/test_whatsapp_legacy_allowlist_is_empty.py

⸻

79. DEFINICIÓN DE TERMINADO

[ ] Existe módulo WhatsApp global.
[ ] Existe microservicio canónico.
[ ] main.py es mínimo.
[ ] Existe CompositionRoot.
[ ] No existen sys.path hacks.
[ ] Existe un solo webhook.
[ ] Existe un solo sender.
[ ] Existe un solo ProviderGateway.
[ ] Existe un solo inbox.
[ ] Existe un solo outbox.
[ ] Existe dead letter.
[ ] Existe idempotencia técnica.
[ ] Existe idempotencia de negocio.
[ ] Todos los IDs usan UUIDv7.
[ ] Existen cuentas.
[ ] Existen números.
[ ] Existe multi-sucursal.
[ ] Existe número global.
[ ] Existe identidad WhatsApp.
[ ] Existe normalización E.164.
[ ] Existen conversaciones.
[ ] Existe state machine.
[ ] Existen mensajes.
[ ] Existen estados de entrega.
[ ] Existe retención de contenido.
[ ] Existe firma de webhook.
[ ] Existe replay protection.
[ ] Existe procesamiento asíncrono.
[ ] Existe ProviderGateway Meta.
[ ] Existen plantillas versionadas.
[ ] Existe resolución por capas.
[ ] El LLM no ejecuta negocio.
[ ] Existen contratos ERP.
[ ] Pedidos pertenece a Orders.
[ ] Cotizaciones pertenece a Quotes.
[ ] Pagos pertenece a Payments.
[ ] Delivery pertenece a Delivery.
[ ] Clientes pertenece a Customers.
[ ] Fidelidad pertenece a Loyalty.
[ ] WhatsApp no escribe tablas ERP.
[ ] No existe ERPBridge con negocio.
[ ] No existen cálculos de precio en flows.
[ ] No existen cálculos de anticipo en flows.
[ ] No existe validación de stock en flows.
[ ] Existe human handoff.
[ ] Existen agentes.
[ ] Existen colas.
[ ] Existe SLA.
[ ] Existen consentimientos.
[ ] Existe opt-out.
[ ] Existen notificaciones transaccionales.
[ ] Existen alertas internas.
[ ] Existe HMAC interno.
[ ] Existe ServiceIdentity.
[ ] Existe SecretStore.
[ ] No existen secretos en código.
[ ] Existen métricas.
[ ] Existen health checks.
[ ] Existe rate limiting.
[ ] Existen retries.
[ ] Existe auditoría.
[ ] Existen permisos granulares.
[ ] Existe segregación.
[ ] UI usa Design System.
[ ] No existe SQL en UI.
[ ] No existen webhooks legacy.
[ ] No existen senders legacy.
[ ] No existen eventos duplicados.
[ ] No existen rutas legacy.
[ ] No existen imports legacy.
[ ] Allowlist vacía.
[ ] Bootstrap limpio funciona.
[ ] Todos los tests pasan.

⸻

80. REPORTE FINAL

Entregar:

1. Webhooks encontrados.
2. Senders encontrados.
3. Colas encontradas.
4. Bridges encontrados.
5. SQL directo encontrado.
6. Flows encontrados.
7. Reglas de negocio filtradas al canal.
8. Eventos encontrados.
9. Secretos o credenciales encontrados.
10. Normalizadores encontrados.
11. Tablas encontradas.
12. Tests existentes.
13. Reglas válidas preservadas.
14. Código reutilizado.
15. Código movido.
16. Código reescrito.
17. Código eliminado.
18. Tablas consolidadas.
19. Tablas eliminadas.
20. Entidades creadas.
21. UseCases creados.
22. QueryServices creados.
23. Gateways creados.
24. Contratos ERP creados.
25. Páginas creadas.
26. Permisos creados.
27. Tests creados.
28. Tests ejecutados.
29. Secret scanning.
30. Allowlist inicial.
31. Allowlist final.
32. Bootstrap limpio.
33. Riesgos pendientes.

Tabla obligatoria:

| Elemento anterior | Destino canónico | Acción | Consumidores restantes |
|-------------------|------------------|--------|------------------------|
| webhook legacy | WebhookProcessor | DELETE | 0 |
| sender legacy | ProviderGateway | DELETE | 0 |
| whatsapp_queue | WhatsAppOutbox | DELETE | 0 |
| wa_event_log duplicado | eventos canónicos | DELETE | 0 |
| ERPBridge writes | ERP API clients | DELETE | 0 |
| BusinessOrchestrator | UseCases ERP | DELETE | 0 |
| precio en flow | PricingQuery | DELETE | 0 |
| stock en flow | AvailabilityQuery | DELETE | 0 |
| anticipo en flow | Payments UseCase | DELETE | 0 |
| delivery en bridge | Delivery UseCase | DELETE | 0 |
| normalización dispersa | PhoneNumberNormalizer | DELETE | 0 |
| X-Internal-Key | HMAC service auth | DELETE | 0 |
| token en código | SecretStore | DELETE | 0 |
| sys.path hacks | paquetes explícitos | DELETE | 0 |
| idempotencia solo mensaje | BusinessOperationIdempotency | DELETE | 0 |
| UI legacy | WhatsApp enterprise UI | DELETE | 0 |

⸻

81. REGLA FINAL

Un solo microservicio.
Un solo webhook.
Un solo sender.
Un solo inbox.
Un solo outbox.
Un solo registro de conversaciones.
Una sola normalización de teléfonos.
Una sola resolución de intención.
Una sola integración por bounded context.
Una sola arquitectura de handoff.
Una sola fuente de auditoría.

WhatsApp recibe y comunica.

Customers administra identidad.

Catalog administra productos.

Pricing administra precios.

Inventory administra disponibilidad.

Orders administra pedidos.

Quotes administra cotizaciones.

Payments administra pagos.

Delivery administra entregas.

Loyalty administra puntos, tarjetas y beneficios.

Notification Management decide el canal.

Secret Store protege credenciales.

El webhook valida y persiste.

Los workers procesan.

Los UseCases ejecutan.

La idempotencia evita operaciones duplicadas.

La auditoría demuestra quién dijo qué, qué intención se resolvió, qué operación se solicitó, cuál fue el resultado y qué mensaje se entregó.