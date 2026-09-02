# Settings / Device / Document Output / Customer Display — Legacy Inventory (SET-0)

Auditoría de todo el código, tablas y patrones legacy relacionados con
Configuración, Dispositivos, Documentos/Impresión, Etiquetas, Pantallas del
Cliente e Integraciones, previo a la construcción de los bounded contexts
canónicos `backend/domain/settings/`, `backend/domain/device_management/`,
`backend/domain/document_output/` y `backend/domain/customer_display/`
definidos en el prompt maestro.

Solo lectura. Ningún archivo de aplicación fue modificado durante esta
auditoría. Complementa (y en varios puntos corrige/actualiza)
`docs/refactor/modules/configuracion.md`, cuyo archivo tiene **marcadores de
conflicto de git sin resolver** (líneas 242-481: `<<<<<<< HEAD` /
`=======` / `>>>>>>> claude/intelligent-clarke-uq1ck7`) y por tanto no debe
tratarse como fuente única de verdad hasta resolverse por separado.

Raíz de código real para todas las rutas: `pos_spj_v13.4/pos_spj_v13.4/`
(carpeta anidada).

---

## 0. Resumen ejecutivo — lo más importante

1. **Cero uso de `QSettings` en todo el repo.** Todo — incluidas preferencias
   de UI puramente locales (tema) — ya vive en SQLite vía la tabla genérica
   `configuraciones`. Buena noticia: no hay una capa de preferencias locales
   que preservar aparte; mala noticia: preferencias de UI y configuración de
   negocio comparten hoy la misma tabla sin diferenciación de sensibilidad/
   ámbito.
2. **`configuraciones` está definida dos veces con esquemas incompatibles**
   dentro de la misma función (`migrations/m000_base_schema.py:128-147`,
   `_create_core_config`). Ambas usan `CREATE TABLE IF NOT EXISTS`, así que
   solo la primera definición (PK `clave`) llega a crearse; la segunda
   (PK `id`, `categoria`) es código muerto que no falla nunca — drift
   silencioso que no debe sobrevivir al rebuild.
3. **Secretos en texto plano** en múltiples lugares no conectados al
   `SecretStoreGateway` ya construido en `backend/security/secrets/`:
   - `email_config.smtp_pass` (`migrations/m000_base_schema.py:1367-1376`),
     leído sin cifrar en `core/services/reporte_email_service.py:85`.
   - `whatsapp_numeros.meta_token/twilio_token` y `configuraciones.wa_meta_token`
     (columnas TEXT planas), usados por `core/services/whatsapp_service.py`,
     `whatsapp_service/config/settings.py::_read_erp_config()`.
   - Ninguno de estos usa `backend/security/secrets/secret_store_gateway.py`
     (`SecretStoreGateway`, `EncryptedLocalSecretStore`,
     `WindowsCredentialManagerSecretStore`) pese a que esa infraestructura ya
     existe, lista para usarse, y sin ningún consumidor real todavía.
4. **Violación REGLA CERO ya presente en una migración**: `migrations/standalone/096_configuration_services_schema.py`
   inserta `INSERT INTO config_programa_fidelidad (id, ...) VALUES (1, ...)`
   con literal entero `1` en una columna `TEXT PRIMARY KEY`.
5. **Credenciales por defecto hardcodeadas** (`admin`/`admin123`,
   `demo`/`demo`, SHA-256 sin sal) en `migrations/m000_base_schema.py` (~línea
   3200) y `migrations/standalone/047_v13_schema.py:274-285`. No explotable
   (rechazado por `verify_password`, que exige bcrypt) pero es basura de
   arranque que debe eliminarse en el rebuild.
6. **Dos modelos de permisos coexistiendo**: el modelo plano legacy
   `modulo/accion` (`rol_permisos`/`permisos`, acciones
   `ver/crear/editar/eliminar/exportar`, módulo `'CONFIGURACION'`,
   `migrations/m000_base_schema.py:3237-3261`) vs. el catálogo moderno de
   códigos punteados `MODULO.accion` en `core/security/permission_catalog.py`.
   **Configuración nunca recibió una clave unificada** en el catálogo nuevo —
   solo existen tres stubs (`CONFIG_HARDWARE: ["ver"]`, `CONFIG_MODULOS: ["ver"]`,
   `CONFIG_SEGURIDAD: ["ver","editar"]`, líneas 340-342) mientras que todo
   bounded context ya migrado (POS, CAJA, INVENTARIO, COMPRAS, PRODUCCION,
   CLIENTES, CRM, FINANZAS, PRODUCTOS) tiene acciones granulares completas.
7. **`hardware_config` tiene PK en `tipo` solo** — un renglón por *tipo* de
   dispositivo en todo el sistema, pese a tener columna `sucursal_id`. Esto
   bloquea estructuralmente cualquier configuración real por
   sucursal/estación y debe corregirse en el esquema nuevo.
8. **Tres pipelines de etiquetas paralelos e independientes**
   (`modulos/etiquetas.py`, `hardware/impresora_etiquetas.py`,
   `labels/generador_etiquetas.py`) más un cuarto moderno
   (`backend/infrastructure/printing/package_label_renderer.py`).
9. **Dos constructores de tickets de delivery independientes**
   (`delivery/ticket_delivery.py` vs `core/services/ticket_printer_service.py`),
   ambos con SQL embebido en la clase que construye el ticket; el segundo
   además construye el texto por concatenación de f-strings sin motor de
   plantillas.
10. **UI accediendo hardware directamente**: `modulos/etiquetas.py`
    (`ModuloEtiquetas._send_to_printer`, un `QWidget` haciendo
    `socket.socket`/`serial.Serial`/`win32print` directo),
    `hardware/cajon_dinero.py`, `hardware/lector_qr.py` (ambos `QObject` con
    I/O serial propio).
11. **Generación de folios por `MAX(...)+1`** en
    `backend/infrastructure/db/repositories/procurement/support_repositories.py:126-135`
    (`next_number`), con seguridad dependiente solo de `UNIQUE(document_number)`
    y no de un contador atómico — riesgo de condición de carrera si el
    caller no reintenta explícitamente ante conflicto.
12. **Feature flags: mecanismo real ya existe** (`core/services/feature_flag_service.py`,
    `repositories/feature_flag_repository.py`) pero con drift de esquema: la
    rama "nuevo esquema" del repositorio (`feature_name`/`enabled`/`branch_id`)
    no tiene migración correspondiente en `m000_base_schema.py` (que solo crea
    el esquema legacy `clave`/`activo`) — confirmar si es código aspiracional
    muerto antes de usarlo como base.
13. **Customer Display es terreno genuinamente verde**: el único artefacto
    existente es `backend/application/sales/queries/customer_display_query_service.py`
    (`CustomerDisplayQueryService`), un query service puro sin consumidor de
    hardware/UI real — su propio docstring documenta que no existe ningún
    consumidor de segunda pantalla en el repo. Buen punto de partida, sin
    legacy que migrar.
14. **`>=20` clases relacionadas con WhatsApp** más allá de los 3 shims
    documentados en `CLAUDE.md` — necesitan mapeo de deduplicación cuidadoso,
    no un simple "preservar 3 archivos" (ver §6).
15. **Prior art ya construido y reutilizable**: el bounded context de Caja
    (`CASH-5_configuration.md`, `CASH-6_devices.md`, `CASH-18_hardware.md`,
    `CASH-24_printing.md`, esquema `migrations/standalone/175_cash_register_bounded_context_schema.py`
    y `176_cash_register_configuration_schema.py`) ya implementa exactamente
    el patrón que este prompt pide a nivel global: configuración tipada,
    jerárquica (`SYSTEM→COMPANY→BRANCH→REGISTER→USER`), versionada, con
    Protocols de hardware (`CashDrawerGateway`, `ReceiptPrinterGateway`,
    `PaymentTerminalGateway`) y un pipeline dual HTML/ESC-POS
    (`cash_register_renderers.py`). Este debe ser el molde de referencia para
    generalizar, no reinventarse desde cero.

---

## 1. Configuration Governance — archivos y símbolos legacy

| Archivo | Rol | Clasificación preliminar |
|---|---|---|
| `modulos/configuracion.py` | Monolito PyQt legacy, única UI viva hoy (no existe `frontend/desktop/modules/settings/`) | REWRITE |
| `modulos/config_hardware.py` | Pantalla satélite de hardware, consulta `container.db` directo | REWRITE |
| `modulos/config_interfaz.py` | Pantalla satélite de tema/UI | REWRITE |
| `modulos/config_modules.py` | Toggle de módulos/feature flags por sucursal | REWRITE |
| `core/services/configuration_settings_service.py` | 13 clases: `SystemSettingsService`, `ModuleSettingsService`, `CompanyProfileService`, `SettingsApplicationService`, `EmailSettingsService`, `PaymentProviderSettingsService`, `ClosingPeriodService`, `HappyHourSettingsService`, `PermissionEventPublisher`, `UserManagementService`, `RoleManagementService`, `PermissionQueryService`, `ModuleAccessService`, `SettingsModuleServices` | MOVE (lógica reutilizable) / REWRITE (estructura) |
| `core/services/config_service.py` (`ConfigService`) | Wrapper k/v genérico más antiguo, coexiste con el anterior | DELETE tras migrar consumidores |
| `core/module_config.py` (`ModuleConfig`, `DEFAULT_TOGGLES`) | Defaults de toggles | MOVE a `ConfigurationDefinition` seeds |
| `repositories/config_repository.py` (`ConfigRepository`) | Frontera SQL genérica `section/name/value` | REWRITE (reemplazar por `ConfigurationValue` repository tipado) |
| `core/repositories/hardware_config_repository.py` | Acceso a `hardware_config` | REWRITE hacia `device_management` |
| `core/repositories/whatsapp_config_repository.py` | Acceso a `whatsapp_numeros`/`configuraciones` WA keys | REWRITE hacia integración + secretos |
| `backend/application/queries/hardware_settings_query_service.py`, `ticket_settings_query_service.py`, `module_settings_query_service.py` | QueryServices ya en capa de aplicación moderna | REUSE como referencia de patrón |
| `backend/application/dto/configuracion_dtos.py`, `backend/application/commands/settings_commands.py` | DTO/commands ya modernos | REUSE parcial |
| `backend/application/use_cases/save_hardware_config_use_case.py`, `save_smtp_settings_use_case.py`, `save_payment_provider_settings_use_case.py` | Use cases ya modernos | REUSE parcial, adaptar a `ConfigurationValue` versionado |
| `ui/themes/theme_engine.py:91-106` | `load_saved_theme()`/`_persist_theme()` — SQL crudo contra `configuraciones` desde módulo casi-UI | REWRITE (debe pasar por QueryService) |

No existe `frontend/desktop/modules/settings/` ni `.../configuracion/`.
Nótese que varios bounded contexts ya migrados tienen su **propia**
`settings_page.py` local (`hr/pages/settings_page.py`,
`inventory/pages/settings_page.py`, `transfers/pages/settings_page.py`,
`finance/pages/finance_settings_page.py`) — son configuración *propia de ese
contexto* (ya fuera del alcance de Configuración central, consistente con
`configuracion_scope.json`) y deben permanecer donde están.

---

## 2. `QSettings` — inventario

Ningún resultado (`grep -rln QSettings` sobre todo el árbol, excluyendo
`.venv`): confirmado vacío. No hay nada que clasificar en esta categoría.

---

## 3. Tablas legacy relacionadas con configuración/hardware/documentos

| Tabla | Definida en | Notas / clasificación |
|---|---|---|
| `configuraciones` (x2, solo la 1a gana) | `m000_base_schema.py:128-147` | REPLACE por `configuration_definition` + `configuration_value` |
| `feature_flags` | `m000_base_schema.py` (~L150) | REPLACE por `FeatureFlag`/`FeatureFlagRule` tipados; confirmar si esquema "nuevo" en el repository es aspiracional |
| `module_toggles` | `migrations/standalone/096_configuration_services_schema.py:44-51` | MERGE con `feature_flags` en el modelo nuevo |
| `system_constants` | `m000_base_schema.py` | MERGE en `configuration_definition` (scope GLOBAL) |
| `hardware_config` | `m000_base_schema.py:169-179`, re-canonizada en `m050_hardware_config_canonical.py` | REPLACE — PK en `tipo` solo, no soporta multi-sucursal/estación (ver §0.7) |
| `sucursales` | `m000_base_schema.py` | REUSE como base de `BranchProfile`, ampliar columnas |
| `email_config` | `m000_base_schema.py` | REPLACE — PK singleton `id DEFAULT 1` (int en TEXT PK), secreto en plano |
| `email_schedule` | `m000_base_schema.py` | MOVE a `notifications`/integraciones |
| `config_diseno_tarjetas` | `m000_base_schema.py` (~L?) | Fuera de alcance — pertenece a Fidelidad |
| `ticket_layouts` | `m000_base_schema.py:~3147` | REPLACE por `DocumentTemplate`/`DocumentTemplateVersion` |
| `print_job_log` | `migrations/standalone/056_print_job_log.py:9-24` | REPLACE por `PrintJob` canónico (patrón ya mejor resuelto en `cash_print_jobs`) |
| `cash_print_jobs`, `cash_print_audit`, `cash_sync_devices`, `cash_sync_envelopes` | `migrations/standalone/175_cash_register_bounded_context_schema.py:192-230` | REUSE COMO MOLDE — CHECK constraints, `original_print_id` con `reprint_reason` obligatorio, `local_sequence`/`last_synced_sequence` para offline |
| `cash_settings`, `cash_denominations`, `cash_payment_methods`, `cash_operation_limits`, `cash_movement_reasons`, `cash_alert_rules`, `cash_difference_policies`, `cash_whatsapp_recipients`, `cash_permission_profiles(_items)`, `cash_in_app_recipients`, `cash_email_recipients`, `cash_notification_jobs(_attempts)`, `cash_in_app_alerts` | `migrations/standalone/176_cash_register_configuration_schema.py` | REUSE COMO MOLDE — único bounded context con modelo `SYSTEM→COMPANY→BRANCH→REGISTER→USER` tipado y versionado hoy |
| `logistics_print_jobs`, `logistics_container_labels` | `migrations/standalone/171_logistics_bounded_context_schema.py:69-78` | REUSE COMO MOLDE para `LabelTemplate`/`PrintJob` de etiquetas |
| `whatsapp_numeros` | schema nuevo (ver auditoría integraciones) | REWRITE — mover secretos a `SecretStoreGateway` |
| `usuarios`, `roles`, `permisos`, `roles_permisos`/`rol_permisos`, `usuarios_roles`, `usuario_permisos`, `usuario_sucursal_permisos`, `login_attempts`, `login_blocks` | `m000_base_schema.py::_create_auth` | Fuera de alcance directo de Settings (pertenece a Security/RBAC), pero `rol_permisos` seed con módulo `'CONFIGURACION'` debe migrar al catálogo punteado nuevo |

No existen tablas dedicadas `printer_config`, `scale_config`,
`label_templates` (fuera del molde de logistics), `webhooks`, `secrets`,
`integrations`, `devices`/`workstations` cross-cutting — todo esto debe
crearse desde cero siguiendo el molde de Caja/Logistics.

---

## 4. Hardware / Device Management — inventario

### 4.1 Acceso directo a hardware (sin gateway)

- `hardware/lector_qr.py:136` — `serial.Serial(...)` dentro de `LectorQRSerial` (`QObject`).
- `hardware/impresora_etiquetas.py:90` — `serial.Serial(...)` en `ImpresoraEtiquetas._imprimir_serial`.
- `hardware/cajon_dinero.py:62-63,92` — `python-escpos` (`Usb`, `Serial`, `Network`) + `serial.Serial` directo en `CajonDinero._abrir_serial` (`QObject`).
- `hardware/scale_reader.py:30` — `serial.Serial(...)` en `safe_serial_read` a nivel de módulo.
- `core/services/hardware_service.py:6-8,69,94` — se autodenomina "HAL" pero abre `serial.Serial` directo; es la capa de I/O, no una abstracción sobre ella.
- `modulos/etiquetas.py:559-603` — `ModuloEtiquetas._send_to_printer()`, método de un `QWidget`, hace `socket.socket`, `serial.Serial` y `win32print` **directo dentro de la UI**. Caso más claro de violación UI/infraestructura.

**Clasificación**: todo lo anterior → REWRITE hacia
`backend/infrastructure/hardware/*_gateway.py` con Protocols, siguiendo el
patrón ya existente en `backend/application/cash_register/hardware.py`.

### 4.2 Configuración de impresoras/básculas/lectores

- Centralizada en `hardware_config` (una fila por `tipo`, ver §0.7) —
  REPLACE con soporte real de ámbito (empresa/sucursal/estación).
- Config hardcodeada de UI (`modulos/config_hardware.py:26-30`, listas de
  puertos/baud rates) — REUSE como seed de opciones, no como config.
- Carga de config duplicada por clase: `CajonDinero.from_config`,
  `ImpresoraEtiquetas.from_config`, `HardwareService._safe_baud` — cada una
  reimplementa su propio parsing contra `hardware_config` → REWRITE en un
  loader compartido (`ConfigurationResolutionService`).

### 4.3 Gateways/abstracciones ya existentes (prior art a reusar)

- `backend/application/cash_register/hardware.py` — Protocols
  `CashDrawerGateway`, `ReceiptPrinterGateway`, `PaymentTerminalGateway`,
  `CashHardwareGateway`, `StubCashHardwareGateway`, `CashHardwareError`.
- `backend/infrastructure/hardware/cash_register/drivers.py` —
  `EscPosDrawerDriver`, `ReceiptPrinterDriver`, `PaymentTerminalDriver`
  (envuelven `ByteTransport`/`PrinterTransport`/`AcquirerClient` — **sin
  implementación real de transporte todavía**, solo stubs).
- `backend/infrastructure/hardware/scale_gateway.py` — `ScaleGateway`,
  `StubScaleGateway`, `ManualScaleGateway` (idem, sin driver serial real).
- `backend/infrastructure/integrations/sales_scale_client.py` —
  `SalesScaleGateway`, delega deliberadamente al legacy
  `core/services/hardware_service.py::read_scale()` (documentado en su propio
  docstring); también documenta que el ya eliminado
  `modulos/ventas.py::leer_peso()` caía a un `serial.Serial` crudo en COM3
  cuando el HAL fallaba — evidencia histórica de bypass del abstraction.
- `backend/infrastructure/desktop/transfers_factory.py` (y hermanos
  `cash_register_factory.py`, `cash_operational_context.py`,
  `losses_factory.py`) son **composition roots de UI**, no factories de
  dispositivo. `cash_register_factory.py` sí conecta
  `StubCashHardwareGateway` — confirma que ningún driver real (no-stub) está
  conectado hoy en la capa moderna.

**Conclusión**: existe el esqueleto Protocol correcto; falta (a) unificar
en un registro cross-cutting de dispositivos con ámbito real, y (b)
implementar transportes reales que reemplacen a `hardware/*.py` legacy.

---

## 5. Document Output / Tickets / Etiquetas — inventario

### 5.1 Tickets de venta (POS) — ya modernizado, usar como molde

`frontend/desktop/modules/sales_pos/sales_pos_presenter.py:232` →
`core/ticket_escpos_renderer.py::TicketESCPOSRenderer.render()`, consume
`TicketPrintModel` (`core/tickets/ticket_print_model.py`) +
`TicketLayoutConfig` (`core/tickets/ticket_layout_config.py`). Renderer
real orientado a modelo de datos (constantes ESC/POS L18-48, tabla Code-39
manual). **Molde de referencia recomendado** para `document_output`.

### 5.2 Tickets de delivery — duplicación real

- `delivery/ticket_delivery.py::TicketDelivery` — `generar_ticket_cliente`,
  `generar_ticket_repartidor` (consulta `SELECT nombre FROM drivers WHERE id=?`
  inline), `imprimir_tickets`; carga pedido con SQL directo
  (`SELECT * FROM pedidos_whatsapp WHERE id=?`, `..._items WHERE pedido_id=?`).
- `core/services/ticket_printer_service.py::TicketPrinterService` —
  `print_customer_ticket`/`print_driver_ticket`/`print_both`, también con
  SQL embebido (`SELECT d.*, dr.nombre AS driver_nombre ...`), y construye
  el texto por **concatenación de f-strings** (`_build_customer_ticket`),
  sin motor de plantillas.

Ambas clases resuelven el mismo problema de forma independiente.
**Clasificación: DELETE ambas, REWRITE unificado** sobre
`DocumentTemplate`/`PrintJob` + DTO (`DeliveryTicketDataDTO`), sin SQL en
el renderer.

### 5.3 Reportes de caja X/Z — ejemplo limpio, no duplicado

`backend/infrastructure/printing/cash_register_renderers.py` —
`CashDocumentHtmlRenderer` y `CashDocumentEscPosRenderer`, ambos consumen
`CashPrintDocument` y emiten `CashPrintArtifact` (`format=HTML`/`ESC_POS`).
Dual pipeline **intencional** (preview vs. térmico), no duplicación
accidental — **reusar este patrón tal cual** para `document_output`.

### 5.4 Boletos de rifa/sorteo

`core/tickets/raffle_ticket_renderer.py` — cuarta familia de constructor
de tickets, independiente de las anteriores. REWRITE para integrarse al
mismo `DocumentTemplate`/`PrintJob` genérico (consistente con §32 del
prompt maestro: Sweepstakes registra la participación, Document Output solo
renderiza e imprime).

### 5.5 Etiquetas — tres pipelines paralelos

- `modulos/etiquetas.py` (746 líneas) — UI de diseño de etiquetas
  (`ModuloEtiquetas`) que además contiene su propio transporte de impresión
  (ver §4.1).
- `hardware/impresora_etiquetas.py` — driver independiente
  (`ImpresoraEtiquetas`: `imprimir`, `imprimir_etiqueta`, `imprimir_imagen`,
  `_imprimir_tcp/_imprimir_serial/_imprimir_usb/_imprimir_archivo`,
  `test_conexion`, `from_config`).
- `labels/generador_etiquetas.py::generar_lote` + `labels/diseno_etiquetas.py`
  — tercer generador/diseñador de lotes de etiquetas.
- `backend/infrastructure/printing/package_label_renderer.py` — cuarto,
  moderno, para etiquetas de paquete logístico (independiente de los tres
  anteriores).

**Clasificación**: consolidar los tres legacy → DELETE tras cubrir con
`LabelTemplate`/`LabelTemplateVersion` + `LabelRenderer` únicos; el moderno
`package_label_renderer.py` → REUSE como referencia de patrón de renderer.

### 5.6 Renderers HTML modernos (no duplicados, por diseño)

`backend/infrastructure/printing/receipt_document_renderer.py`,
`shipment_document_renderer.py`, `transfer_document_renderer.py`,
`picking_list_renderer.py` — pipeline HTML para logística/transferencias,
intencionalmente separado del ESC/POS térmico. REUSE.

### 5.7 `modulos/ticket_designer.py` (975 líneas)

UI standalone de diseño de layout de tickets. Relación con
`core/tickets/ticket_layout_config.py`/`ticket_layout_repository.py`
pendiente de confirmar en detalle (probablemente es la UI de esa config, no
un quinto renderer) — verificar en fase SET-11/12 antes de decidir
REWRITE vs REUSE de su lógica de layout.

### 5.8 Sin `QPrinter`/`QPrintDialog`

Confirmado: cero uso de la pipeline de impresión nativa de Qt en todo el
repo. Todo pasa por transporte custom (socket/serial/win32print RAW o bytes
ESC/POS). Esto simplifica el rebuild: no hay que desmontar una integración
Qt-print paralela, solo los transportes custom ya listados.

### 5.9 Numeración/folios

`backend/infrastructure/db/repositories/procurement/support_repositories.py:126-135`
(`next_number`) usa `SELECT MAX(document_number)... + 1` con
`UNIQUE(document_number)` como única red de seguridad (sin loop de retry
confirmado en esta pasada). REWRITE hacia `DocumentNumberSequence` con
reserva atómica e idempotente (§37 del prompt maestro). Otros usos de
`MAX(...)` encontrados (`inventory/sync_repositories.py:79`,
`cash_register/overview_query_service.py:172-176`) son agregados de solo
lectura — no aplican aquí.

---

## 6. Integraciones / WhatsApp / Feature Flags / Customer Display

### 6.1 WhatsApp — mapa de deduplicación (más allá de los 3 shims)

**Los 3 shims intencionales a preservar** (por `CLAUDE.md`, no tocar):
- `pos_spj_v13.4/services/whatsapp_service.py`
- `pos_spj_v13.4/integrations/whatsapp_service.py`
- `whatsapp_service/webhook/whatsapp.py`

**Implementación canónica actual** (a la que ambos shims re-exportan):
`core/services/whatsapp_service.py` (`WhatsAppConfig`, `WhatsAppService`,
`MessageQueue`, `WhatsAppWebhookServer`). `WhatsAppConfig` lee
`whatsapp_numeros` (columnas plaintext) con fallback a `configuraciones`
(`wa_meta_token`, `wa_verify_token`, ...).

**Clases WhatsApp adicionales, no-shim, activas, a inventariar/consolidar
durante el rebuild de integraciones** (no confundir con los 3 shims):
`core/services/whatsapp_credential_service.py`,
`core/services/whatsapp_admin_service.py`,
`core/services/delivery_whatsapp_service.py`,
`core/integrations/whatsapp_client.py::WhatsAppClient` (resolución de
credenciales en 4 niveles, incluida lectura directa de
`whatsapp_service/.env`),
`core/repositories/whatsapp_config_repository.py`,
`whatsapp_history_repository.py`, `whatsapp_metrics_repository.py`,
`core/delivery/infrastructure/whatsapp_delivery_notifier.py`,
`core/delivery/application/sync_whatsapp_orders.py`,
`core/events/handlers/whatsapp_notification_handler.py`,
`core/events/handlers/delivery_handler.py::DeliveryWhatsAppNotificationHandler`,
`notifications/whatsapp_channel.py::WhatsAppNotificationChannel`,
`modulos/whatsapp/whatsapp_module.py::ModuloWhatsApp` (UI que escribe
`whatsapp_numeros`),
`backend/infrastructure/integrations/cash_notification_senders.py`
(Protocol `WhatsAppClient` propio + `WhatsAppNotificationSender`),
`backend/application/transfers/notification_handlers/transfer_notification_handler.py::WhatsAppTransferNotifier`,
`backend/application/customers/queries/customer_whatsapp_summary_query.py`.

**Microservicio** `whatsapp_service/` (FastAPI standalone, ver estructura
completa en el reporte de auditoría de integraciones) — config vía
`.env`/`config/settings.py`, con `_read_erp_config()` sobreescribiendo desde
la misma tabla `configuraciones` plaintext.

**Clasificación**: preservar los 3 shims; MOVE la config de credenciales
(tokens Meta/Twilio/MercadoPago) a `SecretStoreGateway`; mantener
`ERP_API_URL`/`ERP_API_KEY`/webhooks como `IntegrationDefinition` +
`WebhookSubscription`; las ~13 clases restantes se mapean 1:1 a
handlers/gateways del nuevo `IntegrationManagement`, sin fusionarlas a la
fuerza (cada una tiene una responsabilidad distinta: crédito, admin,
delivery, historial, métricas).

### 6.2 Vulnerabilidad detectada — Webhook MercadoPago sin firma

`whatsapp_service/webhook/mercadopago.py:23-50` (`mp_notification`) **no
valida ninguna firma** — solo revisa `action == "payment.created"` y
refetch a la API de MP. `MP_WEBHOOK_SECRET` existe en config/`.env.example`
pero **nunca se lee**. Comparar con el webhook de WhatsApp
(`whatsapp_service/webhook/whatsapp.py`), que sí valida
`X-Hub-Signature-256` vía HMAC-SHA256 (`middleware/hmac_validator.py`).
**Clasificación: BLOCKED/riesgo de seguridad real** — debe resolverse como
parte de `WebhookSubscription`/`WebhookDeliveryAttempt` con firma
obligatoria, no como mejora opcional.

También: `whatsapp_service/router/notify_router.py` deja endpoints internos
sin protección (solo warning log) si no hay `X-Internal-Key` configurada en
modo dev — revisar antes de exponer en producción.

### 6.3 Feature flags

`core/services/feature_flag_service.py::FeatureFlagService` (cache en
memoria por sucursal, `is_enabled`, `set_flag`/`set_enabled`,
`require_feature`) + `repositories/feature_flag_repository.py`
(consciente de esquema dual legacy/nuevo, ver §0.12). Consumidores:
`modulos/config_modules.py` (pantalla "Configuración de Módulos",
`MODULOS_SISTEMA`), `modulos/delivery.py:1310-1312`
(`is_enabled('delivery_auto_asign', 1)`). Tests:
`tests/unit/test_feature_flag_service.py`. **Clasificación**: MOVE la
lógica de evaluación (útil), REWRITE el esquema/repository unificándolo con
`FeatureFlag`/`FeatureFlagRule` tipados del prompt maestro.

### 6.4 Customer Display — greenfield

Único artefacto: `backend/application/sales/queries/customer_display_query_service.py`
(`CustomerDisplayQueryService.current_state()`), proyección de solo lectura
por `SaleStatus`. DTOs en `backend/application/sales/dto.py`
(`CustomerDisplayLineDTO`, `CustomerDisplayStateDTO`). Tests:
`tests/unit/test_sales_hardware.py::TestCustomerDisplayQueryService`. Sin
hardware, sin UI, sin campañas/publicidad hoy. **Clasificación: REUSE como
base de diseño**, construir el resto (`CustomerDisplay`, `DisplayLayout`,
`ContentCampaign`, `AdvertisingSlot`) desde cero.

### 6.5 Secretos — infraestructura ya lista, sin conectar

`backend/security/secrets/` (untracked, ya construido en esta rama):
`secret_store_gateway.py` (Protocol `SecretStoreGateway`: `set_secret`,
`get_secret`, `describe`/`list_references` con `mask_secret()`,
`rotate_secret`, `delete_secret`), `encrypted_local_secret_store.py`
(Fernet + DPAPI en Windows), `windows_credential_manager_secret_store.py`
(vault nativo de Windows Credential Manager, namespace
`SPJ_ERP_POS/secret/*`), `errors.py`. **Clasificación: REUSE directo** —
es exactamente `SecretStoreGateway`/`SecretReference` que pide §46 del
prompt maestro. Falta únicamente conectar los consumidores (SMTP, WhatsApp,
MercadoPago, futuras integraciones).

### 6.6 Notificaciones

`notifications/service.py::DeliveryNotificationService` — enrutamiento por
string (`"all"|"sound"|"toast"|"whatsapp"|"desktop"|"silent"`), 4 canales
concretos ya wireados (`sound_channel.py`, `toast_channel.py`,
`desktop_channel.py`, `whatsapp_channel.py`). **No existe** una entidad
`NotificationConfig` persistida — severidad/destinatario/canal están
hardcodeados por call site. **Clasificación: REWRITE** hacia
`NotificationConfig` administrado por Settings, consumido por los módulos
vía eventos (§49 del prompt maestro).

---

## 7. Permisos legacy a migrar

- Cadena plana `'CONFIGURACION'` (no código punteado) en:
  `migrations/m000_base_schema.py:3240` (seed `rol_permisos`),
  `migrations/standalone/206_installation_provisioning_schema.py:32`,
  `frontend/desktop/shell/routing/route_registry_validator.py:26`,
  `tools/refactor_control/bootstrap_refactor_state.py:29/128/520`.
- `ADMIN_CONFIG`, `IMPRESION`: cero resultados en todo el repo (no requieren
  migración, no existen).
- `HARDWARE` (como string de módulo): solo en
  `route_registry_validator.py:27` y `bootstrap_refactor_state.py:53`, no
  registrado como clave del catálogo.
- Los permisos de Caja (`CASH_REGISTER_MANAGE`, `CASH_HARDWARE_DIAGNOSE`,
  `CASH_DRAWER_OPEN(_WITHOUT_SALE)`, `CASH_PRINT`, `CASH_TERMINAL_OPERATE`,
  etc.) viven fuera de `permission_catalog.py`, con su propia convención —
  **decisión de diseño pendiente**: ¿el nuevo `device_management` sigue la
  convención `CASH_*` o la convención punteada `MODULO.accion`? Recomendado:
  punteada, para converger con el resto de bounded contexts ya migrados
  (POS, CRM, FINANZAS, etc.), y migrar Caja después si se decide unificar.

---

## 8. Documentación de referencia ya existente (no duplicar)

- `docs/refactor/modules/configuracion.md` + `configuracion_scope.json` —
  auditoría previa, útil para el alcance (excluye explícitamente WhatsApp,
  diseño de tickets, fidelidad, turnos de RRHH del alcance de Configuración
  central) pero **con conflictos de merge sin resolver** — resolver por
  separado antes de citarlo como autoridad.
- `docs/refactor/application_bootstrap_audit.md` — documenta que las
  migraciones (incluidas todas las tablas de config) corren hasta 3 veces
  redundantes por arranque, cada vez con `sqlite3.connect()` crudo en vez
  del pool — relevante porque el nuevo `ConfigurationCache` debe invalidarse
  de forma consistente con este comportamiento de arranque.
- `docs/refactor/security_credentials_audit.md` — confirma bcrypt-12 como
  estándar real de hash, documenta el problema de `admin`/`admin123` y
  `demo`/`demo` (§0.5 arriba).
- `docs/refactor/container_dependency_inventory.md` — marca
  `modulos/config_hardware.py`/`config_modules.py` accediendo `container.db`
  crudo, y `modulos/configuracion.py` llamando
  `container.set_sucursal_activa()` directo desde una vista (debería ser un
  `BranchConfigurationUseCase`).
- `docs/refactor/modules/CASH-5_configuration.md`,
  `CASH-6_devices.md`, `CASH-18_hardware.md`, `CASH-24_printing.md`,
  `12_CASH-12_CONFIGURACION_ENTERPRISE_TIPADA.md` — prior art de referencia
  obligatoria, ver §0.15.

---

## 9. Próximo paso

Ver `docs/refactor/settings_refactor_execution_plan.md` para el plan de
fases SET-0 → SET-N derivado de este inventario.
