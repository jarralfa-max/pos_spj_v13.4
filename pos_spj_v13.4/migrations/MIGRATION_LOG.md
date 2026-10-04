# Migration Log — pos_spj v13.4

Registro de decisiones sobre migraciones. Toda fusión, renombre o conflicto debe
documentarse aquí antes del commit.

---

## 300/301/302 — Re-auditoría de Configuración (SET-26) — 2026-10-04

Hallazgos medidos sobre una copia de la base real; detalle en
`docs/refactor/SET-26_reauditoria.md`.

**300_logistics_qr_secret_to_secret_store.** `logistics.qr_signing_secret`
vivía en texto plano en `configuraciones` (§46). Ahora lo crea y lee el almacén
de secretos (`qr_signing_secret(secret_store)`). Sin etiquetas impresas la fila
se borra (el secreto se regenera en el almacén); con etiquetas, el valor se
copia al almacén antes de borrar y, si el almacén falla, la migración falla en
vez de invalidar etiquetas en silencio. Base real: 0 etiquetas.

**301_drop_dead_configuration_keys.** Retira 12 claves de `configuraciones`
sin ningún lector (`sync_*` ×5, `wa_escalacion_*` ×4, `wa_msg_*` ×2,
`app_version`), sembradas por 047/048/054 para subsistemas borrados. Las
siguen sembrando en una base nueva; la 301 corre después.

**302_seed_gerente_configuracion_permissions.** Al cerrar el hueco de
visibilidad del menú interno de Configuración, `gerente` quedaba viendo sólo
«General». Decisión del usuario: lectura de todas las secciones + gestión de
dispositivos, asignaciones y rutas de impresión. Solo `INSERT OR IGNORE`.

---

## 252_meat_processing_resources_schema — 2026-09-03

**Motivo:** PROC-19 (Recursos y capacidad) — cinco tablas nuevas sobre todo
el esquema previo de Procesamiento Cárnico: `production_areas` → `work_centers`
→ `production_stations` → `production_equipment` (§19, jerarquía de recursos
físicos) y `equipment_assignments` (gemelo estructural de
`operator_assignments`, PROC-7). `work_centers.capacity_per_hour`/`capacity_basis`
es donde ahora vive el número que `CapacityValidationService` (PROC-5)
siempre tomó como argumento del llamador, nunca hardcodeado.
**DDL:** `backend/infrastructure/db/schema/meat_processing_schema.py::create_meat_processing_resources_schema`.
**Impacto:** Solo aditivo. `processing_orders.production_area_id`/`.work_center_id`
y `process_executions`/`operator_assignments.work_center_id` (todas de
migraciones anteriores) siguen siendo referencias TEXT sin FK — SQLite no
permite añadir una FK a una columna existente sin reconstruir la tabla; la
integridad referencial contra estas tablas nuevas queda como responsabilidad
de capa de aplicación, documentado en `PROC-19_recursos.md`.

---

## 251_meat_processing_genealogy_schema — 2026-09-02

**Motivo:** PROC-18 (Trazabilidad) — una tabla nueva sobre todo el esquema
previo de Procesamiento Cárnico, sin tocar ninguna: `process_genealogy_links`
(§38), el enlace explícito upstream→downstream que hace consultable la
cadena "multinivel" entre órdenes distintas (dentro de una misma orden, el
`processing_order_id` compartido entre `material_consumptions` y
`process_outputs` ya basta).
**DDL:** `backend/infrastructure/db/schema/meat_processing_schema.py::create_meat_processing_genealogy_schema`.
**Impacto:** Solo aditivo. Sin FK en `upstream_entity_id`/`downstream_entity_id`
— son referencias polimórficas (pueden apuntar a `process_outputs`,
`material_consumptions`, etc.), imposible de expresar como FK de una sola tabla.

---

## 250_meat_processing_rework_schema — 2026-09-02

**Motivo:** PROC-17 (Reprocesos) — una tabla nueva: `rework_orders` (§29).
Nunca modifica la orden/output de origen (`source_output_id` es de solo
lectura); la ejecución real del reproceso ocurre en una `processing_orders`
nueva referenciada por `processing_order_id`, ejecutada por el mismo núcleo
productivo (§1) — no un motor de ejecución paralelo.
**DDL:** `backend/infrastructure/db/schema/meat_processing_schema.py::create_meat_processing_rework_schema`.
**Impacto:** Solo aditivo; FK a `process_outputs`/`processing_orders`.

---

## 249_meat_processing_packaging_schema — 2026-09-02

**Motivo:** PROC-13 (Empaque) — dos tablas nuevas sobre el esquema núcleo
(187) y el de preparación/ejecución (248), ninguno de los dos tocado:
`packaging_executions` (§25, registro inmutable — sin workflow/estado, igual
que `process_weighings`) y `production_labels` (§25, con `reprint_count` para
reimpresiones; "la impresión no determina el éxito productivo").
**DDL:** `backend/infrastructure/db/schema/meat_processing_schema.py::create_meat_processing_packaging_schema`.
**Impacto:** Solo aditivo; FKs internas (`processing_orders`, `process_outputs`,
`packaging_executions`).

---

## 248_meat_processing_preparation_execution_schema — 2026-09-02

**Motivo:** PROC-7 (Preparación) / PROC-8 (Ejecución) — cuatro tablas nuevas
sobre el esquema núcleo de Procesamiento Cárnico (migración 187, sin tocar):
`material_requirements` (§16, ciclo requerido→reservado→asignado→consumido),
`operator_assignments` (§32), `process_step_executions` (§20, sub-pasos de
una `ProcessExecution`) y `process_incidents` (§30).
**DDL:** `backend/infrastructure/db/schema/meat_processing_schema.py::create_meat_processing_preparation_execution_schema`
(función separada de `create_meat_processing_schema`, para no reabrir 187).
**Impacto:** Solo aditivo; FKs internas al propio bounded context
(`processing_orders`, `process_executions`) — sin FK cross-context, mismo
criterio que 187.

---

## 245_whatsapp_quote_drafts_schema — 2026-09-01

**Motivo:** WA-11 (Cotizaciones) del refactor enterprise del canal
WhatsApp. Agrega `whatsapp_quote_drafts`/`whatsapp_quote_draft_lines` —
equivalente de `whatsapp_order_drafts` (244) para cotizaciones, con un
ciclo de vida en dos pasos (capturar → `QuotesApiClient.create()` obtiene
folio/vigencia real del ERP → aceptar/rechazar más tarde) en vez de uno
solo como Pedidos (§37 vs §34). Reutiliza `create_whatsapp_schema()`.

---

## 244_whatsapp_order_drafts_schema — 2026-09-01

**Motivo:** WA-10 (Pedidos) del refactor enterprise del canal WhatsApp.
Agrega `whatsapp_order_drafts`/`whatsapp_order_draft_lines` al esquema de
la migración 243 — el carrito conversacional que WhatsApp arma ANTES de
pedirle a Orders (`OrdersApiClient`, WA-9) que cree el pedido canónico
contra `ventas`/`detalles_venta` — nunca el pedido en sí (§34 del prompt
maestro: "el draft conversacional no es el pedido canónico"). Reutiliza
`create_whatsapp_schema()` (mismo módulo de la 243), no crea uno nuevo.
Primer consumidor real de `whatsapp_business_operation_idempotency`
(creada en la 243, sin repositorio hasta ahora): la confirmación de un
`OrderDraft` usa un fingerprint determinístico
(`conversation_id`+contenido del carrito+método de entrega) para que dos
mensajes distintos del cliente ("confirmar" / "sí, confirmar") produzcan
el mismo pedido, no dos.

---

## 243_whatsapp_bounded_context_schema — 2026-09-01

**Motivo:** WA-3 (Esquema limpio) del refactor enterprise del canal
WhatsApp (`docs/refactor/whatsapp_legacy_inventory.md`,
`docs/refactor/WA-2_dominio_base.md`). Crea las tablas born-clean UUIDv7
para las entidades de dominio construidas en WA-2
(`whatsapp_service/domain/whatsapp/entities/`), más las capacidades de
infraestructura transversal que el prompt maestro exige para el canal
(inbox único, outbox único, idempotencia de negocio, dead letter):

- `whatsapp_business_accounts`, `whatsapp_provider_configurations`,
  `whatsapp_channel_numbers`, `whatsapp_identities`,
  `whatsapp_conversations` (+ `whatsapp_conversation_sessions`),
  `whatsapp_messages` (+ `whatsapp_message_deliveries`), `whatsapp_inbox`,
  `whatsapp_outbox`, `whatsapp_business_operation_idempotency`
  (`UNIQUE(operation_id)` + `UNIQUE(fingerprint)`), `whatsapp_dead_letter`.

**Ningún nombre canónico reemplaza tabla legacy alguna** — verificado por
grep antes de nombrarlas. `whatsapp_outbox` y
`whatsapp_business_operation_idempotency` son capacidades genuinamente
NUEVAS, no un rename: la auditoría WA-0
(`docs/refactor/whatsapp_schema_consolidation.md` §2) encontró que el
microservicio oficial envía mensajes de forma síncrona sin ningún outbox
persistido — un hueco real frente al requisito "single sender/single
outbox" del prompt maestro — y que la idempotencia de negocio existente
(`wa_business_idempotency`, creada en código con
`id INTEGER PRIMARY KEY AUTOINCREMENT`, no en una migración) tiene una
forma más angosta que el diseño `operation_id`/`aggregate_type`/
`fingerprint` que pide §19. Las demás tablas legacy (`whatsapp_numeros`,
`wa_event_log`, `wa_business_idempotency`, `whatsapp_queue`,
`pedidos_whatsapp`/`pedidos_whatsapp_items`, `conversations`/`message_log`
creadas en código por `whatsapp_service/state/conversation.py`) siguen
siendo la única ruta operativa real y no se tocaron — mismo patrón de
coexistencia que `customer_orders`/`orders_delivery_outbox` (migración
226) frente a `delivery_orders`/`pedidos_whatsapp*`.

Estados no se validan por `CHECK` de SQL — la capa de dominio
(`whatsapp_service/domain/whatsapp/enums.py` + entidades) es la única
fuente de verdad de transiciones válidas, mismo criterio ya establecido en
`sales_schema.py`/`loyalty_schema.py`/`orders_delivery_schema.py`. DDL en
`backend/infrastructure/db/schema/whatsapp_schema.py`
(`create_whatsapp_schema`), invocada solo desde esta migración.

**Tests**: `whatsapp_service/tests/test_whatsapp_schema.py` — round-trip
de las 12 tablas contra SQLite real, `UNIQUE(operation_id)`/
`UNIQUE(fingerprint)` en la tabla de idempotencia, y que ninguna colisiona
con una tabla legacy existente.

---

## 226_orders_delivery_bounded_context_schema — 2026-08-29

**Motivo:** ORD-3 (Esquema limpio) del refactor enterprise de Pedidos/Delivery
(`docs/refactor/orders_delivery_legacy_inventory.md`,
`docs/refactor/ORD-2_dominio_pedidos.md`). Crea las tablas born-clean UUIDv7
para el agregado de dominio construido en ORD-2
(`backend/domain/orders_delivery/entities.py`):

- `customer_orders` (`UNIQUE(operation_id)` + `UNIQUE(channel,
  external_order_reference)` per §18 deduplicación, `order_number UNIQUE`),
  `customer_order_lines`, `orders_delivery_outbox`.

**Nombres canónicos en inglés NO reemplazan las tablas legacy**
(`delivery_orders`, `delivery_items`, `delivery_order_history`,
`pedidos_whatsapp`, `pedidos_whatsapp_items`, `drivers`,
`delivery_outbox_events` — ver
`docs/refactor/orders_delivery_legacy_inventory.md` §1/§3) que siguen
sirviendo `core/services/delivery_service.py`/`core/delivery/` y la UI viva
`modulos/delivery.py`. Verificado por grep antes de nombrarlas: sin colisión
con ninguna tabla existente (a diferencia de la colisión real que LOY-3 tuvo
que corregir con `loyalty_programs`).

`customer_orders.customer_id` referencia lógicamente la tabla NUEVA
`customers` (UUIDv7, Customer Master) — mismo precedente que
`loyalty_accounts.customer_id` en la migración 225 — nunca la tabla legacy
`clientes`. El puente de identidad `clientes.id` legacy vs `customers.id`
sigue siendo un pendiente abierto para el código EXISTENTE de
`core/delivery/`, no algo que esta migración resuelve.

Cantidades/pesos/dinero: `TEXT` (Decimal string), nunca `REAL`. Estados no se
validan por `CHECK` de SQL — la capa de dominio
(`backend/domain/orders_delivery/enums.py` + `entities.py`/`policies/`) es la
única fuente de verdad de transiciones válidas, mismo criterio ya establecido
en `sales_schema.py`/`loyalty_schema.py`.

---

## 225_loyalty_bounded_context_schema — 2026-08-28

**Motivo:** LOY-3 (Esquema limpio) del refactor enterprise de Fidelidad/Loyalty
(`docs/refactor/LOY-0_auditoria.md`, `LOY-2_dominio_base.md`). Crea las
tablas born-clean UUIDv7 para las entidades de dominio construidas en LOY-2
(`backend/domain/loyalty/entities/`):

- `loyalty_program_definitions`, `loyalty_accounts` (`customer_id UNIQUE` —
  un cliente, una cuenta), `loyalty_memberships` (`UNIQUE(loyalty_account_id,
  program_id)` — una membresía por cuenta+programa), `loyalty_transactions`
  (el ledger de puntos, `UNIQUE(operation_id)` +
  `UNIQUE(source_module, source_document_id, transaction_type,
  reason_code)` per §12), `loyalty_outbox`.

**Colisión real encontrada y corregida durante esta fase**: un primer borrador
usó el nombre obvio `loyalty_programs`, pero `migrations/m000_base_schema.py::
_create_loyalty` YA crea una tabla legacy con ese nombre exacto (columnas en
español, floats, umbrales de nivel hardcodeados `nivel_bronce/plata/oro/
platino` — el propio esquema del Growth Engine que esta transformación
reemplazará en LOY-27). `CREATE TABLE IF NOT EXISTS` no hizo nada (la tabla
legacy ya existía) y el `CREATE INDEX ... (status)` posterior falló con
`no such column: status` — detectado al bootstrapear una base real desde
cero, no en una fixture aislada. Renombrada a `loyalty_program_definitions`
(nunca `_v2`/`_new`, mismo criterio que `sale_payments` en la migración 198).
`loyalty_accounts`/`loyalty_memberships`/`loyalty_transactions` no colisionan
con nada (verificado por grep antes de nombrarlas). El resto de nombres
canónicos en inglés NO reemplazan las tablas legacy (`loyalty_programs`,
`loyalty_ledger`, `loyalty_pasivo_log`, `tarjetas_fidelidad`) que siguen
siendo la única ruta operativa real (`core/services/loyalty_service.py`) —
mismo patrón de coexistencia que `sales`/`sale_lines` (migración 198) frente
a `ventas`/`detalles_venta`.
`customer_id` en `loyalty_accounts` es una referencia lógica al Customer
Master, sin FK SQL — Fidelidad nunca posee identidad del cliente (§4/§52).
DDL en `backend/infrastructure/db/schema/loyalty_schema.py`
(`create_loyalty_schema`), invocada solo desde esta migración. Verificada
con un bootstrap real desde cero (`scripts/bootstrap_db.py`), no solo en
fixtures aisladas.

---

## 224_configuracion_security_schema — 2026-08-22

**Motivo:** SET-1 — Seguridad, repegado por el usuario (Permisos/Alcances/
Segregación/Autorización/Secretos/Auditoría/Tests). El corte anterior de
SET-1 (2026-08-21) dejó "auditoría en caliente" explícitamente pendiente
(§60: rotación de secreto, cambio de estado crítico de dispositivo/
plantilla). Crea dos tablas nuevas, mismo molde ya probado por
`inventory_authorization_log`/`inventory_audit_log` (migración 121,
`backend/infrastructure/db/schema/inventory_schema.py`) — cada bounded
context su propia tabla, nunca compartida:

- `configuracion_authorization_log` — registro inmutable de
  autorizaciones en caliente (`AuthorizationGrant`): quién solicitó,
  quién autorizó, código de permiso, `operation_id`, motivo.
- `configuracion_audit_log` — before/after (enmascarado por el llamador
  vía `sensitive_data_redaction.py::redact_mapping` antes de escribir)
  para transiciones críticas: bloqueo/retiro de dispositivo, aprobación/
  activación de versión de plantilla.

DDL en `backend/infrastructure/db/schema/configuracion_security_schema.py`
(`create_configuracion_security_schema`), invocada solo desde esta
migración. `tests/integration/_born_clean_db.py` extendido para
aplicarla también en la fixture born-clean en memoria que usan las demás
suites de integración.

---

## UI/UX (Configuración) — 2026-08-22 — sin migración nueva

**Motivo:** el usuario pidió "SET-24 — UI/UX" (Sidebar, Páginas, Diálogos,
Design System, Responsive, Accesibilidad, Tests). Investigado antes de
construir nada: ese número ya significa otra cosa en este plan
(`settings_refactor_execution_plan.md` ya definía SET-24 como
"Eliminación de legacy"), y el sidebar/shell real está en plena
reescritura por una pista SHELL-N separada y no comiteada
(`frontend/desktop/shell/`, 9 módulos de negocio ya migrados vía
`shell_registration.py`, ninguno todavía wireado en `main.py`). Se
confirmó el alcance con el usuario: construir páginas PyQt5 reales para
los 9 bounded contexts de SET-0..23 (ninguno tenía UI antes), siguiendo
el patrón `<DOMAIN>-N_ui_ux`/FASE DS-10 ya usado en el resto del repo
(`docs/refactor/CASH-23_ui_ux.md`, `module_ui_ux_migration_template.md`),
registrado en la arquitectura shell nueva vía `shell_registration.py`.

Sin cambios de esquema — esta fase es 100% capa de aplicación/presentación
sobre tablas ya existentes (SET-2..23).

- **Sidebar** — `frontend/desktop/modules/configuracion/navigation/
  configuracion_sidebar.py::CONFIGURACION_NAV`, 9 entradas (General/
  Dispositivos/Documentos/Pantalla del cliente/Integraciones/Feature
  Flags/Apariencia/Notificaciones/Offline) — un único punto de entrada
  "Configuración", exactamente lo que la propia auditoría SET-0 ya había
  definido como objetivo (`settings_refactor_execution_plan.md`
  §"Alcance"). Notificaciones (SET-20) y Offline (SET-23) no existían
  cuando se escribió ese alcance original; se pliegan igual que
  integraciones/feature-flags/apariencia porque tampoco tienen grupo de
  permisos propio.
- **Páginas** — `pages/base_page.py::ConfiguracionWorkspacePage` (mismo
  shell responsivo canónico que `transfers/pages/base_page.py`), 7
  páginas genéricas de solo lectura vía `pages/workspace_pages.py::_page()`
  + 2 páginas con escritura real (`feature_flags_page.py`/
  `apariencia_page.py`). Primer read path real contra los 9 bounded
  contexts: `backend/application/queries/configuracion/
  workspace_query_service.py::ConfiguracionWorkspaceQueryService`
  (un `page(page_id, search)`, mismo patrón que
  `TransfersWorkspaceQueryService`) — antes de esta fase, ningún archivo
  bajo `frontend/`/`modulos/` importaba ninguno de los 9 paquetes
  `backend.domain.*` (verificado).
- **Diálogos** — `dialogs/feature_flag_dialogs.py::RejectChangeRequestDialog`
  (`FormDialog`, exige motivo no vacío — el dominio ya rechaza uno en
  blanco) y `dialogs/theme_dialogs.py::SetDefaultThemeDialog`
  (`ConfirmationDialog`). Ningún `QDialog` crudo — verificado con test de
  arquitectura.
- **Design System** — cero componentes nuevos; solo consume
  `frontend/desktop/components`/`themes` ya construidos (incluye SET-22
  `backend/domain/appearance/`), tal como exige FASE DS-10 ("el módulo
  nace dentro del estándar").
- **Responsive** — `ConfiguracionView.setMinimumSize(960, 600)`, probado
  a 1366×768, mismo patrón que Transfers.
- **Accesibilidad** — `accessibleName`/tooltips en sidebar, búsqueda y
  tablas; estados de vista (`LOADING`/`EMPTY`) en vez de tablas en blanco;
  navegación por teclado heredada de los widgets DS-3/4 estándar.
- **Escritura real, 2 de 9 secciones** (alcance documentado, no un
  descuido — 7 secciones son de solo lectura por ahora):
  - Feature Flags: `ApproveFeatureFlagChangeRequestUseCase`/
    `RejectFeatureFlagChangeRequestUseCase`/
    `ApplyFeatureFlagChangeRequestUseCase` — orquestan
    `FeatureFlagChangeRequest.approve/reject/apply` (SET-21) y
    `feature_flag_approval_policy.assert_can_approve` (segregación de
    funciones — verificado con test que un auto-approve se rechaza).
  - Apariencia: `SetDefaultThemeUseCase` — desmarca el default activo
    antes de marcar el nuevo (bug real encontrado y corregido durante
    esta fase: verificar `assert_can_set_default` ANTES de desmarcar el
    actual siempre fallaba, porque el propio default activo se
    autobloqueaba; se corrigió el orden — desmarcar primero, luego
    verificar contra el estado ya actualizado).
- **Permisos** — 4 códigos nuevos (`notificacion.ver`/
  `notificacion.gestionar`/`offline.ver`/`offline.gestionar`) agregados
  al grupo `CONFIGURACION` ya existente (`core/security/
  permission_catalog.py`, SET-1) — Notifications y Offline no tenían
  ninguno todavía. El resto de la navegación referencia códigos que ya
  existían.
- **Nada de `ui/themes/theme_engine.py`, `core/services/theme_service.py`,
  `modulos/config_interfaz.py` (la pantalla "Apariencia" legacy, ya rota),
  `modulos/config_modules.py`, ni el sidebar/shell legacy
  (`interfaz/menu_lateral.py`/`interfaz/main_window.py`) se tocaron.**
  `shell_registration.py` existe pero deliberadamente NO está wireado en
  `main.py`/`MainWindow`/`menu_lateral.py` este round — mismo criterio
  exacto que `finance`/`cash_register`/`inventory`/`transfers`
  (verificado con test de arquitectura). La pista SHELL-N (separada, no
  comiteada) sigue siendo dueña de ese corte real.

**Tests**: `tests/integration/configuracion/` — 20 tests contra SQLite
real (`workspace_query_service` sobre los 9 contextos, los 3 use cases
de Feature Flags, `SetDefaultThemeUseCase` incluyendo el switch-back y el
caso idempotente). `tests/unit/test_configuracion_ui_workspace.py` — 9
tests PyQt5 offscreen (mismo patrón que `test_transfers_ui_workspace.py`
— sidebar, tamaños responsivos, filtrado por permiso, diálogos).
`tests/architecture/test_configuracion_ui_guardrails.py` — 7 tests
(sin SQL/sqlite/commit/rollback, sin colores literales, sin
`setStyleSheet`, sin `QDialog` crudo, permisos de navegación contra el
catálogo real, no wireado en el shell legacy). **36 tests nuevos, todos
verdes.** No se suma al conteo acumulado "Total tras SET-N" — es una
fase de presentación ortogonal al conteo de dominio, no otro bounded
context.

---

## 223_offline_schema — 2026-08-21

**Motivo:** SET-23 (Cache, Version, Sync, Expiration) abre
`backend/domain/offline/`, un noveno bounded context — cierra el
residual "SET-23+ | Offline, eliminación de legacy" que quedaba
pendiente desde SET-22.

- **Investigación previa**: `sync/` (`SyncEngine`/`SyncWorker`/
  `ConflictResolver`, motor de reloj Lamport outbox/inbox) es un motor
  completo pero hardcodeado a una lista fija de tablas legacy y **nunca
  importado por `main.py`/`app_container`** — infraestructura muerta
  confirmada, ya documentada independientemente en
  `docs/refactor/CRM-20_offline_sync_conflictos.md` §"Investigación
  previa", que ya se negó a extenderlo por la misma razón. Ese mismo
  documento confirmó que este repo corre hoy sobre un único archivo
  SQLite compartido, sin servidor central ni transporte real entre
  terminales — por lo que esta SET, igual que CRM-20, NO inventa un
  pipeline `sync_status` (`LOCAL_PENDING`/`SYNCING`/...) sin productor
  real. `backend.domain.settings.entities.workstation.Workstation`
  (SET-6) ya tiene `offline_enabled`/`is_online(at, staleness_threshold)`
  — no se duplicó esa lógica de "¿estoy online?"; `resolve_cache_read()`
  recibe `is_online` como parámetro plano que el llamador calcula
  (típicamente con `Workstation.is_online()`), manteniendo independencia
  entre bounded contexts (sin import cruzado).
- **Sin colisión de nombres de tabla** — las tablas legacy `sync_*`
  (`sync_outbox`/`sync_inbox`/`sync_state`/`sync_conflicts`/
  `sync_version_history`, `migrations/m000_base_schema.py`) respaldan un
  concepto distinto (motor de replicación outbox/inbox), así que el
  esquema nuevo usa nombres descriptivos sin prefijo
  (`offline_cache_entries`, `cache_expiration_policies`), born-clean y
  UUIDv7 desde el inicio. `workstation_id` es una FK real a
  `workstations` (SET-6).
- **Cache** — `entities/offline_cache_entry.py::OfflineCacheEntry`
  (`entity_type`/`entity_id`/`workstation_id`/`payload_json`) generaliza
  los dos cachés ad hoc que ya existen en el repo:
  `backend/domain/settings/services/configuration_cache_service.py::
  ConfigurationCache` (invalidado por evento, sin TTL) y el legacy
  `core/cache/address_cache.py::AddressCache` (TTL+LRU, `ttl=3600`
  hardcodeado) — en un modelo tipado y persistido.
- **Version** — `source_version` en `OfflineCacheEntry` es un string
  libre a propósito: refleja cualquier marcador de versión que la
  entidad origen ya use (columna `version` entera, `updated_at`, un hash
  de contenido) — misma disciplina de "reusar lo que ya existe" que
  `docs/refactor/CRM-20_offline_sync_conflictos.md` estableció para
  concurrencia optimista, no un esquema de versionado nuevo.
- **Sync** — `policies/cache_version_sync_policy.py::
  evaluate_sync_state()` generaliza la comparación de versión/
  `updated_at` que `DetectCustomerSyncConflictUseCase`/
  `DetectCRMSyncConflictUseCase` (CRM-20) ya usan para escrituras, en una
  verificación de frescura para lecturas — `CacheSyncState` es
  deliberadamente de solo dos valores (FRESH/STALE), no un pipeline
  multi-estado fabricado sin productor real.
- **Expiration** — `entities/cache_expiration_policy.py::
  CacheExpirationPolicy` (`entity_type` único, `ttl_seconds`) generaliza
  el `ttl=3600` hardcodeado de `AddressCache` en un registro tipado y
  editable por tipo de entidad — el dominio nunca adivina su propio
  umbral, misma disciplina que `Workstation.is_online()` ya estableció
  para "cuánto es demasiado".
  `policies/cache_expiration_evaluation_policy.py::is_expired()` hace la
  comparación de reloj puro.
- **Composición** — `policies/offline_read_policy.py::
  resolve_cache_read()` combina las cuatro piezas en la decisión que un
  camino de lectura offline-first realmente necesita: online + fresco →
  usar caché; online + obsoleto/expirado → refrescar; **offline** +
  obsoleto/expirado → usar caché de todos modos como mejor esfuerzo
  (`USE_CACHE_STALE_OFFLINE`) — el comportamiento genuinamente
  "offline-first": sin conectividad, un caché obsoleto sigue siendo la
  mejor respuesta disponible, nunca "sin caché" solo porque el reloj o
  la versión avanzaron.
- **Nada de `sync/` (`SyncEngine`/`SyncWorker`/`ConflictResolver`), las
  tablas `sync_*` legacy, `ConfigurationCache`, ni `AddressCache` se
  tocaron.** Esta SET construye el modelo tipado que generalizaría esos
  dos cachés ad hoc, no ejecuta su corte.

**Tests**: `tests/unit/offline/` — 20 tests
(`test_offline_cache_entry_and_expiration_policy.py`,
`test_offline_read_policy.py` — expiración/comparación de versión/
composición online-offline). `tests/integration/offline/
test_offline_repositories.py` — 23 tests contra SQLite real (round-trip
de los 2 repositorios, FK real a `workstations`, índice único de entrada
por alcance, ciclo refresh/mark_stale persistido, composición de extremo
a extremo con `resolve_cache_read()`).
**Total tras SET-23 (Settings + Device Management + Document Output +
Customer Display + Integrations + Notifications + Feature Flags +
Appearance + Offline): 1121 tests verdes**
(`pytest tests/unit/settings/ tests/integration/settings/ tests/unit/device_management/ tests/integration/device_management/ tests/unit/document_output/ tests/integration/document_output/ tests/unit/customer_display/ tests/integration/customer_display/ tests/unit/integrations/ tests/integration/integrations/ tests/unit/notifications/ tests/integration/notifications/ tests/unit/feature_flags/ tests/integration/feature_flags/ tests/unit/appearance/ tests/integration/appearance/ tests/unit/offline/ tests/integration/offline/`).

---

## 222_appearance_schema — 2026-08-21

**Motivo:** SET-22 (Themes, Tokens, Light/dark, Density) abre
`backend/domain/appearance/`, un octavo bounded context — el residual
"SET-22+ | Apariencia, offline, eliminación de legacy" que
`settings_refactor_execution_plan.md` venía dejando pendiente desde
SET-21.

- **Investigación previa**: tres sistemas de tema paralelos e
  inconsistentes coexisten hoy. `ui/themes/theme_engine.py` — singleton a
  nivel de módulo, solo dos temas (`"Claro"/"Oscuro"`, alias
  `SPJ_DARK`/`SPJ_LIGHT`), lee/escribe SQL crudo contra la tabla genérica
  `configuraciones(clave, valor)` con clave `'tema'`
  (`settings_legacy_inventory.md:133` ya lo marcaba REWRITE).
  `core/services/theme_service.py::ThemeService` — puente viejo/nuevo,
  lee/escribe claves `ui_theme`/`ui_density`/`ui_font_size`/`ui_icon_size`
  en la misma tabla genérica, `density` es un string libre sin validar
  (`'Normal'` por defecto, sin conjunto de opciones definido).
  `frontend/desktop/themes/` — sistema de diseño más nuevo ("FASE DS-2"),
  `theme_manager.py` (`VALID_THEMES=("light","dark")`) y un módulo
  `tokens.py` real (Spacing/Typography/Radii/Borders/Elevation/
  ControlHeights/IconSizes/etc.) pero sin persistencia en DB y sin
  concepto de densidad. `modulos/config_interfaz.py` (la pantalla
  "Apariencia") ya está rota hoy — referencia
  `theme_service.palettes`/`.densities`, atributos que no existen en
  `ThemeService` actual. Ninguno de los tres sistemas se tocó.
- **Sin colisión de nombres de tabla** — las preferencias legacy viven
  como claves sueltas dentro de `configuraciones(clave, valor)`, no en
  tablas dedicadas, así que el esquema nuevo usa nombres descriptivos sin
  prefijo (`themes`, `design_tokens`, `density_profiles`,
  `appearance_preferences`), born-clean y UUIDv7 desde el inicio.
- **Themes** — `entities/theme.py::Theme` (`code`/`name`/`mode`/
  `is_default`) generaliza el par hardcodeado "Claro"/"Oscuro" en un
  catálogo tipado y administrable.
  `policies/theme_default_policy.py::assert_can_set_default()` exige a lo
  sumo un tema default activo — verificado también a nivel de esquema con
  `ux_themes_single_default` (índice único parcial sobre `is_default`
  donde toda fila filtrada vale 1, mismo idioma de "a lo sumo una fila"
  que `ux_ff_rules_scope_active`, SET-21, aplicado aquí a un singleton en
  vez de una restricción por alcance) — doble verificación (dominio +
  esquema), mismo patrón de "defense in depth" que la segregación de
  funciones de `feature_flag_approval_policy`.
- **Tokens** — `entities/design_token.py::DesignToken`
  (`theme_id`/`token_key`/`category`/`token_value`) generaliza el módulo
  `frontend/desktop/themes/tokens.py` (constantes Python hardcodeadas, sin
  persistencia ni mecanismo de override) en filas tipadas y persistidas.
  `theme_id=NULL` marca un token GLOBAL (aplica a todos los temas);
  `policies/token_resolution_policy.py::resolve_tokens_for_theme()`
  fusiona tokens globales con overrides específicos de un tema —
  específico gana sobre global, mismo principio de especificidad que el
  resto de las políticas de resolución de este proyecto, aplicado aquí a
  una fusión de mapa en vez de una selección de una sola regla ganadora.
- **Light/dark** — `ThemeMode` (LIGHT/DARK) en `Theme` generaliza
  directamente el split Claro/Oscuro legacy.
  `entities/appearance_preference.py::AppearancePreference`
  (`AppearanceScopeType`: GLOBAL/BRANCH/USER) generaliza el par plano
  único `{ui_theme, ui_density}` del `ThemeService` legacy en overrides
  por sucursal/usuario — sin precedente legacy de scoping en absoluto.
  `policies/appearance_resolution_policy.py::resolve_appearance()`
  reimplementa "la coincidencia más específica gana" (USER > BRANCH >
  GLOBAL), el mismo principio que `ConfigurationResolutionService`,
  `print_routing_policy`, `notification_routing_policy`, y
  `feature_flag_evaluation_policy` ya establecieron independientemente
  (independencia entre bounded contexts).
- **Density** — `entities/density_profile.py::DensityProfile`
  (`DensityLevel`: COMPACT/NORMAL/COMFORTABLE, `scale_factor` Decimal,
  métricas en px) — sin precedente legacy alguno; el `density` de
  `ThemeService` es un string libre sin opciones ni métricas definidas.
  `scale_factor` es Decimal (nunca float), consistente con la convención
  general del repo para valores numéricos de negocio, aunque no sea
  dinero, para evitar drift de redondeo de punto flotante en reflows de
  UI repetidos.
- **Nada de `ui/themes/theme_engine.py`, `core/services/
  theme_service.py`, `frontend/desktop/themes/`, ni las claves
  `configuraciones` (`'tema'`/`ui_theme`/`ui_density`/`ui_font_size`/
  `ui_icon_size`) se tocaron.** Tampoco se reparó la pantalla rota
  `modulos/config_interfaz.py`. Esta SET construye el modelo tipado que
  habilitaría un futuro corte, no ejecuta el corte de los consumidores
  reales. `tests/test_fase0_theme_engine_persistence.py` y
  `tests/test_fase0_theme_normalization.py` (cobertura de la persistencia
  legacy) siguen intactos y en verde.

**Tests**: `tests/unit/appearance/` — 35 tests
(`test_theme_and_design_token.py` — Theme + DesignToken + theme_default_policy
+ token_resolution_policy —, `test_density_profile.py`,
`test_appearance_preference_and_resolution.py` — AppearancePreference +
resolve_appearance con especificidad USER > BRANCH > GLOBAL).
`tests/integration/appearance/test_appearance_repositories.py` — 24 tests
contra SQLite real (round-trip de los 4 repositorios, índice único de
tema default singleton, índice único de token por alcance, índice único
de preferencia activa por alcance, composición de extremo a extremo con
`resolve_tokens_for_theme()` y `resolve_appearance()`).
**Total tras SET-22 (Settings + Device Management + Document Output +
Customer Display + Integrations + Notifications + Feature Flags +
Appearance): 1078 tests verdes**
(`pytest tests/unit/settings/ tests/integration/settings/ tests/unit/device_management/ tests/integration/device_management/ tests/unit/document_output/ tests/integration/document_output/ tests/unit/customer_display/ tests/integration/customer_display/ tests/unit/integrations/ tests/integration/integrations/ tests/unit/notifications/ tests/integration/notifications/ tests/unit/feature_flags/ tests/integration/feature_flags/ tests/unit/appearance/ tests/integration/appearance/`).

---

## 221_feature_flags_schema — 2026-08-21

**Motivo:** SET-21 (Flags, Rules, Rollout, Approval) abre
`backend/domain/feature_flags/`, un séptimo bounded context — el objetivo
exacto que la propia auditoría SET-0 ya había nombrado en
`settings_legacy_inventory.md` §6.3: *"MOVE la lógica de evaluación
(útil), REWRITE el esquema/repository unificándolo con
`FeatureFlag`/`FeatureFlagRule` tipados del prompt maestro"*.

- **Investigación previa**: `core/services/feature_flag_service.py::
  FeatureFlagService` (`is_enabled`/`set_flag`/`require_feature`, caché en
  RAM por sucursal) es real y sigue en uso por `modulos/config_modules.py`
  y `modulos/delivery.py:1310-1312`. Su repositorio,
  `repositories/feature_flag_repository.py`, detecta en tiempo de
  ejecución (`PRAGMA table_info`) si la tabla `feature_flags` tiene el
  esquema nuevo (`feature_name`/`enabled`/`branch_id`) o el legacy
  (`clave`/`activo`) — deuda técnica real, no hipotética. Ninguno de los
  dos se tocó.
- **Nombre de tabla deliberadamente distinto** — el esquema nuevo usa
  prefijo `ff_` (`ff_flags`/`ff_rules`/`ff_change_requests`) precisamente
  para no colisionar con la tabla legacy `feature_flags` que
  `modulos/config_modules.py`/`modulos/delivery.py` siguen leyendo sin
  cambios.
- **Flags** — `entities/feature_flag.py::FeatureFlag` (`code`/`name`/
  `default_enabled`) — generaliza las claves string sueltas que
  `is_enabled(feature_name, ...)` ya usa en producción, con un fallback
  explícito por flag en vez del `False` codificado a mano que el
  servicio legacy asume para cualquier flag desconocido.
- **Rules** — `entities/feature_flag_rule.py::FeatureFlagRule`
  (`FeatureFlagScopeType`: GLOBAL/BRANCH/USER) generaliza la precedencia
  `branch_id IN (?, 0) ORDER BY branch_id DESC` del repositorio legacy
  (una fila específica de sucursal gana sobre la global) en un ranking de
  especificidad explícito, agregando USER como dimensión de targeting que
  el esquema legacy nunca tuvo.
- **Rollout** — `rollout_percentage` en `FeatureFlagRule` (0-100),
  capacidad genuinamente nueva que el esquema legacy (solo booleano) no
  tenía en absoluto.
  `policies/feature_flag_evaluation_policy.py::resolve_flag_value()`
  reimplementa "la regla más específica que coincide gana" (mismo
  principio que `ConfigurationResolutionService`, SET-2/4, y
  `print_routing_policy`, SET-8, reimplementado independientemente) y,
  cuando la regla ganadora tiene `rollout_percentage < 100`, decide con un
  hash determinista de `(flag.code, evaluation_key)` — sin aleatoriedad,
  reproducible en tests, verificado con una distribución de 1000 llaves
  distintas cayendo dentro de una banda razonable del porcentaje
  configurado.
- **Approval** — `entities/feature_flag_change_request.py::
  FeatureFlagChangeRequest`, máquina de 4 estados (PENDING_APPROVAL→
  APPROVED→APPLIED, o →REJECTED) — más simple que los 7 estados de
  `DocumentTemplateVersion` (SET-11) porque no hay fase de edición en
  borrador, una propuesta corregida es una solicitud nueva.
  `policies/feature_flag_approval_policy.py::assert_can_approve()`
  reimplementa la misma segregación de funciones que
  `configuration_approval_policy.assert_can_approve` ya exige para
  cambios de configuración (§59): quien solicita un cambio no puede
  aprobarlo.
- **Nada de `FeatureFlagService`/`FeatureFlagRepository`/la tabla
  `feature_flags` legacy se tocó.** Esta SET construye el modelo tipado
  que la propia auditoría SET-0 pidió, no ejecuta el corte de los
  consumidores reales.

**Tests**: `tests/unit/feature_flags/` — 47 tests
(`test_feature_flag_and_rule.py`,
`test_feature_flag_evaluation_policy.py` — especificidad + rollout
determinista, incluida la prueba de distribución sobre 1000 llaves —,
`test_feature_flag_change_request_and_approval.py`).
`tests/integration/feature_flags/test_feature_flag_repositories.py` —
10 tests contra SQLite real (round-trip de los 3 repositorios, índice
único de regla activa por alcance, composición de extremo a extremo con
`resolve_flag_value()`, ciclo completo solicitud→aprobación→aplicación).
**Total tras SET-21 (Settings + Device Management + Document Output +
Customer Display + Integrations + Notifications + Feature Flags): 1019
tests verdes**
(`pytest tests/unit/settings/ tests/integration/settings/ tests/unit/device_management/ tests/integration/device_management/ tests/unit/document_output/ tests/integration/document_output/ tests/unit/customer_display/ tests/integration/customer_display/ tests/unit/integrations/ tests/integration/integrations/ tests/unit/notifications/ tests/integration/notifications/ tests/unit/feature_flags/ tests/integration/feature_flags/`).

---

## 220_notifications_schema — 2026-08-21

**Motivo:** SET-20 (Accounts, Templates, Channels, Routing) abre
`backend/domain/notifications/`, un sexto bounded context, generalizando
el catálogo real de plantillas WhatsApp y los remitentes reales por canal
que este repositorio ya tiene, sin tocarlos.

- **Investigación previa**: `whatsapp_service/messaging/templates.py::
  TEMPLATES` es un diccionario real de 9 plantillas aprobadas por Meta
  (`pedido_confirmado`, `pedido_listo`, `anticipo_requerido`, ...), cada
  una con `name`/`language`/`params` — WhatsApp solo permite mensajes de
  plantilla pre-aprobados fuera de la ventana de 24h de servicio al
  cliente (comentario explícito al inicio de ese módulo).
  `send_event_template(to, event_name, params)` hace el ruteo implícito
  evento→plantilla, y rellena params faltantes con `""` en silencio — el
  hueco real que esta SET cierra.
  `backend/infrastructure/integrations/cash_notification_senders.py::
  WhatsAppNotificationSender`/`EmailNotificationSender` (CASH-*) y
  `loss_notification_senders.py::LossWhatsAppNotificationSender`
  (LOSS-19) son remitentes reales y en vivo, con su propia validación de
  destinatario (E.164 vía regex `r"\+[1-9]\d{7,14}"` para WhatsApp,
  `"@"` para email). Ninguno de los tres artefactos se tocó ni se
  importó.
- **Accounts** — `entities/notification_account.py::NotificationAccount`
  (`channel`/`credential_reference` hacia `SecretStoreGateway`,
  `integration_instance_id` como referencia opaca hacia el catálogo de
  SET-19 — nunca resuelta ni validada como FK real, mismo patrón que
  `PrintJob.source_document_id`).
- **Templates** — `entities/notification_template.py::NotificationTemplate`
  generaliza `TEMPLATES` (mismos campos `code`/`language`/
  `parameter_names`, `UNIQUE(code, channel)`). `policies/
  template_parameter_policy.py::assert_params_satisfied()` **corrige el
  hueco real**: en vez de rellenar un parámetro faltante con `""` en
  silencio (como hace `send_event_template` hoy), rechaza el envío
  explícitamente.
- **Channels** — `notification_channel_ports.py::NotificationChannelPort`,
  sin implementación real a propósito — los remitentes reales ya existen
  por módulo (WhatsApp/Email de Caja, WhatsApp de Mermas) y esta SET no
  los duplica ni los reemplaza; una futura consolidación adaptaría esos
  remitentes reales a este Protocol, no al revés.
  `value_objects/notification_message.py::NotificationMessage` reproduce
  exactamente la validación real de destinatario de
  `cash_notification_senders.py` (E.164 para WhatsApp/SMS, `"@"` para
  email), generalizada para cualquier módulo.
- **Routing** — `entities/notification_route.py::NotificationRoute`
  (`event_code`→`template_id`+`account_id`) +
  `policies/notification_routing_policy.py::resolve_route()` — a lo sumo
  una ruta ACTIVE por `event_code` (índice único parcial
  `ux_notification_routes_event_active`).
- **Nada de WhatsApp/`TEMPLATES`/los remitentes reales se tocó.** Esta SET
  construye el catálogo de gobierno que eventualmente los reemplazaría,
  no ejecuta ese corte.

**Tests**: `tests/unit/notifications/` — 35 tests
(`test_notification_account_and_template.py`,
`test_notification_routing.py`,
`test_notification_message_and_channel_port.py` — incluye validación de
destinatario por canal y composición con un canal falso).
`tests/integration/notifications/test_notification_repositories.py` —
10 tests contra SQLite real (round-trip de los 3 repositorios, `UNIQUE(code,
channel)`, índice único de ruta activa por evento, composición de
extremo a extremo con `resolve_route()`/`assert_params_satisfied()`).
**Total tras SET-20 (Settings + Device Management + Document Output +
Customer Display + Integrations + Notifications): 962 tests verdes**
(`pytest tests/unit/settings/ tests/integration/settings/ tests/unit/device_management/ tests/integration/device_management/ tests/unit/document_output/ tests/integration/document_output/ tests/unit/customer_display/ tests/integration/customer_display/ tests/unit/integrations/ tests/integration/integrations/ tests/unit/notifications/ tests/integration/notifications/`).

---

## 219_integrations_schema — 2026-08-21

**Motivo:** SET-19 (Definitions, Instances, Credentials, Health,
Webhooks) abre `backend/domain/integrations/`, un catálogo de gobierno
para las integraciones externas del ERP — generalizando las dos
integraciones reales y en vivo que este repositorio ya tiene (WhatsApp,
MercadoPago) en lugar de inventar el concepto desde cero.

- **Investigación previa**: `whatsapp_service/middleware/hmac_validator.py`
  ya implementa dos esquemas reales de verificación de firma —
  `verify_signature` (Meta, header `X-Hub-Signature-256`) y
  `verify_mp_signature` (MercadoPago, manifiesto `ts=...,v1=...`,
  conectado desde SET-1). `backend/security/secrets/secret_store_gateway.py::
  SecretStoreGateway` (`set_secret`/`get_secret`/`describe`/
  `rotate_secret`/`list_references`) ya existe, construido pero sin
  conectar sus consumidores (nota explícita de la auditoría SET-0, §6.5).
  Ninguno de los dos artefactos se tocó ni se importó — WhatsApp es un
  microservicio independiente (CLAUDE.md §14), no algo de lo que este
  backend deba depender vía import de Python.
- **Definitions** — `entities/integration_definition.py::IntegrationDefinition`:
  catálogo de *tipos* de integración (`code`/`category`/
  `required_credential_names`) — p. ej. `WHATSAPP`/MESSAGING,
  `MERCADOPAGO`/PAYMENTS.
- **Instances**/**Credentials** — `entities/integration_instance.py::IntegrationInstance`:
  una instancia configurada de una definición (`config` para ajustes no
  sensibles, `credential_references` para referencias con nombre hacia
  `SecretStoreGateway` — nunca el secreto en sí). `config` se escanea
  contra claves con apariencia de secreto y se rechaza — reimplementación
  independiente del mismo guardia que
  `backend.domain.device_management.value_objects.connection_profile.
  ConnectionProfile` ya aplica a `extra_parameters` (SET-7), no
  importado. `policies/credential_provisioning_policy.py::
  assert_credentials_satisfied()` exige que la instancia tenga referencia
  para cada credencial que su definición requiere — mismo patrón
  "atrápalo en construcción" que `LabelVariableSet.assert_satisfied()`
  (SET-14).
- **Health** — `entities/integration_health_check.py::IntegrationHealthCheck`
  (registro append-only, mismo patrón que `DeviceTestResult`, SET-9) +
  `policies/integration_health_policy.py::current_status()` (el chequeo
  más reciente decide HEALTHY/DOWN; DEGRADED si el más reciente falló
  pero hay un éxito anterior en el historial provisto; UNKNOWN sin
  historial).
- **Webhooks** — `entities/webhook_endpoint.py::WebhookEndpoint` (catálogo
  de endpoints, `signature_scheme` + `signing_secret_reference`) +
  `webhook_verification_ports.py::WebhookSignatureVerifierPort`, **con
  implementación real** —
  `backend/infrastructure/integrations/webhook_signature_verifier.py::
  WebhookSignatureVerifier` — a diferencia de `DocumentRendererPort`
  (SET-11) o `CustomerDisplayGatewayPort` (SET-17), verificar HMAC es
  criptografía sin estado y sin dependencia de hardware/librería externa,
  el mismo criterio de "seguro construirlo real" que SET-12 aplicó al
  ruteo de impresión. **Reimplementa, no importa**, la misma lógica que
  `hmac_validator.py` ya tiene — verificado con los mismos vectores de
  prueba (firma válida, secreto incorrecto, cuerpo alterado, header
  ausente/malformado, `data_id` insensible a mayúsculas) para confirmar
  que produce resultados idénticos al validador real.
- **Nada de WhatsApp/MercadoPago/`SecretStoreGateway` se tocó.** Esta SET
  construye el catálogo de gobierno; conectar los consumidores reales
  (WhatsApp/MercadoPago/SMTP) a `SecretStoreGateway` y a este catálogo
  sigue pendiente, tal como la auditoría SET-0 ya lo señaló.

**Tests**: `tests/unit/integrations/` — 53 tests
(`test_integration_definition_and_instance.py`,
`test_integration_health.py`, `test_webhook_endpoint_and_verifier.py` —
incluye vectores de prueba equivalentes a los reales de WhatsApp/
MercadoPago). `tests/integration/integrations/` — 17 tests contra SQLite
real (`test_integration_definition_and_instance_repositories.py`,
`test_health_and_webhook_repositories.py`). **Total tras SET-19
(Settings + Device Management + Document Output + Customer Display +
Integrations): 917 tests verdes**
(`pytest tests/unit/settings/ tests/integration/settings/ tests/unit/device_management/ tests/integration/device_management/ tests/unit/document_output/ tests/integration/document_output/ tests/unit/customer_display/ tests/integration/customer_display/ tests/unit/integrations/ tests/integration/integrations/`).

---

## 218_content_and_advertising_schema — 2026-08-21

**Motivo:** SET-18 (Content, Campaigns, Placements, Approval, Metrics)
completa `backend/domain/customer_display/` con lo que SET-0/SET-17 ya
habían dejado explícitamente pendiente: `ContentCampaign`/
`AdvertisingSlot`, la mitad "publicidad" de Customer Display que SET-17
(Displays/Layouts/Modes/Gateway) deliberadamente no construyó.

- **Content** — `entities/content.py::Content`: una pieza reutilizable de
  material (imagen/video/texto/HTML — `ContentType`), con
  `duration_seconds`. Sin historial de versiones (a diferencia de
  `DocumentTemplateVersion`, SET-18 no lo pide) — se edita en el lugar.
- **Campaigns**/**Approval** — `entities/content_campaign.py::ContentCampaign`,
  máquina de 7 estados que **replica exactamente** la forma de
  `DocumentTemplateVersionStatus` (SET-11): DRAFT→PENDING_APPROVAL→
  APPROVED→ACTIVE→INACTIVE/EXPIRED→ARCHIVED, sin terminal REJECTED (un
  rechazo regresa a DRAFT). La misma disciplina de "esto necesita
  revisión antes de estar en vivo" que ya se aplicó a plantillas de
  documentos aplica igual a contenido publicitario que se muestra en la
  pantalla de cara al cliente.
- **Placements** — `entities/advertising_slot.py::AdvertisingSlot`
  (reutiliza `CustomerDisplayMode` de SET-17, mismo bounded context) +
  `entities/campaign_placement.py::CampaignPlacement`, que **replica
  exactamente** la forma de `WorkstationDeviceAssignment` (device_management,
  SET-7): `assign()`/`unassign()`, a lo sumo una asignación ACTIVA por
  slot (índice único parcial `ux_campaign_placements_slot_active`, mismo
  patrón que `ux_wda_workstation_role_active`).
  **Approval gatea Placements**: `policies/campaign_placement_policy.py::
  assign_placement()` exige que la campaña esté en estado ACTIVE (nunca
  DRAFT/PENDING_APPROVAL/APPROVED/INACTIVE/EXPIRED/ARCHIVED) antes de
  poder ocupar un slot — contenido sin aprobar nunca llega a la pantalla.
- **Metrics** — `entities/content_impression.py::ContentImpression`
  (registro de solo-append, sin ciclo de vida — mismo patrón que
  `DeviceTestResult`, SET-9) +
  `policies/impression_metrics_policy.py::summarize_impressions()`
  (conteo, duración total, promedio Decimal). **Honesto sobre su alcance**:
  no existe ninguna pantalla física real que genere impresiones reales
  todavía (misma situación que `CustomerDisplayGatewayPort` sin
  implementación real en SET-17) — esta es la capacidad de registro que
  un futuro consumidor de gateway usaría, no una afirmación de que hay
  métricas reales hoy.
- **`CustomerDisplayQueryService`/`CustomerDisplay`/`DisplayLayout`
  (SET-17) no se tocaron.**

**Tests**: `tests/unit/customer_display/` — 56 tests nuevos
(`test_content_entity.py`, `test_content_campaign_entity.py`,
`test_advertising_slot_and_placement.py`, `test_impression_metrics.py`).
`tests/integration/customer_display/` — 14 tests nuevos
(`test_content_and_campaign_repositories.py`,
`test_placement_and_impression_repositories.py` — incluye el índice
único de slot activo y la composición completa de
`assign_placement()`/`summarize_impressions()` contra SQLite real).
**Total tras SET-18 (Settings + Device Management + Document Output +
Customer Display): 847 tests verdes**
(`pytest tests/unit/settings/ tests/integration/settings/ tests/unit/device_management/ tests/integration/device_management/ tests/unit/document_output/ tests/integration/document_output/ tests/unit/customer_display/ tests/integration/customer_display/`).

---

## 217_customer_display_schema — 2026-08-21

**Motivo:** SET-17 (Displays, Layouts, Modes, Gateway) abre **el cuarto y
último bounded context nuevo** que el propio título de este plan de
ejecución anticipa ("Settings / Device Management / Document Output /
Customer Display"): `backend/domain/customer_display/`, gobernando la
pantalla secundaria orientada al cliente en caja.

- **Investigación previa**: la auditoría de SET-0 (§6.4) ya había
  encontrado el único artefacto real que existe hoy —
  `backend/application/sales/queries/customer_display_query_service.py::
  CustomerDisplayQueryService.current_state()` — una proyección de solo
  lectura sobre `Sale` (Ventas solo *publica* estado para esta pantalla,
  nunca la controla, §6/§50) con su propio DTO
  (`CustomerDisplayStateDTO`/`CustomerDisplayLineDTO` en
  `backend/application/sales/dto.py`). Esa auditoría clasificó
  explícitamente: **REUSE como base de diseño**, construir el resto
  (`CustomerDisplay`, `DisplayLayout`, `ContentCampaign`,
  `AdvertisingSlot`) desde cero. SET-17 construye los dos primeros;
  `ContentCampaign`/`AdvertisingSlot` quedan para una SET futura (mismo
  patrón de incrementos pequeños que separó Tickets de Marketing en
  SET-12/13).
- **Displays** — `entities/customer_display.py::CustomerDisplay`: el
  registro de una pantalla física/virtual en una estación de trabajo
  (`workstation_id` FK a `workstations`, migración 210 de Settings —
  misma dirección de dependencia que Device Management y Document Output
  ya establecieron). `current_mode` **sin máquina de estados** — a
  diferencia de `PrintJob`/`DocumentTemplateVersion`, el modo de una
  pantalla refleja lo que sea que el estado de la venta diga en cada
  momento, sin regla de negocio que restrinja qué modo puede seguir a
  cuál; `set_mode()` es una asignación libre, no una transición
  guardada.
- **Modes** — `enums.py::CustomerDisplayMode` (IDLE/CART/PAYMENT_PENDING/
  THANK_YOU), generaliza el diccionario legacy
  `customer_display_query_service.py::_SCREEN_BY_STATUS` (mismos 4
  valores, no inventados) en un enum tipado.
- **Layouts** — `value_objects/display_section.py::DisplaySection` +
  `entities/display_layout.py::DisplayLayout`: qué secciones
  (`CustomerDisplaySectionCode`: CUSTOMER_NAME/ITEMS/SUBTOTAL/DISCOUNT/
  TOTAL/MESSAGE/LOGO) se muestran, en qué orden, para cada modo.
  Definidos independientemente de
  `backend.domain.document_output.value_objects.document_section` pese a
  la forma casi idéntica — misma disciplina de independencia entre
  bounded contexts que ya separó `DeviceStatus`/`WorkstationStatus`. A lo
  sumo un `DisplayLayout` ACTIVE por modo, forzado con un índice único
  parcial (`ux_display_layouts_mode_active`), sin historial de versiones
  (SET-17 no lo pide, a diferencia de `DocumentTemplateVersion` en
  SET-11). `policies/display_layout_resolution_policy.py::resolve_layout()`
  resuelve cuál layout aplica — más simple que
  `print_routing_policy.resolve_route()` (SET-8): sin ámbito por
  sucursal/estación, porque el mapeo legacy que generaliza siempre fue
  global.
- **Gateway** — `gateway_ports.py::CustomerDisplayGatewayPort`, **sin
  implementación real, a propósito** — la propia auditoría de SET-0 ya
  había confirmado "no existe ningún consumidor/hardware real de
  customer display en este repositorio (cero referencias)"; construir un
  mecanismo de push hacia un dispositivo que no existe sería exactamente
  la infraestructura decorativa que el propio docstring de
  `CustomerDisplayQueryService` ya se negó a construir por la misma
  razón. `policies/display_state_push_policy.py::push_state()` filtra el
  contenido a solo lo que el layout resuelto habilita antes de llamar al
  gateway — probado con un gateway falso
  (`test_gateway_ports_composition.py`, mismo patrón que
  `test_rendering_ports_composition.py`/`test_hardware_ports_composition.py`).
- **`CustomerDisplayQueryService`/`CustomerDisplayStateDTO` (Sales) no se
  tocaron.** Esta SET construye la capacidad de dominio (registro de
  pantallas, layouts, resolución de modo, gateway) que un futuro caso de
  uso conectaría con esa proyección real de Ventas — no se ejecuta esa
  integración en este corte.

**Tests**: `tests/unit/customer_display/` — 27 tests
(`test_customer_display_entity.py`, `test_display_layout_entity.py`,
`test_display_layout_resolution_policy.py`,
`test_gateway_ports_composition.py`). `tests/integration/
customer_display/test_customer_display_repositories.py` — 8 tests contra
SQLite real (round-trip de ambos repositorios, cambio de modo persistido,
listados filtrados, índice único de layout activo por modo). **Total
tras SET-17 (Settings + Device Management + Document Output + Customer
Display): 777 tests verdes**
(`pytest tests/unit/settings/ tests/integration/settings/ tests/unit/device_management/ tests/integration/device_management/ tests/unit/document_output/ tests/integration/document_output/ tests/unit/customer_display/ tests/integration/customer_display/`).

---

## 216_document_numbering_schema — 2026-08-21

**Motivo:** SET-16 (Sequences, Reservas, Reset, Idempotencia) cierra el
riesgo "Folio duplicado" que la propia entrada de SET-10 en este log ya
había marcado explícitamente: *"al introducir `DocumentNumberSequence`
mientras `next_number()` legacy sigue activo... cortar ambos consumidores
al mismo tiempo, no dejar dos generadores de folio vivos"*. Esta SET
construye ese `DocumentNumberSequence` — no corta ningún consumidor legacy
todavía (ver abajo).

- **Investigación previa**: ya existen **dos** esquemas de folio distintos
  y en vivo — `backend/domain/procurement/value_objects.py::DocumentNumber`
  (formato `PREFIX-YYYY-NNNNNN`, calculado con
  `backend/infrastructure/db/repositories/procurement/support_repositories.py::
  DocumentSequenceRepository.next_number()` — un **escaneo `MAX(document_number)+1`
  contra la tabla de documentos real**, con una ventana de carrera real:
  dos reservas concurrentes pueden leer el mismo MAX antes de que
  cualquiera confirme; solo el `UNIQUE(document_number)` evita la
  colisión, y solo después del hecho) y
  `backend/domain/finance/value_objects/document_number.py::DocumentNumber`
  (un wrapper opaco de string, sin generación propia). Ninguno de los dos
  se tocó.
- **Sequences** — `entities/document_number_sequence.py::DocumentNumberSequence`:
  un contador persistido por prefijo (`document_number_sequences`, único
  por `prefix`), en vez de escanear una tabla de documentos cada vez.
  `value_objects/document_number.py::DocumentNumber` (mismo nombre que
  los otros dos por diseño — duplicación deliberada entre bounded
  contexts, igual que `DeviceStatus`/`WorkstationStatus`) formatea
  `PREFIX-PERIOD-NNNNNN`.
- **Reservas** — `reserve_next()`: incrementa el contador y devuelve el
  `DocumentNumber` resultante como una operación mecánica de un solo
  paso, reforzada por `document_number_reservations`
  (`UNIQUE(sequence_id, operation_id)` + `UNIQUE(document_number)`
  global) — un registro auditable de cada reserva exitosa, no solo un
  contador ciego.
- **Reset** — `SequenceResetPolicy` (NEVER/YEARLY/MONTHLY/DAILY),
  generaliza el reset anual implícito que el esquema de Procurement ya
  tenía (`WHERE document_number LIKE 'PREFIX-{year}-%'`) en una política
  explícita y configurable. `reserve_next()` reinicia el contador
  automáticamente al cruzar de periodo; `force_reset()` es la operación
  administrativa distinta — corregir manualmente sin esperar el cruce de
  periodo.
- **Idempotencia** — `policies/sequence_reservation_policy.py::
  reserve_with_idempotency()`: si ya existe una reserva para el
  `operation_id` dado, la devuelve sin avanzar el contador — mismo patrón
  exacto que `configuration_values.operation_id` (Settings, SET-3) y
  `print_jobs.operation_id` (Document Output, SET-11). La entidad
  (`reserve_next()`) sigue siendo permisiva y mecánica; la policy es
  donde se exige la regla de negocio más estricta — mismo split que
  `reprint_policy.py` estableció en SET-12.
- **Nada de Procurement/Finance se tocó.** Esta SET construye el
  generador seguro que eventualmente reemplazaría el escaneo `MAX()+1` de
  Procurement, pero no ejecuta ese corte — cortar ambos consumidores al
  mismo tiempo (como la propia entrada de SET-10 ya advertía) es trabajo
  de una SET futura con autorización explícita, no de esta.

**Tests**: `tests/unit/document_output/` +18
(`test_document_number_sequence.py` — las 4 políticas de reset +
`force_reset`; `test_sequence_reservation_policy.py` — idempotencia).
`tests/integration/document_output/test_document_numbering_repositories.py`
— 8 tests contra SQLite real (round-trip de secuencia, `prefix` único,
persistencia del contador entre recargas, idempotencia de extremo a
extremo simulando una petición repetida, índice único de `operation_id`
por secuencia, unicidad global de `document_number`). **Total tras
SET-16 (Settings + Device Management + Document Output): 742 tests
verdes**
(`pytest tests/unit/settings/ tests/integration/settings/ tests/unit/device_management/ tests/integration/device_management/ tests/unit/document_output/ tests/integration/document_output/`).

---

## SET-15 (Sorteos) — sin migración nueva — 2026-08-21

**Motivo:** SET-15 (Integración con Sweepstakes, Plantilla, Boleto,
Reimpresión) cierra el círculo de `DocumentType.SWEEPSTAKES_TICKET`
(reservado desde SET-11, sin uso hasta ahora) integrando Document Output
con el dominio real de rifas/sorteos que ya vive en
`core/services/loyalty_service.py::LoyaltyService` (validadores
financieros reales de §FASE 3: no activar rifa sin presupuesto
reservado, no generar boletos si la rifa no está activa, no seleccionar
ganador si la rifa no está cerrada) y
`core/tickets/raffle_ticket_renderer.py::RaffleTicketESCPOSRenderer`. **No
genera una migración 216** — nota explícita:

- **Investigación previa**: `LoyaltyService` es dueño real de las reglas
  de negocio de rifas (activación, elegibilidad de generación de
  boletos, selección de ganador) — no se tocó ni se reimplementó nada de
  eso, consistente con Prioridad 0 del CLAUDE.md. Su capa de repositorio
  (`list_raffles`, `list_raffle_tickets`, `generate_tickets_for_sale`,
  ...) todavía usa ids enteros legacy (`venta_id: int`,
  `sucursal_id: int`) — no migrada a UUIDv7 (REGLA CERO) — lo cual
  determinó el alcance de "Integración" (ver abajo).
- **Boleto** — `value_objects/sweepstakes_ticket_data.py::SweepstakesTicketData`,
  generaliza el payload real que
  `LoyaltyService._raffle_print_payload()` ya construye para
  `RaffleTicketESCPOSRenderer` (raffle_name/ticket_number/prize/
  draw_date/cliente/venta) — mismos campos, reutilizando `TicketParty`
  (SET-12) para el cliente en vez de un string suelto.
  `to_render_data()` alimenta el mismo `DocumentRendererPort.render()`
  que `TicketData`/`LabelData` ya alimentaban, sin cambiar su firma. 4
  códigos de sección nuevos en `DocumentSectionCode`
  (`RAFFLE_TITLE`/`TICKET_NUMBER`/`PRIZE`/`DRAW_DATE`), generalizando los
  4 bloques de `core/tickets/ticket_layout_config.py::RAFFLE_BLOCK_ORDER`
  que `DEFAULT_BLOCK_ORDER` (SET-12) todavía no cubría (el resto de
  `RAFFLE_BLOCK_ORDER` — logo/brand_header/customer/sale_info/qr/
  barcode/footer/legal — ya existía).
- **Plantilla** — sin entidad nueva: `DocumentTemplate`/
  `DocumentTemplateVersion` (SET-11) ya sirven para
  `DocumentType.SWEEPSTAKES_TICKET` (reservado desde SET-11, sin uso
  hasta esta SET) sin modificación. Probado con el ciclo de vida
  completo (DRAFT→...→ACTIVE) y persistencia contra SQLite real.
- **Integración con Sweepstakes** — `sweepstakes_ports.py::
  SweepstakesTicketPort` (Protocol), **sin implementación real, a
  propósito** — a diferencia del adaptador real de ruteo en SET-12
  (`DocumentOutputPrintRoutingClient`, seguro de construir porque
  device_management ya es UUIDv7-nativo de punta a punta), puentear
  `LoyaltyService` de forma segura implica decidir cómo/dónde traducir
  entre sus ids enteros legacy y el UUIDv7 que exige este bounded
  context — una decisión que le corresponde a quien migre el dominio de
  Lealtad/Sorteos, no algo que Document Output deba resolver
  unilateralmente reingenierizando un adaptador hoy. Documentado
  explícitamente, no un olvido — mismo criterio que
  `rendering_ports.DocumentRendererPort` (SET-11) y `hardware_ports.py`
  (SET-10).
- **Reimpresión** — **sin código nuevo**: `policies/reprint_policy.py`
  (SET-12) ya es agnóstico al `document_type` — un `PrintJob` de boleto
  de sorteo se reimprime exactamente igual que uno de ticket de venta.
  Probado explícitamente para confirmarlo, no asumido. Coherente con el
  propio `LoyaltyService`, que ya distingue `reprint_existing=True`
  (reimpresión explícita) de `reprint_existing=False` (idempotencia en el
  handler de venta completada) — reimprimir un boleto ya emitido es un
  flujo legítimo y existente, no un riesgo nuevo que esta SET deba
  mitigar con una regla adicional.
- **Nada de `LoyaltyService`/`RaffleTicketESCPOSRenderer` se tocó.** Esta
  SET construye la capacidad de dominio (boleto tipado, plantilla
  reutilizada, puerto de integración, reimpresión reutilizada) que
  permitiría eventualmente conectar Document Output al flujo real de
  emisión de boletos, pero no ejecuta ese corte — misma cautela que con
  los 3 pipelines de etiquetas en SET-14.

**Tests**: `tests/unit/document_output/` +18
(`test_sweepstakes_ticket_data.py`,
`test_sweepstakes_integration_and_reprint.py` — puerto con adaptador
falso, plantilla y reimpresión probadas como composición sin cambios).
`tests/integration/document_output/test_sweepstakes_document_persistence.py`
— 2 tests contra SQLite real. **Total tras SET-15 (Settings + Device
Management + Document Output): 716 tests verdes**
(`pytest tests/unit/settings/ tests/integration/settings/ tests/unit/device_management/ tests/integration/device_management/ tests/unit/document_output/ tests/integration/document_output/`).

---

## SET-14 (Etiquetas) — sin migración nueva — 2026-08-21

**Motivo:** SET-14 (Label templates, Variables, Serialización, Routing)
extiende `backend/domain/document_output/` para que las etiquetas
(lote/peso/transferencia/conteo/ajuste/producto — inventario y cárnico)
se compongan e impriman con la misma infraestructura que los tickets
(SET-11/12), en vez de un cuarto pipeline. **No genera una migración
216** — nota explícita para que quede claro que es una decisión, no un
olvido:

- **Investigación previa**: el repo ya tiene **tres** pipelines de
  etiquetas reales y distintos (de ahí que el plan de fases original
  describa SET-14 como el que "elimina los 3 pipelines"): (1)
  `backend/application/inventory/labels/` (INV-26) — el bueno: real,
  permission-gated (`LABEL_PRINT`/`LABEL_REPRINT`), auditado
  (`inventory_label_print_log`), emite eventos, pero con renderers
  *hardcodeados en Python* (`render_lot_label`, `render_weight_label`,
  ...), sin plantilla editable ni variables declaradas; (2)
  `labels/generador_etiquetas.py`/`labels/diseno_etiquetas.py` — v11,
  genera PNG/PDF/HTML con su propio sistema de tamaños (50x30/60x40/
  80x50mm) y taxonomía de tipos; (3) `modulos/etiquetas.py` — UI v13 de
  PyQt5 con su propia lista de campos y lógica embebida. Los tres siguen
  operando, no se tocaron.
- **Label templates** — **sin entidad nueva**: `DocumentTemplate`/
  `DocumentTemplateVersion` (SET-11) ya sirven para etiquetas sin
  modificación — una etiqueta es un documento como cualquier otro. Se
  agregaron 6 valores nuevos a `DocumentType` (`enums.py`):
  `LOT_LABEL`/`WEIGHT_LABEL`/`TRANSFER_LABEL`/`COUNT_LABEL`/
  `ADJUSTMENT_LABEL`/`PRODUCT_LABEL` — generalizan
  `backend/domain/inventory/enums.py::LabelType` (INV-26, mismas 6
  categorías, no inventadas), agrupados en `LABEL_DOCUMENT_TYPES`.
  Sufijo `_LABEL` para no confundirse con `TRANSFER_REQUEST`/
  `TRANSFER_DISPATCH`/`TRANSFER_RECEIPT` (papeleo de transferencia, no la
  etiqueta física de la caja/producto). `RenderFormat.ZPL` ya existía
  desde SET-11. Ninguna columna `document_type` tiene CHECK de valores
  fijos, así que esto no requirió tocar el esquema — probado con
  `DocumentTemplate`/`DocumentTemplateVersion` reales contra SQLite para
  los 6 tipos.
- **Variables** — `value_objects/label_variable.py::LabelVariable`
  (`name`/`var_type`/`required`) +
  `value_objects/label_variable_set.py::LabelVariableSet.assert_satisfied()`.
  Generaliza los parámetros de función hardcodeados de los renderers
  INV-26 (`product_name`, `net_weight`, `lot_code`, ...) en un esquema
  declarado y tipado (STRING/DECIMAL/INTEGER/DATE) que se puede validar
  antes de renderizar — atrapa una variable faltante o del tipo
  equivocado en construcción, no en la etiqueta ya impresa.
  **Deliberadamente sin tabla nueva**: el esquema de variables de una
  plantilla es, para este corte, una ayuda de validación que un caller
  construye junto al `content` de la plantilla — la misma decisión de
  no-persistencia que SET-12 tomó para `SectionLayout`.
- **Serialización** — `value_objects/label_data.py::LabelData`, la
  contraparte de `TicketData` (SET-12) para etiquetas. Generaliza
  `backend/domain/inventory/value_objects/label_document.py::LabelDocument`
  (INV-26) — mismos campos (`title`/`body_lines`/`barcode`/`qr_payload`/
  `entity_ref`/`copies`), Decimal de punta a punta, hacia el bounded
  context de Document Output para que cualquier módulo lo use, no solo
  Inventario. `create()` valida contra un `LabelVariableSet` opcional
  antes de construir. `to_render_data()` alimenta el mismo
  `DocumentRendererPort.render()` que `TicketData` ya alimentaba, sin
  cambiar su firma.
- **Routing** — **sin código nuevo**: `policies/ticket_routing_policy.py::
  create_routed_print_job()` (SET-12) ya es agnóstico al `document_type`
  — funciona para una etiqueta exactamente igual que para un ticket, sin
  modificación. Probado explícitamente para confirmarlo, no asumido.
- **Los 3 pipelines legacy no se tocaron.** SET-14 construye la
  capacidad de dominio (plantilla + variables + serialización + ruteo)
  que permitiría eventualmente consolidarlos, pero no ejecuta ese corte
  de producción — misma cautela que `print_job_log`/
  `ticket_delivery.py`/`ticket_printer_service.py` en SET-11/12: redirigir
  la impresión física de etiquetas reales (código de barras/QR/ZPL en
  impresoras Zebra/TSC reales) sin validación manual contra hardware no
  se hace sin autorización explícita.

**Tests**: `tests/unit/document_output/` +36 (`test_label_variables.py`,
`test_label_data.py`, `test_label_templates_and_routing.py` — prueba
composición sin cambios con `DocumentTemplate`/`DocumentTemplateVersion`
y `create_routed_print_job`). `tests/integration/document_output/
test_label_document_persistence.py` — 2 tests contra SQLite real
confirmando que los tipos de etiqueta persisten en las tablas ya
existentes de SET-11 sin ningún cambio de esquema. **Total tras SET-14
(Settings + Device Management + Document Output): 698 tests verdes**
(`pytest tests/unit/settings/ tests/integration/settings/ tests/unit/device_management/ tests/integration/device_management/ tests/unit/document_output/ tests/integration/document_output/`).

---

## 215_marketing_campaigns_schema — 2026-08-21

**Motivo:** SET-13 (Campaigns, Rules, FOMO policy, Loyalty summary)
completa `backend/domain/document_output/` con mensajes de marketing
configurables en el ticket, generalizando la lógica ya real y probada en
producción de `core/tickets/ticket_message_engine.py::
TicketMessageEngine.build_messages` (mensajes de fidelidad/FOMO/CTA
derivados de datos reales de negocio — nunca urgencia inventada) en datos
persistidos que un administrador puede gestionar sin desplegar código.

- **Campaigns** — `entities/marketing_campaign.py::MarketingCampaign`:
  `code`, `category` (LOYALTY/FOMO/CTA — mismo vocabulario que
  `TicketMessage.category` legacy), `message_template` (con placeholders
  `{metric}`, igual que los `.format(remaining=...)` del motor legacy),
  `priority`, `requires_customer`, `rules`, `active`. Persistida en la
  tabla nueva `marketing_campaigns` (migración 215) — a diferencia de
  Secciones/DTO (SET-12, deliberadamente sin tabla), un catálogo de
  campañas que un admin necesita crear/editar/activar sí encaja con el
  patrón de catálogo persistido que `DocumentTemplate` (SET-11) ya
  estableció.
- **Rules** — `value_objects/campaign_rule.py::CampaignRule`: generaliza
  los umbrales fijos que el motor legacy tenía hardcodeados en Python
  (`goal_remaining <= 5`, `points_to_reward <= 50`, `promo_days_left <= 4`)
  en datos configurables — `metric`/`comparator`/`threshold`, Decimal de
  punta a punta. `MarketingCampaign.matches(context)` exige que **todas**
  las reglas de una campaña pasen (AND) más, si `requires_customer=True`,
  que el contexto reporte un cliente presente. Serializadas como
  `rules_json` en la fila de su propia campaña — sin tabla de reglas
  separada, no hay necesidad de referenciarlas independientemente.
- **FOMO policy** — `policies/marketing_claim_validation_policy.py`. La
  regla de "FOMO responsable": `assert_responsible_claim()` rechaza toda
  campaña de categoría FOMO que no tenga ninguna `CampaignRule` — un
  mensaje de urgencia/escasez sin ninguna condición real detrás
  imprimiría siempre, exactamente el patrón manipulador que el motor
  legacy nunca hizo (todo mensaje FOMO legacy viene de un dato de negocio
  real: saldo de puntos, días de vigencia de promo, compras faltantes).
  `select_messages()` generaliza el cap de frecuencia que el motor legacy
  aplicaba solo a FOMO (`ticket_fomo_max_messages`, default 2) a las tres
  categorías, configurable por categoría — imprimir cada mensaje elegible
  cada vez haría el ticket ilegible y le quitaría fuerza a la persuasión
  que se busca agregar.
- **Loyalty summary** — `value_objects/loyalty_summary.py::LoyaltySummary`,
  generaliza `TicketLoyaltyInfo` legacy (puntos ganados/saldo/nivel).
  Puramente estado de cuenta factual — no es un "claim" sujeto a la FOMO
  policy. `TicketData` (SET-12) se extiende con dos campos nuevos,
  `loyalty: LoyaltySummary | None = None` y `messages: tuple[str, ...] = ()`
  (los mensajes finales ya seleccionados/limitados por `select_messages`),
  ambos con default vacío — **no rompe ningún caller de SET-12 existente**,
  confirmado re-corriendo los 115 tests de `tests/unit/document_output/`
  previos a este SET antes de escribir los nuevos. `to_render_data()` se
  actualizó para incluir ambos campos en el `data: dict` hacia
  `DocumentRendererPort.render()`.
- **DTO específico de Ventas intacto** — igual que en SET-12, este DTO
  nuevo es para módulos sin uno propio; `backend/application/sales/dto.py`
  no se tocó.

**Tests**: `tests/unit/document_output/` +40 (`test_marketing_campaign.py`,
`test_marketing_claim_validation_policy.py`,
`test_loyalty_summary_and_ticket_data.py`). `tests/integration/
document_output/test_marketing_campaign_repository.py` — 9 tests contra
SQLite real (round-trip preservando reglas, `code` único, upsert,
múltiples reglas en orden, listados activos/por categoría). **Total tras
SET-13 (Settings + Device Management + Document Output): 662 tests
verdes**
(`pytest tests/unit/settings/ tests/integration/settings/ tests/unit/device_management/ tests/integration/device_management/ tests/unit/document_output/ tests/integration/document_output/`).

---

## SET-12 (Tickets) — sin migración nueva — 2026-08-21

**Motivo:** SET-12 (Secciones, DTO, Routing, Reimpresión) completa
`backend/domain/document_output/` con lo que hace falta para que un
módulo cualquiera (no solo Ventas) componga y enrute un ticket real
usando la infraestructura de SET-11/SET-8, sin construir ningún esquema
nuevo — **no genera una migración 215**, nota explícita para que quede
claro que es una decisión, no un olvido:

- **Secciones** — `enums.DocumentSectionCode` (13 códigos — LOGO,
  BRAND_HEADER, SALE_INFO, CUSTOMER, ITEMS, TOTALS, PAYMENT, LOYALTY,
  FOMO, QR, BARCODE, FOOTER, LEGAL) + `value_objects/document_section.py::
  DocumentSection` + `value_objects/section_layout.py::SectionLayout`.
  Generaliza el vocabulario de bloques ya probado en producción por
  `core/tickets/ticket_layout_config.py::DEFAULT_BLOCK_ORDER` (mismos 13
  nombres, no inventados) en un value object de dominio puro —
  `SectionLayout` valida que no haya códigos duplicados y expone
  `ordered()`/`enabled_codes()`. **Deliberadamente sin tabla nueva**: el
  arreglo de secciones de una plantilla es, para este corte, dato que el
  propio `content` de `DocumentTemplateVersion` ya codifica — la misma
  decisión de no-persistencia que SET-9 tomó para `WeightReading`/
  `StabilityPolicy`.
- **DTO** — `value_objects/{ticket_line,ticket_totals,ticket_payment_summary,
  ticket_party,ticket_data}.py`. Generaliza el `TicketPrintModel` legacy
  (float, en `core/tickets/ticket_print_model.py`) en un DTO Decimal de
  punta a punta que cualquier módulo puede construir antes de llamar a
  `rendering_ports.DocumentRendererPort.render()` (§27). Dos invariantes
  aritméticas reales, no cosméticas: `TicketTotals` exige
  `total == subtotal - discount`, y `TicketData` exige que la suma de
  `lines[].line_total` coincida con `totals.subtotal` — ambas atrapan en
  tiempo de construcción la clase de bug real "se agregó una línea a la
  venta pero nunca llegó al total impreso". `TicketData.to_render_data()`
  serializa Decimal como string (nunca float) hacia el `data: dict` que
  `DocumentRendererPort.render()` ya esperaba desde SET-11 — la firma del
  Protocol no cambió, solo se agregó una capa tipada por encima.
  **La DTO específica de Ventas (`backend/application/sales/dto.py::
  SaleReceiptDataDTO`, de SALES-17) queda intacta** — este DTO nuevo es
  para módulos que aún no tienen el suyo, no un reemplazo forzado.
- **Routing** — `routing_ports.py::PrintRouteResolverPort` (Protocol) +
  `policies/ticket_routing_policy.py::create_routed_print_job()` (compone
  `PrintJob.create()` + resolución + `assign_route()` como una sola
  operación garantizada). A diferencia de `rendering_ports.py` (SET-11) y
  `hardware_ports.py` (SET-10), que se quedaron como contratos puros
  porque generar bytes reales o hablar con hardware real requiere una
  librería/vendor concreto para validar, la resolución de rutas es lógica
  pura más lecturas de SQLite — sin esa dependencia externa — así que esta
  vez sí se construyó un adaptador real:
  `backend/infrastructure/integrations/document_output_print_routing_client.py::
  DocumentOutputPrintRoutingClient`, que delega enteramente en
  `device_management.policies.print_routing_policy.resolve_route()`/
  `select_device()` (SET-8) y sus repositorios reales
  (`SqlitePrintRouteRepository`, `SqliteDeviceRepository`) — mismo patrón
  que `backend/infrastructure/integrations/sales_cash_drawer_client.py`:
  delega en el bounded context dueño, no reimplementa su lógica, y no
  traduce las excepciones de vuelta (`PrintRouteNotFoundError`/
  `NoAvailablePrinterError` propagan tal cual).
- **Reimpresión** — `policies/reprint_policy.py::assert_reprintable()`/
  `request_reprint()`, construido sobre `PrintJob.create_reprint()`
  (SET-11), sin modificarlo. `create_reprint()` sigue siendo la operación
  mecánica de bajo nivel (permite reimprimir desde cualquier estado, a
  propósito — ver su test en SET-11); `request_reprint()` es la entrada
  más estricta que un caller debería usar: exige que el job original ya
  haya salido de su primer intento en curso (PENDING/RENDERING/READY/
  PRINTING rechazados) — PRINTED, FAILED, CANCELLED y DEAD_LETTER sí
  califican. La autorización (el equivalente de `POS.ticket.reimprimir`
  de Ventas para cada módulo) queda deliberadamente fuera de esta policy
  — es una decisión de capa de aplicación por módulo, la misma que
  `backend/application/sales/use_cases/receipt_use_cases.py::
  ReprintReceiptUseCase` ya aplica para Ventas.
- **`ticket_delivery.py`/`ticket_printer_service.py`: no eliminados en
  este corte.** La tabla del plan de fases describe SET-12 como el que
  "elimina" estos duplicados legacy; esta SET construye la capacidad de
  dominio que lo haría posible pero no ejecuta el corte de producción —
  cortar rutas de impresión térmica reales en vivo sin haberlas probado
  contra hardware físico es un riesgo que este refactor no toma sin
  autorización explícita y validación manual, la misma cautela aplicada a
  no tocar `print_job_log` en SET-11.

**Tests**: `tests/unit/document_output/` +51 (`test_document_sections.py`,
`test_ticket_data_dto.py`, `test_ticket_routing_policy.py` — con un
resolver falso, sin importar device_management —, `test_reprint_policy.py`).
`tests/integration/document_output/test_print_routing_client.py` — 6
tests contra SQLite real probando el adaptador real
(`DocumentOutputPrintRoutingClient`): dispositivo primario activo,
failover a dispositivo de respaldo cuando el primario está en
mantenimiento, la ruta más específica gana, error cuando no hay ruta y
error cuando ningún dispositivo de la cadena está disponible, más
`create_routed_print_job()` compuesto de punta a punta. **Total tras
SET-12 (Settings + Device Management + Document Output): 613 tests
verdes**
(`pytest tests/unit/settings/ tests/integration/settings/ tests/unit/device_management/ tests/integration/device_management/ tests/unit/document_output/ tests/integration/document_output/`).

---

## 214_document_output_schema — 2026-08-21

**Motivo:** SET-11 (Templates, Versiones, Renderers, PrintJobs, Worker,
Tests) abre un **segundo bounded context nuevo**,
`backend/domain/document_output/` (el primero fue
`backend/domain/device_management/` en SET-7), gobernando qué se imprime,
con qué plantilla, en qué formato, y el ciclo de vida de cada trabajo de
impresión (§24-27).

- **Templates** — `DocumentTemplate`: identidad/metadata mayormente
  estática de una *familia* de plantillas por `document_type` (20 valores
  cubiertos, desde `SALE_TICKET` hasta `SWEEPSTAKES_TICKET` — el
  inventario completo de documentos imprimibles del ERP). Mismo rol que
  `ConfigurationDefinition` cumple en Settings: el contenido versionado en
  sí vive aparte.
- **Versiones** — `DocumentTemplateVersion`: máquina de 7 estados (DRAFT →
  PENDING_APPROVAL → APPROVED → ACTIVE → INACTIVE/EXPIRED → ARCHIVED).
  Deliberadamente **sin estado REJECTED terminal** — a diferencia de
  `ConfigurationValueStatus` en Settings, un `reject(reason)` regresa la
  versión a DRAFT para revisión, no la mata (§26 no exige un
  rechazo terminal). Toda modificación crea versión nueva vía
  `create_next_version()` (encadenada por `previous_version_id`, nunca una
  edición in-place de una versión ACTIVE) — mismo principio que
  `ConfigurationValue.create_next_version()`. La supersesión de "cuál
  versión está activa" vive en `policies/template_activation_policy.py::
  activate_version()`, no en la entidad — misma división de
  responsabilidades que `configuration_rollback_policy.py` (la entidad
  ofrece transiciones válidas de un solo objeto; una policy coordina dos
  objetos). Reforzado con un índice único parcial
  (`ux_dtv_template_active ... WHERE status='ACTIVE'`) — a lo sumo una
  versión ACTIVE por plantilla, verificado con un test de integración que
  confirma el `IntegrityError` cuando se intenta activar una segunda
  versión sin pasar por la policy de supersesión.
- **PrintJobs** — `PrintJob`: máquina de 8 estados (PENDING → RENDERING →
  READY → PRINTING → PRINTED, con FAILED/CANCELLED/DEAD_LETTER como
  ramas). Nunca se imprime directo desde UI (§26/§70) — todo trabajo de
  impresión pasa por esta entidad. `start_printing()` exige
  `printer_device_id` ya asignado (probado explícitamente: falla sin él,
  funciona tras `assign_route()`). Reimpresión (§33) es
  `create_reprint(reason)` — siempre un job **nuevo**, encadenado vía
  `reprint_of_job_id`, nunca una mutación del original; exige motivo no
  vacío.
- **Worker** — `policies/print_job_queue_policy.py`: la *decisión* de cuál
  trabajo PENDING sigue (`select_next_job` — prioridad URGENT/HIGH/NORMAL/
  LOW, empate roto por FIFO de `requested_at`) y si un trabajo FAILED se
  reintenta o se mueve a DEAD_LETTER (`should_retry`/
  `retry_or_dead_letter`). El *loop* de fondo real que desencola, renderiza
  y envía a la impresora (`backend/infrastructure/printing/print_worker.py`
  en el layout del prompt maestro) es infraestructura — trabajo de una SET
  posterior, no lógica de dominio.
- **Renderers** — `rendering_ports.py::DocumentRendererPort`: Protocol
  puro (`render(template_version, data) -> bytes`), **sin implementación
  real** — a propósito. Generar bytes ESC/POS reales o un PDF real es un
  trabajo dependiente de formato/librería/vendor que necesita un objetivo
  real contra el cual validar, la misma razón por la que
  `hardware_ports.py` (SET-10) se quedó como contrato puro. Probado con un
  renderer falso (`test_rendering_ports_composition.py`, mismo patrón que
  `test_hardware_ports_composition.py`) que demuestra la composición
  plantilla+datos→bytes, incluyendo que un fallo de renderizado propaga la
  excepción en vez de devolver salida parcial.
- **Esquema** — `document_templates`, `document_template_versions`,
  `print_jobs` (migración 214). Depende de las tablas de Device Management
  (`devices` de 211, `print_routes` de 212) — `print_jobs.printer_device_id`
  y `print_jobs.print_route_id` son FKs nullable hacia ellas (un job se
  crea antes de que se decida el ruteo; `assign_route()` ocurre después de
  `create()`). Este orden de dependencia (211-213 antes de 214) es
  deliberado, igual que Device Management dependió de Settings en su
  momento.
- **operation_id como llave de idempotencia** — `print_jobs.operation_id`
  (nullable, único cuando no-NULL) sigue exactamente el patrón de
  `configuration_values.operation_id` en Settings: es una columna
  *solo de persistencia*, nunca un campo de la entidad `PrintJob` —
  `save(job, operation_id=...)` y `get_by_operation_id()` en el
  repositorio. Se descubrió al escribir el repositorio: el primer
  borrador reutilizaba `source_document_id` como si fuera la llave de
  idempotencia, lo cual es semánticamente incorrecto (un mismo documento
  origen puede generar más de un `PrintJob` legítimamente — p. ej. una
  reimpresión); se corrigió para replicar el patrón real de Settings antes
  de escribir los tests de integración.

**Tests**: `tests/unit/document_output/` — 64 tests
(`test_document_template_and_version.py`: template + máquina de estados de
versión + `template_activation_policy`; `test_print_job_lifecycle.py`:
máquina de estados completa de `PrintJob` + `create_reprint()`;
`test_print_job_queue_policy.py`: selección por prioridad/FIFO +
reintento/dead-letter; `test_rendering_ports_composition.py`: composición
de `DocumentRendererPort` con un renderer falso). `tests/integration/
document_output/test_document_output_repositories.py` — 13 tests contra
SQLite real (round-trip de los 3 repositorios, upsert, listados filtrados,
supersesión de versión activa vía policy + su índice único, ciclo de vida
completo de un `PrintJob` persistido, `operation_id` como idempotencia +
su índice único, reimpresión persistida como job independiente). **Total
tras SET-11 (Settings + Device Management + Document Output): 556 tests
verdes**
(`pytest tests/unit/settings/ tests/integration/settings/ tests/unit/device_management/ tests/integration/device_management/ tests/unit/document_output/ tests/integration/document_output/`).

---

## SET-10 (Cajones y terminales) — sin migración nueva — 2026-08-21

**Motivo:** SET-10 (Gateways, Asignación, Pruebas, Seguridad) extiende
`backend/domain/device_management/` con lo específico de cajones de
dinero y terminales de pago (§18/§20/§23, §60). A diferencia de SET-7/8/9,
**no genera una migración 214** — nota explícita para que quede claro que
es una decisión, no un olvido:

- **Asignación** — `WorkstationDeviceAssignment` + `device_assignment_policy`
  (SET-7) ya cubren `CASH_DRAWER`/`PAYMENT_TERMINAL` genéricamente
  (`ROLE_COMPATIBLE_DEVICE_TYPES` ya los mapeaba desde SET-7). Este SET
  solo agrega tests que lo confirman explícitamente, no código nuevo de
  persistencia.
- **Pruebas** — `DeviceTestResult` (SET-9, generalizado a propósito)
  cubre pruebas de apertura de cajón / conectividad de terminal sin
  cambios; probado con `test_type='OPEN_TEST'`/`'CONNECTIVITY'`.
- **Perfiles** — `assert_valid_cash_drawer_profile()` (exige capacidad
  `DRAWER_PULSE`) y `assert_valid_payment_terminal_profile()` (exige al
  menos una de `CARD_SWIPE`/`CARD_CHIP`/`CARD_CONTACTLESS`/`ACCEPT_CASH`/
  `DISPENSE_CASH`) — dominio puro, sin tabla nueva (reutilizan
  `device_profiles` de SET-7 tal cual).
- **Gateways** — `hardware_ports.py` (nuevo): `CashDrawerGatewayPort`/
  `PaymentTerminalGatewayPort`, Protocols que una infraestructura real
  implementaría más adelante — **sin escribir I/O serial/red real**, a
  propósito. Construir drivers reales de hardware (abrir un cajón físico,
  hablar con la API de una terminal de pago real como Clip/Mercado Pago
  Point/Stripe Terminal) es un tipo de trabajo distinto y más riesgoso —
  requiere hardware real, SDKs de proveedor y credenciales para probar
  contra algo de verdad — que construir capas de dominio puras; se dejó
  fuera de este corte a propósito, consistente con cómo SET-7/8/9 tampoco
  tocaron E/S real. Probado con un gateway falso
  (`test_hardware_ports_composition.py`) que demuestra la composición
  autorización→gateway sin hardware.
- **Seguridad** — la pieza genuinamente nueva de este SET:
  `CashDrawerOpenRequest` (VO, forma válida de una solicitud de apertura)
  + `policies/cash_drawer_security_policy.py::assert_can_open()`
  (¿está autorizada?). Codifica el control anti-robo real que la
  auditoría SET-0 encontró como permiso legacy
  (`CASH_DRAWER_OPEN_WITHOUT_SALE`,
  `docs/refactor/settings_legacy_inventory.md` §7): abrir un cajón **sin**
  una venta asociada exige un motivo explícito; con venta asociada, no.
  Separación deliberada forma-válida vs. autorizada (mismo patrón que
  `ConfigurationValue`/`ConfigurationApprovalPolicy` en Settings). Un caso
  de prueba expuso que la primera versión de `assert_can_open()` solo
  comprobaba veracidad del campo `reason`, no su contenido — un `reason`
  de puros espacios se habría aceptado si alguien construía el VO sin
  pasar por `.create()`; se corrigió antes de cerrar el corte.

**Sin cambios de esquema.** No hay migración 214. Todo lo de esta SET
persiste en tablas que SET-7/9 ya crearon.

**Tests**: `test_cash_drawer_and_terminal_profile_policy.py`,
`test_cash_drawer_security_policy.py`, `test_cash_drawer_terminal_assignment.py`,
`test_hardware_ports_composition.py` (dominio) +
`test_cash_drawer_terminal_integration.py` (infraestructura — registro,
asignación, prueba y autorización de apertura de extremo a extremo contra
SQLite real, incluida la reconfirmación de que el índice único parcial de
asignación activa de SET-7 aplica también a estos dos tipos de
dispositivo). **Total tras SET-10 (Settings + Device Management): 479
tests verdes**
(`pytest tests/unit/settings/ tests/integration/settings/ tests/unit/device_management/ tests/integration/device_management/`).

---

## 213_scale_reader_diagnostics_schema — 2026-08-21

**Motivo:** SET-9 (Básculas y lectores: puertos, protocolos,
estabilidad, diagnóstico) — extiende `backend/domain/device_management/`
con lo específico de básculas y lectores de código de barras/QR (§22).

**Puertos**: no se creó una nueva VO — se reutilizó `SerialPortProfile`
(SET-7) tal cual, probado explícitamente con una báscula (COM4, 4800
baud, paridad E, 7 bits) para confirmar que el mismo tipo sirve tanto
para impresoras seriales (SET-8) como para básculas.

**Protocolos**: `ScaleProtocol` (6 valores: `TOLEDO_STANDARD`, `SICS`,
`NCI`, `CONTINUOUS`, `ON_DEMAND`, `VIRTUAL`) validado por
`policies/scale_profile_policy.py::assert_valid_scale_profile()`, que
también exige la capacidad `WEIGH` en cualquier perfil de báscula —
sin ella, un perfil "de báscula" no puede pesar nada, así que se rechaza
en la creación, no se descubre en producción. `policies/reader_profile_policy.py::assert_valid_reader_profile()`
hace lo mismo para `BARCODE_SCANNER`→`SCAN_1D` y `QR_SCANNER`→`SCAN_2D`
(y prueba explícitamente que un lector 1D no satisface el requisito de
uno 2D — no son intercambiables).

**Estabilidad**: `WeightReading` (Decimal, nunca float; rechaza negativos)
+ `StabilityPolicy` (mínimo de lecturas estables consecutivas, tolerancia,
espera máxima) +
`policies/scale_stability_policy.py::evaluate_stability()` — función pura
que exige que las últimas N lecturas estén todas marcadas `stable=True`
**y** coincidan entre sí dentro de la tolerancia antes de confirmar un
peso. Cubre el caso "doble lectura" (dos lecturas que ambas dicen
`stable=True` pero no coinciden — debe rechazarse igual, una báscula
puede oscilar entre valores mientras el usuario acomoda el producto) y el
caso de ventana deslizante (una lectura vieja/inestable fuera de la
ventana requerida no debe bloquear la confirmación). Deliberadamente
**no persistido**: la política correcta de estabilidad es candidata a
vivir como `ConfigurationValue` (Settings, SET-2) resuelta por
sucursal/dispositivo, no un campo fijo en el schema de Device Management.

**Diagnóstico**: `DeviceTestResult`, entidad **generalizada** (no
`ScaleTestResult`/`ReaderTestResult` separados) — con dos casos de uso
reales ya en la mano (básculas y lectores, además de que cajones/
terminales de SET-10 previsiblemente necesitan lo mismo), generalizar
ahora es la elección correcta; `PrinterTestResult` (SET-8, tabla
`printer_test_results`, ya en producción vía migración 212) se deja tal
cual — deshacerla para unificar retroactivamente no vale el churn de una
migración de por medio, documentado explícitamente en el docstring de
`DeviceTestResult` para que quede claro que es una decisión, no un
descuido.

**Esquema**: migración `213_scale_reader_diagnostics_schema` — solo
`device_test_results` (FK a `devices`); ninguna tabla nueva para
`WeightReading`/`StabilityPolicy` (ver más arriba).

**Infraestructura**: `SqliteDeviceTestResultRepository`.

**Tests**: `test_weight_reading_and_stability.py` (incluye el caso "doble
lectura" y el de ventana deslizante), `test_scale_and_reader_profile_policy.py`,
`test_device_test_result_entity.py` (dominio) +
`test_device_test_result_repository.py` (infraestructura — incluida
prueba de que un mismo dispositivo puede acumular tests de distintos
`test_type`, a diferencia de `PrinterTestResult`). **Total tras SET-9
(Settings + Device Management): 426 tests verdes**
(`pytest tests/unit/settings/ tests/integration/settings/ tests/unit/device_management/ tests/integration/device_management/`).

---

## 212_print_routing_schema — 2026-08-21

**Motivo:** SET-8 (Impresoras: perfiles, routing, failover) — extiende
`backend/domain/device_management/` (SET-7) con lo específico de
impresión: validación de perfil de impresora (§23), enrutamiento de
documentos a impresora (§25) y registro de pruebas de impresión (§21/§23).

**Perfiles**: no se tocó `DeviceProfile` (SET-7, ya construido) — se
agregó `policies/printer_profile_policy.py::assert_valid_printer_profile()`,
una validación adicional aplicable solo a perfiles de impresora
(`THERMAL_PRINTER`/`LABEL_PRINTER`/`DOCUMENT_PRINTER`/`CARD_PRINTER`):
`paper_profile` debe ser uno de los 8 perfiles canónicos de §23
(`PAPER_58MM`…`VIRTUAL`) y `protocol` uno de 6 protocolos reconocidos
(`ESC_POS`, `ZPL`, `PDF`, `HTML`, `RAW`, `VIRTUAL`) — aplicando en código
el "no asumir que toda impresora es ESC/POS" de §23, no solo
documentándolo.

**Routing**: `PrintRoute` (`document_type` + `primary_device_id` +
`fallback_device_ids` ordenados, con ámbito opcional
empresa/sucursal/estación/módulo/canal por §25).
`policies/print_routing_policy.py::resolve_route()` elige, entre las
rutas activas que igualan `document_type` y encajan en el contexto, la
más específica (más dimensiones de ámbito fijadas) — mismo principio de
"más específico gana" que `ConfigurationResolutionService` (SET-2/4),
implementado de forma independiente porque las dimensiones de ruteo
(módulo/canal) no son la misma jerarquía de ámbitos de Configuración.
`document_type` se mantiene como string libre validado, no un enum
importado desde `document_output` (SET-11 aún no existe) — evita una
dependencia cruzada prematura en el sentido equivocado.

**Failover**: `select_device()` recorre primary→fallback y devuelve el
primer dispositivo para el que `is_available(device_id)` sea verdadero —
la función de disponibilidad la inyecta quien llama (la futura
infraestructura de diagnóstico, no este módulo), manteniendo el ruteo
puro/testeable sin hardware real. Devuelve `DeviceSelection` con
`used_failover` explícito, no solo el id elegido — para que el "usamos el
respaldo" sea observable, no incidental.

**Test**: `PrinterTestResult`, registro histórico append-only (nunca se
sobreescribe un intento anterior) de pruebas de impresión — éxito/fallo,
mensaje, quién y cuándo.

**Esquema**: migración `212_print_routing_schema` (separada de 211, misma
razón que siempre). `print_routes.primary_device_id`/
`printer_test_results.device_id` FK a `devices` (211);
`print_routes.branch_id`/`workstation_id` FK opcionales a
`sucursales`/`workstations`. Índice único
`(document_type, COALESCE(branch_id,''), COALESCE(workstation_id,''), COALESCE(module,''), COALESCE(channel,''))`
impide dos rutas idénticas en ámbito exacto — probado en integración
(mismo ámbito exacto choca; mismo `document_type` en sucursales distintas
no choca).

**Infraestructura**: `SqlitePrintRouteRepository`,
`SqlitePrinterTestResultRepository`.

**Tests**: `tests/unit/device_management/test_printer_profile_policy.py`,
`test_print_route_and_routing_policy.py`, `test_printer_test_result_entity.py`
+ `tests/integration/device_management/test_print_routing_repositories.py`.
**Total tras SET-8 (Settings + Device Management): 365 tests verdes**
(`pytest tests/unit/settings/ tests/integration/settings/ tests/unit/device_management/ tests/integration/device_management/`).

---

## 211_device_management_schema — 2026-08-21

**Motivo:** SET-7 (Device Management) — primer bounded context nuevo
fuera de `backend/domain/settings/`: `backend/domain/device_management/`
(§18-20, §23). Persiste `DeviceProfile`, `Device`,
`WorkstationDeviceAssignment`.

**Decisión de alcance (misma lógica que SET-5/`sucursales`)**: esta
migración **no toca `hardware_config`** (la tabla legacy, PK en `tipo`
solo, sin ámbito de sucursal/estación — ver auditoría SET-0). Sus
consumidores en vivo (`core/services/hardware_service.py`,
`modulos/config_hardware.py`, `hardware/*.py`,
`backend/infrastructure/integrations/sales_scale_client.py`) siguen
funcionando sin cambios; cortarlos hacia el modelo nuevo es trabajo de
SET-8/9/10 (impresoras/básculas/cajones específicamente), no de este
corte fundacional.

**Qué hace:** crea `device_profiles` (perfil de conexión/capacidades
reutilizable — 13 `device_type`, 8 `connection_type`), `devices`
(instancia concreta, FK a `sucursales` y a `device_profiles`, mismos 5
estados que `Workstation`/Cash Register), `workstation_device_assignments`
(FK a `workstations` de la migración 210 y a `devices`; 11 roles de §20).

**Idempotencia/conflicto (§62)**: `UNIQUE(device_id, workstation_id, role)`
evita filas idénticas duplicadas; el índice único parcial
`(workstation_id, role) WHERE active=1` es el que realmente impide que
dos dispositivos distintos sean "el" impresor principal de una estación
al mismo tiempo — probado explícitamente (asignar un segundo dispositivo
al mismo rol mientras el primero sigue activo falla con
`IntegrityError`; después de `unassign()` la reasignación funciona).

**Seguridad (§19)**: `ConnectionProfile.create()` **rechaza en el
dominio** cualquier `extra_parameters` con una clave de apariencia de
secreto (`password`, `token`, `secret`, `credential`, `apikey`,
`private_key`, `auth*`) — antes de que el valor llegue a la fila. La
única forma legítima de referenciar una credencial es
`credential_reference`, un nombre hacia `SecretStoreGateway`
(`backend/security/secrets/`), nunca el secreto en sí.

**Infraestructura**: `SqliteDeviceProfileRepository` (serializa
`ConnectionProfile`/`SerialPortProfile`/`NetworkEndpoint`/`DeviceCapability`
a JSON), `SqliteDeviceRepository`, `SqliteWorkstationDeviceAssignmentRepository`
en `backend/infrastructure/db/repositories/device_management/`.

**Tests**: `tests/unit/device_management/` (3 archivos: perfil+VOs de
conexión con el guardia de secretos probado con 6 variantes de clave,
entidad Device con máquina de estados, asignación + política de
compatibilidad rol↔tipo con cobertura de los 11 roles) +
`tests/integration/device_management/test_device_management_repositories.py`
(round-trip NETWORK y SERIAL, FKs a `sucursales`/`device_profiles`/
`workstations`, unicidad de `code`, conflicto de asignación activa).
**Total tras SET-7 (Settings + Device Management): 312 tests verdes**
(`pytest tests/unit/settings/ tests/integration/settings/ tests/unit/device_management/ tests/integration/device_management/`).

---

## 210_settings_workstation_schema — 2026-08-21

**Motivo:** SET-6 (Estaciones) — persiste `Workstation`
(`backend/domain/settings/entities/workstation.py`). Separada de 208/209
por la misma razón: no reabrir una migración ya "cerrada".

**Qué hace:** crea `workstations` (PK `id` UUIDv7, `branch_id` FK a
`sucursales(id)` — igual que `branch_profiles`, una estación siempre
pertenece a una sucursal ya existente —, `code` UNIQUE, `workstation_type`
y `status` con `CHECK IN (...)` de los 11 tipos y 5 estados de §17. Los 5
estados (`ACTIVE/INACTIVE/MAINTENANCE/BLOCKED/RETIRED`) son
deliberadamente los mismos que `cash_registers`/`pos_terminals` ya usan
(`migrations/standalone/175_cash_register_bounded_context_schema.py`) —
un solo vocabulario de ciclo de vida de hardware/estación en todo el
repo, no dos.

**Dominio**: `Workstation.check_in()` es el camino de "Registro"/
heartbeat (rechazado si la estación está BLOCKED o RETIRED); `is_online()`
compara `last_seen_at` contra un umbral que el llamador decide — nada de
TTL hardcodeado en el dominio; RETIRED es terminal (ninguna transición
sale de ahí, ni siquiera otra retirada).

**Infraestructura**: `SqliteWorkstationRepository` implementando el
Protocol nuevo `WorkstationRepositoryPort`.

**Tests**: `tests/unit/settings/test_workstation_entity.py` (máquina de
estados completa, check-in/is_online/offline_enabled) +
`tests/integration/settings/test_workstation_repository.py`
(persistencia real, FK a `sucursales`, unicidad de `code`,
`list_by_branch`/`list_active`). Total Configuration Governance tras
SET-6: **235 tests verdes**
(`pytest tests/unit/settings/ tests/integration/settings/`).

---

## 209_settings_company_branch_profile_schema — 2026-08-21

**Motivo:** SET-5 (Empresa y sucursales) — persiste `CompanyProfile` y
`BranchProfile` (`backend/domain/settings/entities/`). Separada de la
208 a propósito (no una expansión de esa migración ya "cerrada" —
ver el docstring de `create_company_branch_profile_schema`).

**Decisión de alcance (importante, léase antes de tocar `sucursales`)**:
`BranchProfile` **no reemplaza** la tabla `sucursales` — esa tabla es la
identidad de sucursal viva, referenciada por FK desde ~20 bounded
contexts ya construidos (ventas, inventario, caja, RRHH, ...). Cortarla
es una migración cross-cutting dedicada, fuera de alcance de un SET de
Configuración. `branch_profiles.branch_id` es una FK 1:1 hacia
`sucursales(id)` — `BranchProfile` extiende con los campos que
`sucursales` nunca tuvo (ticket_header/footer, social_links,
map_reference, warehouse_ids, default_workstation_profile), reutilizando
la identidad UUIDv7 existente en vez de crear una segunda. `CompanyProfile`
sí es enteramente nuevo — no existía tabla "empresa" alguna en el schema
legacy (solo `rfc_empresa` disperso en cada fila de `sucursales`, según
la auditoría SET-0).

**Qué hace:** crea `company_profiles` (PK `id` UUIDv7, `default_currency`
CHECK longitud 3, sin restricción de singleton — "multiempresa futuro" del
prompt maestro) y `branch_profiles` (PK `id` UUIDv7 que **es** el mismo
valor que `branch_id`, FK a `sucursales(id)`, `code` UNIQUE,
`CHECK` cruzado opening_time/closing_time y map_latitude/map_longitude).

**Infraestructura**: `SqliteCompanyProfileRepository`,
`SqliteBranchProfileRepository` en
`backend/infrastructure/db/repositories/settings/`, implementando los
Protocols nuevos en `repository_ports.py`
(`CompanyProfileRepositoryPort`, `BranchProfileRepositoryPort`).

**Tests**: `tests/unit/settings/test_company_and_branch_profile_entities.py`
(dominio puro: `AssetReference`, `MapReference`, ambas entidades) +
`tests/integration/settings/test_company_and_branch_profile_repositories.py`
(persistencia real, incluida verificación de que `branch_id` sin fila
`sucursales` correspondiente falla con `IntegrityError`). Total
Configuration Governance tras SET-5: **205 tests verdes**
(`pytest tests/unit/settings/ tests/integration/settings/`).

---

## 208_settings_configuration_governance_schema — 2026-08-21

**Motivo:** SET-3 (esquema born-clean del bounded context Settings/
Configuración) — persiste el dominio puro construido en SET-2
(`backend/domain/settings/`): `ConfigurationDefinition` y
`ConfigurationValue`. No es una migración de `configuraciones`/
`hardware_config` (esas tablas legacy se retiran en un SET posterior,
cuando `device_management`/`document_output` existan para absorber lo que
aún les falta) — es un bounded context nuevo, sin puente ni escritura dual
con nada existente.

**Qué hace:** crea `configuration_definitions` (PK `id` UUIDv7,
`key` UNIQUE, `value_type`/`default_scope` con `CHECK IN (...)`
enumerando los 19/17 valores canónicos de `ValueType`/`ScopeType`) y
`configuration_values` (PK `id` UUIDv7, FK a `configuration_definitions`,
`CHECK` cruzado GLOBAL⇔scope_id NULL, `CHECK(effective_to IS NULL OR
effective_to > effective_from)`). Dos índices únicos hacen cumplir en
schema lo que el dominio ya exige en memoria: `(definition_id, scope_type,
COALESCE(scope_id,''), version)` — un número de versión por linaje
(definición, ámbito), con `COALESCE` porque SQLite trata NULLs distintos
como no-colisionantes y GLOBAL siempre tiene `scope_id` NULL — y
`(operation_id) WHERE operation_id IS NOT NULL` para escritura idempotente
(§62).

**Infraestructura nueva**: `backend/infrastructure/db/repositories/settings/`
— `SqliteConfigurationDefinitionRepository`/`SqliteConfigurationValueRepository`
implementando los Protocols de `backend/domain/settings/repository_ports.py`,
más `value_serialization.py` (una forma JSON por `ValueType`; DECIMAL/
MONEY/PERCENT siempre como *string* JSON, nunca número, para no perder
precisión al reconstruir `Decimal`). `ConfigurationValue` no carga su
propio `value_type` — el repositorio de valores siempre hace JOIN contra
`configuration_definitions` para saber cómo (de)serializar `value_json`.

**Tests**: `tests/integration/settings/test_configuration_repositories.py`
(32 tests: round-trip de los 19 `ValueType` uno por uno, uniqueness de
`operation_id` y de `(definition, scope, version)`, `create_next_version`
persistiendo como fila nueva, resolución de herencia end-to-end contra
filas reales). Sumado a los 93 de SET-2 (dominio puro), **125 tests
verdes** para Configuration Governance. `tests/integration/_born_clean_db.py`
actualizado para aplicar esta migración en el fixture compartido.

---

## m000_base_schema — `configuraciones` código muerto eliminado — 2026-08-21

**Motivo:** SET-0 (auditoría del bounded context Settings/Configuración,
`docs/refactor/settings_legacy_inventory.md`) encontró que
`_create_core_config()` en `m000_base_schema.py` declaraba **dos**
`CREATE TABLE IF NOT EXISTS configuraciones` seguidas, con esquemas
incompatibles (la primera con PK `clave`; la segunda con PK `id` +
columnas `categoria`/`updated_at`). `IF NOT EXISTS` hace que la primera
gane siempre — la segunda nunca se ejecutó en ninguna instalación,
nueva o existente. Se confirmó que `ConfigRepository` (único consumidor
de `configuraciones` para lectura/escritura genérica) solo usa
`clave`/`valor`, nunca `id`/`categoria`/`updated_at`.

**Qué hace:** elimina el segundo `CREATE TABLE` muerto. No es una
migración nueva — es una corrección del schema base (`m000`), sin efecto
en bases de datos existentes (la tabla ya tenía, y sigue teniendo, el
esquema de la primera definición) ni en bases nuevas (bootstrap
verificado con `scripts/bootstrap_db.py`: `configuraciones` se crea
idéntica, solo sin el segundo statement redundante).

---

## 207_authentication_schema — 2026-08-19

**Motivo:** SHELL-7 (prompt maestro) — `AuthenticateUserUseCase` necesita
un historial real de intentos de login para que `AccountLockoutPolicy`
(SHELL-1) razone sobre la secuencia de fallos, no sobre un contador
(`usuarios.intentos_fallidos`/`bloqueado_hasta`, que sigue usando
`core/services/auth_service.py` sin cambios); y `AccountRecoveryService`
(SHELL-1, hasta ahora solo con repositorio en memoria) necesita persistir
tokens de recuperación de contraseña reales ahora que `LoginWindow` los
expone en un flujo de "olvidé mi contraseña" de verdad.

**Qué hace:** crea `authentication_attempts` (un row por intento: usuario,
estación, éxito/fallo, razón, fecha) y `account_recovery_tokens` (hash del
token, emitido/expira/usado — distinto de `installation_recovery_codes` de
SHELL-2, que es el kit de respaldo de la instalación, no de una cuenta).
Ambos mecanismos de lockout (el nuevo basado en historial y el legacy
basado en contador) coexisten mientras `AuthService` siga siendo el camino
de login real; SHELL-16/17 retira las columnas legacy cuando el nuevo
camino las reemplace.

**Backend nuevo** (`backend/security/authentication/`):
`UserCredentials`/`SqliteUserCredentialsRepository` (lectura de `usuarios`
+ el único write que necesita: persistir el hash tras un rehash exitoso),
`AuthenticationAttemptRepository` (Sqlite real + InMemory para tests),
`AuthenticateUserUseCase` (login → lockout → verificación → rehash
silencioso → sesión). `backend/security/credentials/password_verification.py`
gana `MultiSchemePasswordVerifier`: `Argon2idPasswordHasher.verify()` no
reconoce hashes bcrypt, así que sin este verificador de esquema múltiple
*ninguna* cuenta existente (ni siquiera el owner creado por el wizard de
SHELL-2, que usa `BcryptPasswordHasher`) podría iniciar sesión por este
camino nuevo — se detectó y corrigió antes de escribir
`AuthenticateUserUseCase`, no después. `backend/security/recovery/recovery_token_repository.py`
gana `SqliteRecoveryTokenRepository` junto al `InMemoryRecoveryTokenRepository`
de SHELL-1. `backend/bootstrap/application_context_builder.py`
(`ApplicationContextBuilder`) construye un `ApplicationContext` (SHELL-6)
real a partir del resultado de login, reutilizando `PermissionQueryService`
y `FeatureFlagService` — servicios existentes, no una segunda forma
paralela de cargar permisos/flags.

**UI nueva** (`frontend/desktop/auth/`): `LoginWindow` (§39 — recibe los
casos de uso, nunca `db`/`AuthRepository`/`AppContainer`/`SecretStore`,
construida sobre el Design System, no sobre el `DialogoLogin` legacy de
estilos en línea), `AccountRecoveryDialog` (dos pasos: solicitar código,
restablecer contraseña — sin integración de envío de correo/SMS todavía,
así que el token se muestra en pantalla como flujo asistido/interino, no
como patrón de producción final), `AuthenticationCoordinator` (§38 —
enruta según `InstallationStatusQuery`: UNINITIALIZED/PROVISIONING →
`InitialSetupWizard`, PROVISIONED → `LoginWindow`, LOCKED/RECOVERY_REQUIRED
→ diálogos mínimos ya que nada en la app transiciona la instalación a esos
estados todavía), `InstallationLockedDialog`/`InstallationRecoveryRequiredDialog`.
**Aún no cableado** en `main.py` — SHELL-16/17.

**Tests:** 82 nuevos (unitarios de `MultiSchemePasswordVerifier`,
integración contra schema real para `AuthenticateUserUseCase` —incluyendo
disparo real de lockout tras N fallos, auto-rehash bcrypt→argon2id
verificado leyendo la fila, y que el mismo mensaje genérico cubre usuario
inexistente/contraseña incorrecta—, `AuthenticationAttemptRepository`,
`SqliteRecoveryTokenRepository`, `ApplicationContextBuilder`, y UI headless
para `LoginWindow`/`AccountRecoveryDialog`/`AuthenticationCoordinator` esta
última con diálogos falsos para evitar bloquear en `QDialog.exec_()` real
sin un usuario cerrando el diálogo). `tests/integration/_born_clean_db.py`
incluye ahora la migración 207.

---

## 206_installation_provisioning_schema — 2026-08-19

**Motivo:** SHELL-2 (prompt maestro de refactor del bootstrap/shell) —
"instalación" (Installation, InitialSetupWizard, primer propietario, kit de
recuperación) no existía en ninguna forma; una base nueva llegaba a `admin`
seed-hardcodeado con hash SHA-256 que el verificador de login (bcrypt-only)
rechazaba, dejando el primer arranque sin forma real de entrar. Este trabajo
también corrigió, por separado, dos bugs de arranque encontrados en el
camino: `_seed_initial_data` (m000) insertaba en la tabla legacy `cajas`
(retirada intencionalmente en CASH-3/CASH-25 pero nunca actualizada aquí),
abortando antes de llegar al INSERT del usuario admin; y tanto el admin
como el usuario `demo` (migración 047) se sembraban con SHA-256 sin sal en
vez de bcrypt — ambos fijados directamente en sus migraciones (`admin`
ahora usa `security.auth.hash_password`, `demo` idem con contraseña
`demo12345` para cumplir el mínimo de 8 caracteres).

**Qué hace:** crea `installation` (fila singleton en
`INSTALLATION_SINGLETON_UUID`, estados UNINITIALIZED → PROVISIONING →
PROVISIONED, o LOCKED/RECOVERY_REQUIRED) e `installation_recovery_codes`
(códigos de respaldo hasheados, un solo uso). Agrega `usuarios.recovery_contact`
(email/teléfono para `AccountRecoveryService`, columna aditiva vía
`ALTER TABLE ... ADD COLUMN`). Siembra el rol de sistema `system_owner`
(UUIDv7 `...aa`, ver `SYSTEM_ROLE_UUIDS`) con la misma matriz de permisos
totales que `admin` — es el rol que recibe el primer propietario creado por
`InitialSetupWizard`/`CreateInitialOwnerUseCase`, distinto de `admin` (que
sigue existiendo como rol operativo asignable después).

**Backend nuevo** (`backend/security/provisioning/`): `Installation`
(entidad de dominio pura, transiciones validadas), `InstallationRepository`
(Sqlite real + InMemory para tests — a diferencia de Recovery/Sessions de
SHELL-1, esto sí necesita persistir desde el día uno: se consulta en cada
arranque frío, antes de que exista login), `InstallationStatusQuery`,
`RecoveryCode`/`InstallationRecoveryKit`/`RecoveryCodeRepository` (códigos
de respaldo de la instalación — hash SHA-256 rápido, mismo razonamiento que
`RecoveryToken` de SHELL-1: son secretos de alta entropía generados por
máquina, no contraseñas elegidas por humanos), `CreateInitialOwnerUseCase`,
`ProvisionInstallationUseCase` (orquestador; idempotente vía el propio
estado de `Installation` — `InstallationAlreadyProvisionedError` en un
segundo intento). `backend/security/credentials/password_hasher.py` ganó
`BcryptPasswordHasher` junto al `Argon2idPasswordHasher` de SHELL-1: el
verificador de login real (`core/services/auth_service.py`) solo acepta
bcrypt hoy, así que `CreateInitialOwnerUseCase` debe hashear con
`BcryptPasswordHasher` — un owner creado con Argon2id quedaría con una
cuenta inutilizable hasta que SHELL-7 corte el verificador en vivo a
Argon2id (momento en que `needs_rehash()` migra los hashes bcrypt
existentes automáticamente).

**UI nueva** (`frontend/desktop/provisioning/`): `InitialSetupWizard` (7
páginas en `QStackedWidget` — welcome, company, branch, workstation,
owner_account, security_recovery, confirmation — usando los componentes
canónicos del Design System: `PageHeader`, `create_primary_button`,
`StandardDialog`, `PasswordInput`, `EmailInput`; nada de QSS/emojis
sueltos), `ProvisioningViewModel` (datos puros, sin PyQt) y
`ProvisioningPresenter` (única costura entre las páginas y
`ProvisionInstallationUseCase` — las páginas nunca ven la conexión de DB ni
el hasher). La página de confirmación muestra los 10 códigos de
recuperación una sola vez y bloquea el cierre del diálogo
(`closeEvent`) hasta que el usuario reconoce haberlos guardado. **Aún no
está cableado** en `main.py`/`AppContainer` — eso es SHELL-7
(AuthenticationCoordinator); por ahora es un componente autónomo y
probado.

**Tests:** 55 nuevos (38 unitarios puros en `tests/unit/security/` +
10 BcryptPasswordHasher, 18 de integración con schema real en
`tests/integration/security/` incluyendo un roundtrip de login real contra
`AuthService`, y 17 de UI headless en `tests/ui/test_initial_setup_wizard.py`
que ejercitan el wizard completo — incluida la protección de cierre —
contra la base de datos y el `ProvisionInstallationUseCase` reales, no
mocks). `tests/integration/_born_clean_db.py::make_db()` ahora incluye la
migración 206 en su lista curada (usada por 26 suites de integración
existentes; verificado sin regresiones).

---

## 196_customer_credit_profile_backfill — 2026-08-16

**Motivo:** CRM-27 (cut-over completo Customer Master, parte 1) — el gate
real de crédito en checkout (`CustomerCreditService.validate_credit`)
leía `clientes.allows_credit`/`credit_limit` directamente; el workflow
moderno `customer_credit` (CRM-8, migración 188) existía pero no tenía
ningún efecto en POS.

**Qué hace:** bridgea todo `clientes` legacy con crédito activo hacia
`customers` (CRM-21) y crea un `customer_credit_profiles` AUTHORIZED
espejo. Idempotente, nunca pisa un perfil ya existente. Ver
`docs/refactor/CRM-27_finance_credit_cutover.md` para el detalle completo.

---

## 193_customers_legacy_customer_bridge — fix de orden — 2026-08-14

**Motivo:** CRM-25 — al aplicar esta migración por primera vez contra una
base de datos de desarrollo REAL (no un bootstrap fresco en memoria, que es
lo único que la ejercitaba hasta ahora), falló con
`sqlite3.OperationalError: no such column: legacy_customer_id`.

**Causa raíz:** `run(conn)` llamaba `create_customers_crm_schema(conn)`
ANTES de agregar la columna vía `_add_column`. En una base con `customers`
ya creada por la migración 181 (es decir, cualquier base real migrada
secuencialmente, no una vacía), el `CREATE TABLE IF NOT EXISTS` de esa
función es un no-op — pero su `CREATE UNIQUE INDEX IF NOT EXISTS
idx_customers_legacy_customer_id ON customers(legacy_customer_id)` es
incondicional y se ejecuta igual, fallando porque la columna todavía no
existe. Nunca se detectó antes porque toda la suite de tests de CRM-13
en adelante usa `full_crm_conn`/bootstraps en memoria, donde la tabla
`customers` se crea POR PRIMERA VEZ ya con la columna incluida.

**Cambio:** se invirtió el orden en `migrations/standalone/
193_customers_legacy_customer_bridge.py::run()` — `_add_column` primero,
`create_customers_crm_schema(conn)` después. Sin cambio de comportamiento
en un bootstrap fresco (la función seguía creando la columna en el primer
`CREATE TABLE`); solo corrige el caso de una base preexistente.

**Verificación:** aplicada exitosamente contra
`data/spj_pos_database.db` (backup previo en el scratchpad de la sesión);
1 cliente legacy existente puenteado correctamente vía
`tools/crm/backfill_legacy_customers.py`.

---

## 193_customers_legacy_identity_bridge — 2026-08-13

**Motivo:** CRM-21 — "Migración de consumidores" (POS, Ventas, WhatsApp,
Delivery, Fidelidad, Finanzas). CRM-13 built a full read-side integration
layer for the Customer Master (`backend/application/customers/queries/*`,
`backend/application/customer_credit/queries/*`,
`sales_event_handlers.py`) but left it deliberately inert: the legacy
`clientes` table (all real production data) and the new `customers` table
(CRM-3, essentially unused in production) are two separate tables with
independently-minted UUIDv7 ids and no bridge between them — named
explicitly as deferred to "CRM-21/22" in three places in the CRM-13 code.

**Cambio:** agrega `customers.legacy_customer_id TEXT` (nullable) +
`idx_customers_legacy_id` (índice único parcial, `WHERE legacy_customer_id
IS NOT NULL`, para no colisionar en NULL entre clientes nativos del nuevo
bounded context). Same idempotent `_add_column` pattern as migration 192.
DDL also added to the born-clean path in
`backend/infrastructure/db/schema/customers_crm_schema.py` so a fresh DB
gets the column from `create_customers_crm_schema()` directly.

**No migra `clientes` en sí.** El puente es de solo lectura/resolución:
`backend/application/customers/use_cases/legacy_identity_bridge_use_cases.py`
añade `ResolveLegacyCustomerUseCase` (resuelve o crea perezosamente una fila
`customers` bridge para un `clientes.id` dado) y
`BackfillLegacyCustomersUseCase` (backfill por lotes, vía
`tools/crm/backfill_legacy_customers.py`). Los seis módulos consumidores
(POS/Ventas, WhatsApp, Delivery, Fidelidad, Finanzas) siguen escribiendo en
`clientes` exactamente igual que antes — reescribir esas rutas de escritura
al nuevo `customers` es trabajo futuro (CRM-22+), explícitamente fuera de
alcance de esta fase por el riesgo de mover datos financieros reales sin una
migración de producción dedicada (CLAUDE.md Prioridad 0).

Investigación confirmó que solo dos consumidores de CRM-13 necesitaban este
puente (`sales_event_handlers.py` vía `RecordCustomerSaleActivityUseCase` y
`CustomerCommercialEligibilityQuery`, ambos leen la tabla `customers`
nueva por id) — las otras tres queries de integración
(`CustomerOrdersSummaryQuery`/`LoyaltyCustomerSummaryQuery`/
`CustomerAccountsReceivableSummaryQuery`) ya funcionan correctamente contra
datos reales al recibir directamente el `cliente_id` legacy, sin traducción
de identidad. Ver `docs/refactor/CRM-21_migracion_consumidores.md`.

---

## 187_meat_processing_bounded_context_schema — 2026-08-12

**Motivo:** PROC-3 — esquema born-clean del bounded context Procesamiento
Cárnico/Meat Processing (núcleo productivo del prompt maestro §1: `ProcessingOrder`,
`ProcessingBatch`, `ProcessExecution`, `MaterialConsumption`, `ProcessOutput`,
`ProcessWeighing`, `YieldReconciliation`), consumido por
`backend/infrastructure/db/repositories/meat_processing/` vía
`MeatProcessingUnitOfWork`. DDL vive en
`backend/infrastructure/db/schema/meat_processing_schema.py` (patrón CRM/Customers:
la migración solo invoca `create_meat_processing_schema(conn)`).
**Tablas:** `processing_orders`, `processing_batches`,
`processing_batch_source_lots`, `process_executions`, `material_consumptions`,
`process_outputs`, `process_weighings`, `yield_reconciliations`,
`meat_processing_authorization_log`, `meat_processing_audit_log`,
`meat_processing_outbox`, `meat_processing_processed_events` (12 tablas nuevas).
**Constraints:** todo `id` es `TEXT PRIMARY KEY` UUIDv7 (REGLA CERO); todo
`operation_id` es `UNIQUE` y `CHECK(operation_id <> id)`; toda columna
cantidad/peso/porcentaje es `TEXT` decimal con `CHECK(CAST(x AS NUMERIC) >= 0)`
(sin `REAL`); `status`/`process_type`/`output_type`/etc. usan
`CHECK (col IN (...))` generado directamente desde
`backend.domain.meat_processing.enums` (no puede haber drift esquema↔dominio);
`process_weighings` fuerza `manual_override=0 OR authorized_by_user_id IS NOT NULL`
(§21) y `stable=1 OR manual_override=1`.
**Impacto:** Solo aditivo — no toca las tablas legacy `producciones`/
`produccion_detalle` (ver `docs/refactor/PROC-0_legacy_audit.md`), que conservan
sus lectores vivos hasta PROC-25. Sin FKs cross-context (product_id/branch_id/
warehouse_id se validan a nivel de aplicación, no de esquema, para no acoplar el
orden de migraciones a Productos/Sucursales/Inventario).

---

## 184_inventory_cold_chain_resolution — 2026-08-10

**Motivo:** INV-9 — resolución operacional de excursiones de cadena de frío
(quién resolvió, cuándo y por qué), consumida por `ResolveTemperatureExcursionUseCase`.
**Tabla:** `inventory_temperature_excursions` — agrega `resolved_by`, `resolved_at`,
`resolution_note` (todas nullable, TEXT).
**Impacto:** Sólo aditivo; `ALTER TABLE ... ADD COLUMN` idempotente (mismo patrón que 180).

---

## 060_depreciacion_acumulada — 2026-04-13

**Motivo:** Fase 3 — acumulado mensual de depreciación por activo y periodo.
**Tabla:** `depreciacion_acumulada` (activo_id, periodo YYYY-MM, monto_mes, acumulado, cuenta_id).
**Constraint:** UNIQUE(activo_id, periodo) — idempotente por diseño.
**Impacto:** Solo aditivo; vincula `activos` → `depreciacion_acumulada` → `plan_cuentas`.

---

## 059_plan_cuentas — 2026-04-13

**Motivo:** Fase 3 — catálogo contable mínimo NIF/SAT para plan de cuentas formal.
**Tabla:** `plan_cuentas` (codigo_sat UNIQUE, nombre, tipo, nivel, padre_id).
**Catálogo:** 41 cuentas 1xx–6xx (Activo, Pasivo, Capital, Ingresos, Costos, Gastos).
**Impacto:** Solo aditivo; base para asientos doble entrada en `finance_service`.

---

## 058_scan_event_log — 2026-04-12

**Motivo:** Fase 2 — auditoría de eventos de escaneo (Plan Maestro).
**Tabla:** `scan_event_log` (raw_code, tipo, contexto, accion, payload, cliente_id, producto_id).
**Impacto:** Solo lectura/escritura de auditoría; sin cambios destructivos.

---

## 057_loyalty_ledger_unificado — 2026-04-12

**Motivo:** Fase 2 — ledger unificado de fidelización (acumulación+canje+reversa).
**Tabla:** `loyalty_ledger` (cliente_id, tipo, puntos, monto_equiv, saldo_post, referencia).
**Tablas existentes preservadas:** `growth_ledger`, `loyalty_pasivo_log`, `historico_puntos`.
**Impacto:** Solo aditivo; no modifica tablas existentes.

---

## 056_print_job_log — 2026-04-12

**Motivo:** Fase 1 Plan Maestro — bitácora de impresión obligatoria.
**Tabla creada:** `print_job_log` (job_id, job_type, plantilla, impresora, folio,
estado, reintentos, total, error_msg, created_at, finished_at).
**Impacto:** Auditoría de cada trabajo de impresión; sin cambios destructivos.
**Registrado en:** `migrations/engine.py` posición 056.

---

## Estado inicial auditado — 2026-04-08

### Migraciones canónicas (en engine.py)

| Número | Archivo canónico | Observación |
|--------|-----------------|-------------|
| 016 | 016_concurrency_events.py | OK |
| 018 | 018_sync_industrial_extension.py | OK |
| 019 | 019_margin_protection.py | OK |
| 020 | 020_system_integrity.py | OK |
| 021 | 021_db_hardening.py | OK |
| 022 | 022_industrial_hardening.py | OK |
| 023 | 023_enterprise_upgrade.py | OK |
| 024 | 024_enterprise_blocks_5_8.py | OK |
| 025 | 025_sync_batch_log.py | OK |
| 026 | 026_final_structural_hardening.py | OK |
| 027 | 027_inventory_hardening.py | OK |
| 028 | 028_sales_transaction_hardening.py | OK |
| 029 | 029_reversals_hardening.py | OK |
| 030 | **030_recetas_industriales.py** | Canónico — ver conflicto abajo |
| 031 | **031_inventory_engine.py** | Canónico — ver conflicto abajo |
| 032 | **032_bi_tables.py** | Canónico — ver conflicto abajo |
| 033 | 033_demand_forecast.py | OK |
| 034 | 034_bi_tables.py | OK |
| 035 | 035_finance_erp.py | OK |
| 036 | 036_whatsapp_rasa.py | OK |
| 037 | 037_product_images.py | OK |
| 038 | 038_transfer_suggestions.py | OK |
| 039 | 039_branch_products.py | OK |
| 040 | 040_qr_reception.py | OK |
| 041 | 041_notification_inbox.py | OK |
| 042 | 042_whatsapp_multicanal.py | OK |
| 043 | 043_price_history.py | OK |
| 044 | 044_cotizaciones.py | OK |
| 045 | 045_performance_indexes.py | OK |
| 046 | 046_comisiones_happy_hour.py | OK |
| 047 | 047_v13_schema.py | OK |
| 048 | **048_v131_hardening.py** | Canónico — ver conflicto abajo |
| 049 | 049_v134_intelligent_erp.py | OK |
| 050 | 050_wa_integration.py | OK |
| 051 | 051_fix_kpi_snapshots.py | OK |

---

## Conflictos resueltos

### Conflicto 030
- **Canónico**: `030_recetas_industriales.py` (97 líneas, crea tabla `recetas`)
- **Huérfano**: `030_recipe_tables.py` (5 líneas, solo contiene comentario de fusión)
- **Decisión**: `030_recipe_tables.py` ya fue vaciado y contiene solo el comentario
  `# 030_recipe_tables.py — FUSIONADO en 030_recetas_industriales.py`.
  No requiere acción adicional. El engine.py usa el canónico.
- **Fecha**: Pre-existente al 2026-04-08

### Conflicto 031
- **Canónico**: `031_inventory_engine.py` (612 líneas, crea tablas de inventario)
- **Huérfano**: `031_inventory_industrial.py` (3 líneas, solo comentario)
- **Decisión**: Igual que 030. Ya resuelto antes de esta auditoría.
- **Fecha**: Pre-existente al 2026-04-08

### Conflicto 032 ⚠️
- **Canónico**: `032_bi_tables.py` (476 líneas, crea tablas BI + producción)
- **Huérfano activo**: `032_meat_production.py` (73 líneas, `run()` real que crea
  `meat_production_runs` y `meat_production_yields`)
- **Problema**: El huérfano tiene `run()` real pero NO está en engine.py, por lo que
  sus tablas pueden no existir en la DB de producción.
- **Decisión 2026-04-08**: Crear `053_meat_production_tables.py` que aplica las tablas
  faltantes de forma idempotente. Se marca `032_meat_production.py` como fusionado.
  Ver migración 053.

### Conflicto 048 ⚠️
- **Canónico**: `048_v131_hardening.py` (97 líneas, columnas sync + `sync_state`)
- **Huérfano activo**: `048_sync_improvements.py` (66 líneas, `run()` real que agrega
  columnas `operation_id`, `uuid` a `event_log` y `sync_outbox`)
- **Problema**: Igual que 032 — el huérfano nunca se ejecutó vía engine.py.
- **Decisión 2026-04-08**: Crear `054_sync_improvements_orphan.py` con ALTER TABLE
  idempotentes. Ver migración 054.

---

## Migraciones nuevas (v13.4 audit)

### 052 — financial_event_log (2026-04-08)
- **Archivo**: `052_financial_event_log.py`
- **Motivo**: Audit trail de operaciones financieras requerido por spec v13.4.
  La tabla `treasury_ledger` existente no tiene campos `cuenta_debe`/`cuenta_haber`
  necesarios para asientos contables de doble entrada.
- **Tablas creadas**: `financial_event_log` + 2 índices

### 053 — meat_production_tables (2026-04-08)
- **Archivo**: `053_meat_production_tables.py`
- **Motivo**: Resolución del conflicto 032. Tablas `meat_production_runs` y
  `meat_production_yields` del huérfano `032_meat_production.py` aplicadas
  de forma idempotente.

### 054 — sync_improvements_orphan (2026-04-08)
- **Archivo**: `054_sync_improvements_orphan.py`
- **Motivo**: Resolución del conflicto 048. Columnas del huérfano
  `048_sync_improvements.py` aplicadas de forma idempotente via ALTER TABLE.

---

## v13.4 wiring + bootstrap fix — 2026-04-08

### Cambios en servicios (solo aditivos)

- **`core/db/connection.py`**: Agregada función `verificar_tablas(conn)` que
  levanta `RuntimeError` si alguna de las tablas críticas
  (`usuarios`, `productos`, `clientes`, `ventas`, `configuraciones`, `inventario`)
  no existe. Usada por `main.py` como check fail-fast post-migraciones.

- **`main.py`**: `inicializar_sistema()` ahora llama `verificar_tablas()` justo
  después de `migrator.up()`. Si las tablas faltan se muestra un diálogo y se
  aborta el arranque en lugar de continuar con DB vacía.

- **`core/services/forecast_engine.py`**: Agregado `generar_forecast_diario()`
  como alias de `run()`. Resuelve el crash del `SchedulerService` que llamaba
  este método inexistente.

- **`core/services/inventory_service.py`**: Agregados alias en español
  `descontar_stock()`, `incrementar_stock()`, `ajustar_merma()` que delegan en
  `deduct_stock()` / `add_stock()` respectivamente.

- **`core/services/enterprise/finance_service.py`**: Agregados
  `registrar_ingreso()`, `registrar_egreso()`, `registrar_perdida()` como
  wrappers de `registrar_asiento()` con cuentas contables predeterminadas.

- **`core/events/wiring.py`**: Agregadas dos nuevas funciones de wiring:
  - `_wire_venta_financiero`: `VENTA_COMPLETADA` → `finance_service.registrar_ingreso`
    (prioridad 50) para generar asiento contable en cada venta.
  - `_wire_merma_inventario`: `MERMA_CREATED` → `inventory_service.ajustar_merma`
    (prioridad 80) para descontar stock físico ante mermas vía evento.

---

## 080 — Caja turno_id FK + índices de rendimiento (2026-05-19)

**Migración**: `080_caja_turno_id_link.py`

**Contexto**: Fase 3/4 del refactor del módulo de caja (clean architecture).
`CajaApplicationService.generar_corte_z()` ahora persiste `turno_id` en
`cierres_caja` para permitir trazabilidad directa entre un corte Z y su turno.

**Cambios de esquema**:
- `cierres_caja`: columna `turno_id INTEGER` (nullable, retrocompatible)
- Índice `idx_cierres_turno` sobre `cierres_caja(turno_id)`
- Índice `idx_mov_caja_turno` sobre `movimientos_caja(turno_id)`
- Índice `idx_mov_caja_fecha` sobre `movimientos_caja(sucursal_id, fecha)`

**Riesgo**: Bajo. Solo agrega columna nullable e índices.

---

## FASE 5 Auditoría Finanzas — Extracción de sub-servicios (2026-05-21)

**Rama**: `claude/fix-finance-audit-AVOoY`

**Contexto**: Auditoría profunda del módulo Finanzas. `FinanceService` (1,921 líneas)
se descompone en tres sub-servicios especializados. FinanceService conserva todos los
métodos públicos como wrappers de compatibilidad hacia atrás (facade pattern).

**Nuevos archivos**:

- `core/services/finance/general_ledger_service.py` — Motor de libro mayor.
  `registrar_asiento()` NO hace commit (el caller decide cuándo confirmar).
  Métodos: `registrar_asiento`, `obtener_ledger`, `generar_poliza_periodo`, `exportar_poliza_periodo`.

- `core/services/finance/accounts_payable_service.py` — CxP canónico.
  Opera sobre tabla `accounts_payable`. `crear_cxp` y `abonar_cxp` hacen commit propio
  (operaciones autónomas). Métodos: `listar`, `summary`, `crear_cxp`, `abonar_cxp`, `historial_pagos`.

- `core/services/finance/accounts_receivable_service.py` — CxC canónico.
  Opera sobre tabla `accounts_receivable`. `crear_cxc` y `cobrar_cxc` hacen commit propio.
  Métodos: `listar`, `summary`, `crear_cxc`, `cobrar_cxc`.

**Cambios en servicios existentes**:

- `core/services/enterprise/finance_service.py`:
  - Bug fix FASE 4: `pagar_nomina` usaba `'efectivo'` hardcodeado → corregido a `metodo_pago`
  - `__init__` inicializa `self._gl` (GeneralLedger), `self._aps` (AP), `self._ars` (AR)
  - `registrar_asiento` delega a `self._gl.registrar_asiento()` con fallback SQL
  - `crear_cxp / abonar_cxp / cuentas_por_pagar` delegan a `self._aps` (marcados DEPRECATED)
  - `crear_cxc / cobrar_cxc / cuentas_por_cobrar` delegan a `self._ars` (marcados DEPRECATED)
  - `obtener_ledger / generar_poliza_periodo / exportar_poliza_periodo` delegan a `self._gl`
  - `registrar_movimiento_manual`: removido `self.db.commit()` interno (era llamado dentro SAVEPOINT)

- `core/services/finance/third_party_service.py`:
  - Agregado `check_duplicate_proveedor(nombre, rfc, telefono, exclude_id)` para validación
    centralizada (antes estaba en `DialogoProveedor` en la UI).

- `core/events/domain_events.py`:
  - Agregadas 7 constantes de eventos financieros con aliases en inglés sobre strings legacy.

- `core/services/finance/financial_dashboard_service.py` (nuevo):
  - `FinancialDashboardService`: elimina SQL directo de `finanzas_unificadas.py`.
  - Métodos: `get_quick_kpis`, `get_credit_info`, `listar_clientes`, `crear_cliente`.

- `modulos/finanzas_unificadas.py`:
  - 4 bloques de SQL directo en UI → reemplazados con llamadas a `FinancialDashboardService`.
  - `DialogoProveedor._guardar()` usa `ThirdPartyService.check_duplicate_proveedor()`.

**Nuevos tests** (60+ tests en rama):
- `tests/test_finance_audit_fixes.py` — 26 tests (bug fix nómina, dashboard service, sin doble CxP/CxC)
- `tests/test_finance_sub_services.py` — 34 tests (GL, AP, AR, delegación de fachada, FASE 8)

**Riesgo**: Bajo. Wrappers legacy preservados. Sin cambio de schema. Sin cambio de UI visible.

---

## Segunda auditoría Finanzas — hallazgos R-01 a R-06 (2026-05-21)

**Rama**: `claude/fix-finance-audit-AVOoY`

**Correcciones**:

- **R-01 — SQL injection en `TreasuryService.balance_general()`**
  `dt_filter = f"AND DATE(fecha) <= '{fc}'"` reemplazado por queries parametrizadas:
  condición condicional construida sobre columnas SQL fijas (`WHERE tipo='ingreso' AND DATE(fecha) <= ?`)
  con `dp = [fc] if fc else []`. Nunca se interpola input del usuario.

- **R-02 — Desync credit_balance/saldo en cancelaciones de crédito**
  `SaleCancelledFinanceHandler` actualizaba `credit_balance` pero olvidaba actualizar `saldo`.
  Ahora actualiza ambas columnas (`credit_balance` y `saldo`) en el mismo UPDATE, manteniendo
  la invariante de sincronización definida en `CreditSaleFinanceHandler`.

- **R-03 — Dead code `SaleCreatedFinanceHandler` eliminado**
  Clase nunca suscrita en `wiring.py`. Si se hubiese activado habría causado doble asiento
  de ingresos junto a `SaleFinanceHandler` (priority=90). Removida per CLAUDE.md: eliminar
  código muerto detectado en auditoría. Referencia: A-04 en FINANZAS_AUDIT_FIX_PLAN.md.

- **R-04 — Parámetros incorrectos en `GestionarFinanzasUC.registrar_asiento_manual()`**
  Llamada a `finance_service.registrar_asiento()` usaba `cuenta_debe=`, `cuenta_haber=`, `descripcion=`
  (API legacy que ya no existe). Corregido a `debe=`, `haber=`, `concepto=`.

- **R-05 — A-02: `TreasuryService._ensure_tables()` movida a migración**
  Las 6 tablas (treasury_capital, treasury_ledger, treasury_gastos_fijos, gastos_futuros,
  pagos_cobros, pagos_cobros_aplicaciones) ahora se crean via `migrations/standalone/082_treasury_tables.py`.
  `_ensure_tables()` es ahora un no-op por compatibilidad con callers legacy.

- **R-06 — `core/events/handlers/__init__.py` actualizados**
  Removida exportación de `SaleCreatedFinanceHandler` que causaba ImportError al importar el módulo.

**Nuevos tests** (23 tests en `tests/test_finance_remaining_fixes.py`):
- TestBalanceGeneralSQLInjection (5 tests) — verifica query parametrizada y rechazo de injection
- TestSaleCancelledHandlerSaldoSync (5 tests) — verifica sincronía credit_balance/saldo
- TestSaleCreatedHandlerRemoved (3 tests) — verifica eliminación de código muerto
- TestFinanzasUCParametros (3 tests) — verifica parámetros correctos en llamadas a registrar_asiento
- TestMigracion082TreasuryTables (7 tests) — verifica creación e idempotencia de tablas

**Total suite finanzas**: 117 tests pasando.

---

## 2026-07-12 — Bugfix/Refactor auditoría funcional (rama claude/pos-spj-refactor-bugfix)

Cambios al schema base (`m000_base_schema.py`) — sin migraciones de rescate,
la DB de desarrollo debe resetearse (born-clean UUIDv7):

- **S-01 — `loyalty_snapshots` reconstruida a forma checkpoint**: columnas
  `cliente_id UNIQUE`, `puntos_actuales`, `nivel`, `visitas`, `importe_total`,
  `ultimo_evento_id TEXT` (UUID), `fecha_snapshot`. Corrige
  `no such column: ls.ultimo_evento_id` del scheduler. La forma anterior
  (visitas_dia/importe_dia…) no tenía lectores.
- **S-02 — `historico_puntos` gana `saldo_actual REAL` y `usuario TEXT`**:
  sus escritores (sale_loyalty_policy, sales_reversal) ya insertaban esas
  columnas; ahora además acuñan `id` con `new_uuid()`.
- **S-03 — `usuarios` gana `intentos_fallidos`, `bloqueado_hasta`,
  `locked_reason`, `updated_at`** en el CREATE base (antes solo por
  ensure_column parcial). Soporta el flujo administrativo de desbloqueo.
- **S-04 — `usuario_permisos` y `usuario_sucursal_permisos` creadas**:
  overrides RBAC por usuario/sucursal con `usuario_id`/`sucursal_id` UUID TEXT.
  Antes no existían y los overrides se ignoraban en silencio.
- **S-05 — Índice único `idx_cxc_venta_unica` en
  `cuentas_por_cobrar(venta_id)`**: garantiza idempotencia de CxC por venta.

Cambios de servicios (fuera de schema) documentados en el PR/reporte:
compras ya no escriben `movimientos_caja` (asiento contra
`capital_operativo`); Corte Z compara solo efectivo esperado vs contado;
`ConfigRepository` sin `int(UUID)`; `SessionContext` con identidad str;
lotes/movimientos_lote con `id` UUIDv7 (sin columna `uuid` ni randomblob);
`new_uuid()` monótono in-process (checkpoints UUIDv7).

### Adendum (misma rama) — saldo de deuda de identidad

- **S-06 — Tabla `anticipos` creada en m000**: antes la creaba
  `api/routers/anticipos.py` con `INTEGER PRIMARY KEY AUTOINCREMENT`
  (doble violación: DDL fuera de migrations + autoincrement). Ahora nace
  UUIDv7 en el schema base y el router solo inserta.
- **Deuda lastrowid saldada**: api/routers (cotizaciones/pedidos/anticipos),
  integrations/pos_adapter, integrations/cfdi — todos acuñan `id` con
  `new_uuid()`. Helper muerto `_lastrowid` eliminado de
  infrastructure/persistence/base.py. Allowlists reducidas a solo
  menciones en docstrings.
- **Contratos API a UUID string**: modelos Pydantic de cotizaciones y
  pedidos transportan `cliente_id`/`producto_id`/`sucursal_id` como str
  (sin defaults `sucursal_id=1`).

### Hotfix post-validación manual (misma rama)

- **114_security_lock_and_canonical_kpi_schema.py** (registrada en engine):
  alinea bases de desarrollo EXISTENTES con el schema nuevo — el engine
  salta m000 en DBs ya migradas (`_already_run`), por lo que
  `locked_reason`, `usuario_permisos`, `anticipos`, la forma checkpoint de
  `loyalty_snapshots` y el índice único de CxC no llegaban a DBs vivas
  ("no such column: locked_reason" al desbloquear). Idempotente; deduplica
  CxC por venta_id conservando la fila más antigua antes de crear el índice.
- **balance_general (TreasuryService)**: "Caja y bancos" ahora suma el
  efectivo operativo de `movimientos_caja` (ventas/ingresos − retiros) y
  "Cuentas por cobrar" suma la CxC canónica `cuentas_por_cobrar` — antes
  leía solo `treasury_ledger`/`accounts_receivable` (vacías) y los KPIs de
  Finanzas quedaban en cero con datos reales.
- **_prov_repo / _history_qs**: convertidos de @property a atributos planos
  asignados en __init__ (la property sin setter chocaba con asignaciones de
  hotfixes locales: "property '_prov_repo' has no setter").

### Lote 4 — Tesorería unificada, identidad de roles, integración financiera

- **S-07 — Roles del sistema born-clean UUIDv7 (m000)**: `_seed_system_roles`
  siembra `roles` + `rol_permisos` con UUIDv7 canónico (SYSTEM_ROLE_UUIDS).
  Se eliminaron de 047 los seeds con id entero 1..6 (identidad legacy) y el
  usuario demo pasó a UUIDv7 + sucursal de instalación. Migración 116 remienda
  DBs existentes (roles enteros → UUIDv7, propagando rol_permisos/usuarios_roles).
  Corrige "role_id must be a canonical lowercase UUIDv7".
- **S-08 — proveedores gana limite_credito/condiciones_pago (m000)**: soporte
  para la política de crédito de proveedor en Compras.
- **Tesorería unificada**: TreasuryService expone register_inflow/outflow
  delegando en un TreasuryMovementService propio (fix "register_outflow
  inexistente" en CapitalService/OperatingSupplies/Maintenance/FinancialTrace).
- **Corte Z → capital**: CashCutCapitalHandler consolida el efectivo del turno
  en treasury_movements (idempotente) al cerrar caja.
- **KPIs financieros**: count_overdue_payables/receivables ahora suman la unión
  canónica (financial_documents + CxP/CxC del POS) — la CxC del POS siempre
  cuenta en KPIs.
- **Historial de puntos del cliente**: fuente canónica loyalty_ledger
  (acumulación/canje por venta), no historico_puntos vacío.

## 2026-07-16 — Migración 117: bounded context financiero born-clean (UUIDv7)

- **Nueva migración `117_finance_bounded_context_schema.py`**: crea el esquema
  canónico de doble partida (24 tablas: accounts, journals, journal_entries +
  journal_lines, fiscal_periods, financial_documents, receivables/collections,
  payables/supplier_payments, treasury_accounts, bank_statements,
  reconciliations, budgets, cost/profit_centers, fixed_assets,
  posting_profiles, commercial_obligations, finance_processed_events,
  finance_outbox). Todo `TEXT PRIMARY KEY` UUIDv7; importes como cadenas
  decimales (`Decimal`, sin `REAL`); idempotencia estructural por
  `UNIQUE(operation_id)` y `UNIQUE(source_module, source_document_id,
  posting_purpose)`.
- **Drop de tablas legacy huérfanas** (sin rescate de datos — regla de
  desarrollo): plan_cuentas, ledger_financiero, documentos_financieros,
  movimientos_financieros, financial_trace_log, reconciliation_records,
  capital_movements, cortes_caja_erp, terceros, cuentas_financieras,
  catalogo_cuentas_contables, pagos_cobros_aplicaciones, cuentas_por_pagar,
  loyalty_budget_caps, asset_depreciation_entries, maintenance_records,
  operating_supplies, conciliaciones_financieras + las versiones legacy de
  journal_entries/journal_lines/financial_documents/fixed_assets (se recrean
  limpias).
- **Conservadas** (escritores operativos vivos, migran con su módulo dueño):
  financial_event_log, cuentas_por_cobrar, accounts_payable/receivable,
  treasury_capital/ledger/gastos_fijos, pagos_cobros, treasury_movements,
  production_cost_ledger, growth_ledger, activos_depreciacion.
- El DDL vive en `backend/infrastructure/db/schema/finance_schema.py`; la
  migración es el único punto de ejecución.

## Compras / Procurement bounded context (PUR-4 → PUR-13)

- **Nueva migración `120_procurement_bounded_context_schema.py`**: crea el
  esquema canónico born-clean de Compras (23 tablas: user/role/branch
  purchase_limits, direct_purchases + direct_purchase_lines +
  direct_purchase_authorizations, purchase_requisitions + lines,
  requests_for_quotation, supplier_quotes + lines, purchase_orders + lines +
  purchase_order_versions, goods_receipts + lines, receipt_discrepancies,
  supplier_invoices + supplier_invoice_matches, purchase_authorization_log,
  procurement_audit_log, procurement_outbox, procurement_processed_events).
  Todo `TEXT PRIMARY KEY` UUIDv7; importes/cantidades como cadenas decimales
  (sin `REAL`); idempotencia estructural por `UNIQUE(operation_id)`,
  `UNIQUE(document_number)` y `UNIQUE(supplier_id, invoice_number)`.
- **Sin colisión con legacy**: los nombres canónicos (direct_purchases,
  purchase_orders, goods_receipts, purchase_requisitions, supplier_invoices…)
  NO chocan con las tablas legacy en español (compras / ordenes_compra /
  recepciones / purchase_requests), que conservan sus lectores vivos hasta que
  migren en PUR-11.
- El DDL vive en `backend/infrastructure/db/schema/procurement_schema.py`; la
  migración es el único punto de ejecución (allowlist en el guardrail
  clean-birth).
- **Separación POS↔Compras (§87)**: el POS detecta necesidades (emite eventos de
  reabasto) y NUNCA ejecuta compras; guardrail
  `tests/architecture/test_pos_does_not_execute_purchases.py`.
- **Integraciones (PUR-11)**: `backend/application/procurement/integrations/`
  publica eventos canónicos (INVENTORY_ADJUSTMENT_REGISTERED, PAYABLE_CREATED,
  SUPPLIER_PAYMENT_SCHEDULED, SUPPLIER_PERFORMANCE_RECORDED) y consume
  necesidades (STOCK_REPLENISHMENT_REQUIRED / PURCHASE_NEED_DETECTED /
  CUSTOMER_ORDER_REQUIRES_PURCHASE) creando solicitudes idempotentes. El pago
  inmediato jamás sale de la caja operativa del POS.

## Compras / Logística — permisos canónicos `MODULO.accion` (migración 177)

- **Problema**: `PurchasePermissions` (`backend/application/procurement/permissions.py`)
  usaba códigos planos (`PURCHASES_REQUISITION_CREATE`) y `LogisticsPermissions`
  (`backend/application/logistics/authorization.py`) usaba
  `logistics.shipment.view` — ninguno con el formato `MODULO.accion` que usa el
  resto del sistema (Ventas, Caja, Mermas, Finanzas) vía
  `core/security/permission_catalog.py::CANONICAL_MODULE_PERMISSIONS` y
  `SessionContext.tiene_permiso()`. Como `rol_permisos`/`usuario_permisos`
  guardan `(modulo, accion)` y jamás sembraron filas con esa forma legacy,
  **todo permiso granular de Compras/Logística fallaba cerrado para cualquier
  rol no-admin** — el bypass `es_admin` era la única vía funcional.
- **Cambio**: se renombraron los *valores* de ambas clases (los nombres de
  atributo Python no cambiaron, así que ningún call site necesitó edición) a
  `COMPRAS.solicitud.crear`, `COMPRAS.orden.aprobar`, `COMPRAS.recepcion.completar`,
  `COMPRAS.factura.conciliar`, `LOGISTICA.embarque.ver`,
  `LOGISTICA.contenedor.sellar`, etc. (77 códigos de Compras, 11 de Logística,
  incluye nuevo `LogisticsPermissions.CONTAINER_SCAN` que antes era un literal
  suelto `"logistics.container.scan"` en `mobile_workflow.py`, sin constante).
  `CANONICAL_MODULE_PERMISSIONS["COMPRAS"]` se amplió con las ~77 acciones
  granulares (antes solo `ver/crear/recibir`) y se agregó
  `CANONICAL_MODULE_PERMISSIONS["LOGISTICA"]`, así Configuración → Seguridad
  puede otorgarlas (`ConfigRepository.permission_matrix()` lee directo del
  catálogo).
- **Migración 177** (`177_compras_logistica_canonical_permissions.py`): NO
  otorga ningún permiso nuevo — no hay filas legacy que preservar (confirmado:
  ningún seed insertó jamás `modulo='PURCHASES'`/`'LOGISTICS'`). Solo normaliza
  defensivamente `modulo` en `rol_permisos`/`usuario_permisos`/
  `usuario_sucursal_permisos` por si algún ajuste manual usó los nombres
  legacy. Un administrador debe otorgar las nuevas acciones granulares
  explícitamente vía Configuración.
- **Refresh de sesión en vivo**: Compras (como todo módulo) se construye en
  `MainWindow._construir_todas_las_pantallas()` ANTES del login, con
  `capabilities()` vacío. Se agregó `PurchasingModuleShell.refresh_permissions()`
  (reconstruye sidebar/rutas/botones desde `capabilities()` sin recrear el
  widget) y se conectó al bucle genérico ya existente en
  `MainWindow._propagar_usuario()` (el mismo que llama
  `set_usuario_actual`/`set_sucursal` en cada widget cargado), que ya se
  re-invoca tanto tras login como tras guardar permisos en Configuración
  (`refresh_module_access()`). `DirectPurchaseCreatePage`/`DirectPurchaseCreateView`
  ganaron su propio `refresh_permissions()` porque son singletons reutilizados
  entre reconstrucciones del shell (no se recrean como las demás páginas).

## Compras — Fase 2 (contratos): sesión, UUID visibles y bloqueo de proveedor

- **UUID mostrado como texto principal (§4C del prompt de remediación)**:
  `EnterprisePurchasingPresenter.session_summary()` mostraba
  `"Sucursal: <uuid>"` (leía `default_branch()`, el id) y la tabla de
  Solicitudes mostraba `branch_id` crudo en la columna "Sucursal". Corregido:
  `session_summary()` ahora usa `session.sucursal_nombre`/`active_warehouse_name`
  reales (con mensaje controlado "Sucursal sin nombre configurado" si faltan,
  nunca el id); `RequisitionReadService.list()` agregó
  `LEFT JOIN sucursales` — mismo patrón ya usado para nombres de proveedor.
  El id sigue siendo la única fuente de verdad para persistencia/auditoría
  (`default_branch()` sin cambios); solo la presentación cambió.
- **Migración `178_proveedores_bloqueo_financiero.py`**: `proveedores` no
  tenía ninguna columna para bloqueo financiero o habilitación de compra —
  `SupplierDirectoryQueryService.get_eligibility()` devolvía
  `purchasing_enabled=True`/`financially_blocked=False` fijos, así que un
  proveedor bloqueado por Finanzas igual pasaba la validación de elegibilidad.
  La migración agrega `bloqueado_financiero`, `motivo_bloqueo` y
  `compras_habilitadas` (idempotente, `DEFAULT 0`/`NULL`/`DEFAULT 1` — ningún
  proveedor existente cambia de estado). `get_eligibility()` ahora lee las
  columnas reales; si una base no ha corrido la migración (schemas de prueba
  mínimos, instalaciones no migradas), degrada al comportamiento anterior en
  vez de fallar. Pendiente de diseño: quién puede bloquear/desbloquear un
  proveedor y desde qué módulo (no se construyó UI para esto todavía).

---

## Compras — Fase 2 (contratos): DTOs del read-model enterprise — 2026-08-05

- **Sin migración de esquema; solo tipos y wiring de aplicación/UI.**
- `backend/application/procurement/dto/enterprise_dtos.py` (nuevo): dataclasses
  `frozen` para las filas y detalles que ya devolvían `dict`/`sqlite3.Row` sin
  contrato — `RequisitionRowDTO`/`RequisitionDetailDTO`,
  `OrderRowDTO`/`OrderDetailDTO`, `InvoiceRowDTO`/`InvoiceDetailDTO`,
  `ReceiptRowDTO`/`ReceiptDetailDTO`, `PurchaseHistoryRowDTO` — mismo patrón
  que `DirectPurchaseRowDTO`/`DirectPurchaseDetailDTO` (Fase 1). Las
  colecciones secundarias de un detalle (`related_documents`, `timeline`,
  `matches`/`comparison` de facturas, `invoices` de una recepción) se dejaron
  como `list[dict]` a propósito — son proyecciones heterogéneas tipo
  bitácora, no la entidad documental en sí; tipar cada una habría sido
  alcance no pedido sin beneficio de contrato real.
- `enterprise_read_services.py` y `purchase_history_read_service.py` — `.list()`
  y `.detail()` ahora construyen y devuelven estos DTOs en vez de `dict`.
- **Bug real encontrado y corregido de paso (no cosmético):**
  `OrderDetailPanel` mostraba `Proveedor: <uuid>` (leía `supplier_id` crudo,
  nunca se unía contra `proveedores`) y `RequisitionDetailPanel` mostraba
  `Solicitante: <uuid>` (`requested_by_user_id` crudo, nunca contra
  `usuarios`). Corregido con el mismo patrón tolerante ya usado para
  proveedor en otras vistas (`_supplier_name()`/`_requester_name()`: lookup
  aparte con `_query_one`, nunca falla el detalle completo si la tabla de
  nombres no existe en un fixture de prueba — degrada a "Proveedor no
  disponible"/"Usuario no disponible", nunca revienta ni inventa un nombre).
- **Bug real encontrado y corregido de paso (crash):**
  `InvoicesPage._selection_changed()` (`enterprise_pages.py`) llamaba
  `self._presenter.invoice_detail(invoice_id)`, método que no existía en
  `EnterprisePurchasingPresenter` — `AttributeError` garantizado al
  seleccionar cualquier factura en la pantalla de Facturas. Se agregó
  `invoice_detail()` (mismo patrón que `order_detail()`, delega a
  `InvoiceReadService.detail()`).
- Consumidores actualizados de acceso por `dict`/`.get()` a atributos de
  dataclass: `document_detail.py` (`RequisitionDetailPanel`,
  `OrderDetailPanel`), `enterprise_pages.py` (`InvoicesPage`),
  `enterprise_dialogs.py` (`ReceiveOrderDialog`).
- Tests actualizados: `test_phase2_canonical_domain.py`,
  `test_enterprise_flow.py` (acceso por atributo donde el tipo cambió;
  `related_documents`/`timeline`/`comparison` internos siguen siendo `dict`,
  sin cambio). `test_enterprise_ui.py` no requirió cambios — solo consume
  `TableViewModel`, no las filas crudas.
- **Verificación:** `pytest tests/unit/procurement tests/integration/procurement`
  `tests/unit/logistics tests/integration/logistics` → 229/229; `pytest
  tests/architecture -k "procurement or purchasing or purchase"` → 43/47
  (los 4 fallos son preexistentes y no relacionados: directorio no
  rastreado `application/purchases`, `EntitySearchInput` ausente en
  `direct_purchase_dialogs.py`, y un bug de encoding en un test bajo
  Windows — ninguno tocado por este cambio); `compileall` limpio.
- **Pendiente del checklist de Fase 2:** "Crear puertos" (arquitectura de
  puertos § 22 del prompt maestro: `ProcurementProductCatalogPort`,
  `SupplierProcurementProfilePort`, `InventoryReceiptPort`,
  `ProcurementFinancePort`, `BranchWarehouseContextPort` — integración con
  Productos/Inventario/Finanzas, no construida todavía) y una auditoría
  fresca de "Corregir firmas" más allá de la que este cambio cubrió de paso.

---

## Compras — Fase 2 (puertos) — 2026-08-06

- **Bug real: una factura conciliada nunca generaba CxP en producción.**
  `MatchSupplierInvoiceUseCase`/`ReleaseInvoiceVarianceUseCase` emitían
  correctamente `ACCOUNT_PAYABLE_CREATE_REQUESTED` → `PAYABLE_CREATED`, y
  `CreatePayableUseCase` existía y tenía tests — pero nada lo suscribía en
  `core/events/wiring.py`. Nuevo `ProcurementPayableBridgeHandler`
  (`backend/application/event_handlers/finance/procurement_payable_bridge.py`)
  suscrito con prioridad 50 (contabilidad/ledger). Se agregó
  `document_number`/`branch_id`/`currency_code` al evento (faltaban para
  poder invocar `CreatePayableUseCase`). Pendiente documentado: el handler
  solo crea la obligación (Payable), no el asiento contable debe/haber —
  no hay enrutamiento de cuenta por `purchase_nature` implementado.
- **`ports.py` + `adapters/product_catalog_adapter.py`**: `ProcurementProductCatalogPort`
  (búsqueda + resolución contra el catálogo canónico `products`, nunca
  `productos`) y `BranchWarehouseContextPort` (tipado sobre
  `WarehouseDirectoryQueryService`, ya existente). Reemplaza el campo de
  texto libre "Código o ID de producto" por `EntitySearchInput` en compra
  directa, solicitudes, órdenes y facturas — cierra el gap de "captura
  manual de ID" señalado en el prompt maestro.
- **Bugs reales encontrados de paso al conectar el picker**: `EnterprisePurchasingPresenter`
  no tenía `supplier_options`, `requisition_detail`, `invoice_document_options`
  ni `invoice_document_profile` — la UI ya los llamaba (crear RFQ, crear
  orden desde solicitud, ver detalle, capturar factura) y siempre fallaba
  con `AttributeError` antes de llegar a la lógica de esos flujos. Al
  agregarlos se destapó una segunda capa: `OrderFormDialog` y
  `DirectPurchaseCreatePage.start_from_requisition` esperaban un `dict`
  donde ahora llega un `RequisitionDetailDTO` (Fase 2 anterior) — corregido
  a acceso por atributo. `CartLineVM` tampoco acepta `purchase_nature`
  (nunca lo aceptó); se quitó ese kwarg inválido.

---

## Compras — Fase 3 (acotada): proveedores y costos — 2026-08-07

Alcance acordado con el usuario: solo los 4 puntos sin migración de
esquema (Unidades y Condiciones de pago en Órdenes quedan pendientes —
`purchase_orders`/`purchase_order_lines` no tienen esas columnas hoy).

- **Bloqueo financiero visible en el picker de proveedores**:
  `SupplierPickerQueryService.search()` ahora expone
  `bloqueado_financiero`/`compras_habilitadas` (migración 178) y los
  presenters muestran "Bloqueado financieramente"/"Compras deshabilitadas"
  como subtítulo — antes el usuario solo se enteraba al fallar el envío.
  **Bug real encontrado al implementarlo**: el primer intento envolvió
  `self._query(...)` en un `try/except OperationalError`, pero `_query()`
  ya atrapa esa excepción internamente y devuelve `[]` — el except nunca
  se ejecutaba y una base sin la migración 178 devolvía **cero
  proveedores** en vez de degradar. Corregido llamando `execute()`
  directo (mismo patrón que `SupplierDirectoryQueryService`).
- **Costo de referencia visible al capturar línea**: `AddCartLineDialog`
  ahora muestra `presenter.price_variance(product_id, costo)` (ya existía
  y tenía tests, pero ninguna pantalla lo invocaba) al seleccionar
  producto o escribir el costo.
- **Conversión de unidades en Órdenes**: `_LinesEditor` gana
  `with_conversion` (solo `OrderFormDialog` — `purchase_order_lines.conversion_factor`
  ya existe y `CreatePurchaseOrderUseCase` ya la lee; Solicitudes y
  Facturas no tienen esa columna, no se agregó ahí).
- **Verificación**: 227 (procurement) + 3 (bloqueo proveedor) + 2 (nuevos,
  UI) tests en verde; regresión cubierta con test explícito para el bug
  del `try/except` muerto.

---

## Compras — Fase 4: flujo documental — Cotizaciones y Adjudicación — 2026-08-07

Auditoría previa contra el checklist "Solicitudes → RFQ → Cotizaciones →
Adjudicación → Órdenes → Compra directa → Documentos relacionados" encontró
que **Cotizaciones y Adjudicación no tenían ninguna pantalla**:
`CaptureSupplierQuoteUseCase`/`AwardSupplierQuoteUseCase` estaban completos
y probados en el backend desde antes, con permisos
`COMPRAS.cotizacion.capturar/comparar/adjudicar` ya en el catálogo, pero
nunca conectados a nada — un comprador podía crear y enviar una RFQ y ahí
se acababa el flujo en la app de escritorio.

- **Nuevo read-model** (`backend/application/procurement/queries/quotation_read_services.py`,
  `.../dto/quotation_dtos.py`): `RfqReadService.list/detail/comparison()`,
  proyecciones SQL puras (nunca reutiliza el `ProcurementUnitOfWork` de
  escritura). `comparison()` rankea por precio unitario dentro de cada
  producto y marca `is_best`; es una ayuda de presentación, no la fuente de
  verdad de qué se adjudica — eso lo sigue decidiendo
  `AwardSupplierQuoteUseCase`/el dominio.
- **`QuotationsPage`** (`frontend/desktop/modules/purchasing/pages/enterprise_pages.py`):
  lista de RFQ (invitados/cotizados/adjudicada) con panel de detalle
  (`RfqDetailPanel` en `document_detail.py`) mostrando invitaciones y
  resumen de cotizaciones por proveedor.
- **`QuoteCaptureDialog`**: captura lo que respondió un proveedor —
  restringido a los proveedores realmente invitados a esa RFQ (nunca
  búsqueda libre), plazo de entrega y líneas (reutiliza `_LinesEditor`).
- **`AwardDialog`**: tabla de comparación producto×proveedor con ★ para el
  mejor precio; un clic por producto elige la línea ganadora — permite
  adjudicación dividida (proveedores distintos por producto), tal como lo
  soporta el dominio (`PurchaseAward`/`PurchaseAwardLine`), no solo "todo
  a un proveedor".
- **Capacidades nuevas**: `quotation_view`/`quote_capture`/`quote_compare`/
  `quote_award` en `PurchasingCapabilities` + `capability_resolver.py`;
  ruta `PurchasingRoutes.QUOTATIONS` en `navigation.py`, gateada por
  `quotation_view` (verdadero si el usuario puede crear RFQ, capturar,
  comparar o adjudicar — no hay un permiso "ver" dedicado en el catálogo
  para RFQ, así que se compone de las acciones).
- **Efecto colateral esperado, ya corregido**: el rol "comprador" en
  `test_purchasing_role_matrix.py` gana la ruta `quotations` (tiene
  `RFQ_CREATE`) — se actualizó el set esperado. El guardarraíl de
  arquitectura `test_shell_exposes_only_implemented_permission_gated_routes`
  tenía "Cotizaciones" en su lista de *labels que no deben existir todavía*
  — se movió a la lista de labels implementados; "Adjudicaciones" se dejó
  en la lista de pendientes porque no es una pantalla propia (es una acción
  dentro de Cotizaciones).
- **Checklist "Documentos relacionados"**: sigue parcial — el panel de
  detalle de Solicitud/Orden ya muestra una lista de documentos
  relacionados, pero no es clicable/navegable. No se tocó en esta vuelta
  (alcance acordado fue solo Cotizaciones/Adjudicación).
- **Verificación**: suite completa de procurement + logistics (256 tests) y
  arquitectura de purchasing (8 tests) en verde; `compileall` limpio sobre
  `backend/`, `frontend/desktop/modules/purchasing/` y los tests tocados.
  Nuevos tests: `tests/integration/procurement/test_quotation_read_services.py`
  (5), más 4 en `test_enterprise_ui.py` cubriendo el flujo RFQ→captura→
  comparación→adjudicación de punta a punta a través del presenter, la
  página headless, y el `AwardDialog`.

---

## Fase 5 (Inventario y finanzas) — auditoría + CxP sin asiento contable — 2026-08-07

Auditoría contra "Recepciones → Movimientos → Facturas → Conciliación →
Cuentas por pagar → Pagos → Estados de integración": **Recepciones,
Movimientos, Facturas, Conciliación y Pagos ya estaban completos** — en
particular, Movimientos ya tiene un handler real
(`CanonicalPurchaseStockEntryHandler`) que entra a inventario con costo
promedio ponderado, y "Cuentas por pagar"/"Pagos" ya tenían pantalla
completa (`AccountsPayablePage`, `PaymentsPage`) con el ciclo Programar →
Autorizar → Ejecutar segregado. Un solo hallazgo real:

- **Bug de integridad financiera: `CreatePayableUseCase` reconocía el pasivo
  (CxP) sin ningún asiento contable.** El único asiento balanceado del ciclo
  de pago ocurría hasta *ejecutar* el pago (Debe CxP / Haber Tesorería) — el
  reconocimiento del pasivo en sí (al conciliar la factura) no generaba
  Debe Inventario/Gasto/Activo, violando la regla #11 de CLAUDE.md. El
  propio código ya documentaba el hueco (`procurement_payable_bridge.py`
  decía explícitamente: "routing it correctly requires the line's
  purchase_nature... which this event does not carry").
- **Causa raíz**: `SupplierInvoiceLine` no tenía `purchase_nature` (a
  diferencia de `PurchaseOrderLine`/`RequisitionLine`/`DirectPurchaseLine`,
  que sí lo tienen) — se perdía en el primer eslabón de la cadena.
- **Fix, en 5 capas**:
  1. `SupplierInvoiceLine.purchase_nature` (default `INVENTORY`, mismo
     patrón que el resto del dominio); `CaptureSupplierInvoiceUseCase` lo
     acepta por línea.
  2. `MatchSupplierInvoiceUseCase`/`ReleaseInvoiceVarianceUseCase` agregan
     subtotales pre-impuesto por naturaleza (`nature_subtotals`) al emitir
     `ACCOUNT_PAYABLE_CREATE_REQUESTED`.
  3. `downstream_translators.on_payable_created` reenvía `nature_subtotals`
     + `tax_total` en `PAYABLE_CREATED` (antes se perdían ahí).
  4. `ProcurementPayableBridgeHandler` postea el asiento de reconocimiento
     (Debe Inventario/Gasto/Activo por naturaleza + Debe IVA acreditable /
     Haber CxP) vía `PostingEngine`, usando `PostingPurpose.SUPPLIER_INVOICE`
     (ya existía en el enum, nunca se usaba). Payloads sin `nature_subtotals`
     (legacy) solo crean el `Payable`, nunca inventan una cuenta.
  5. `finance_bootstrap.py`: el perfil contable `PURCHASE` no tenía
     `expense_account_id` ni `asset_account_id` configurados — se agregaron
     (6130 "Gastos operativos", 1201 "Activo fijo"; `SERVICE` se enruta a
     `expense_account_id`, no tiene cuenta propia).
- **Regresión real encontrada al verificar**: el test existente
  `test_payable_created_reaches_finance_and_creates_real_payable` seguía
  pasando con el fix roto (perfil `PURCHASE` no sembrado → `FinanceDomainError`
  silenciada por el retry-on-failure del outbox dispatcher, que no
  propaga la excepción). Se corrigió sembrando `bootstrap_finance()` en el
  test y agregando `assert summary["failed"] == 0` — sin eso, un fallo de
  posteo queda enmascarado indefinidamente.
- **Entorno**: el `.venv` del proyecto apareció vacío a mitad de esta vuelta
  (solo `pip`) — se reinstalaron `pytest`, `PyQt5`, `cryptography`, `fastapi`,
  `fpdf2`, `matplotlib`, `pillow`, `pydantic`, `requests`, `pyOpenSSL`
  (inferidos de los imports reales del repo; no hay `requirements.txt`).
- **Verificación**: 397 tests de procurement + finance en verde; nuevo test
  de asiento mixto (`test_payable_recognition_entry_routes_by_purchase_nature_and_splits_tax`)
  prueba que una factura con líneas INVENTORY + EXPENSE debita dos cuentas
  distintas, no todo a Inventario.
- **Pendiente explícito**: "Estados de integración" del checklist se dio
  por cubierto con esta auditoría (las integraciones evento-driven
  Compras→Inventario/CxP/Tesorería ya estaban bien cableadas) — no se
  construyó ninguna pantalla nueva de monitoreo.

---

## Fase 6 (UI/UX enterprise): Finanzas y RRHH migran a SideNav/Worklist — 2026-08-08

Auditoría contra "Shell, Sidebar, Worklists, Master-detail, Command bars,
Tablas, Dashboard, Estados visuales, Accesibilidad táctil" — a diferencia de
Fase 4/5, el hueco no era funcional dentro de un módulo sino de
**consistencia del sistema de diseño entre módulos**: Compras/Inventario/
Productos ya usaban los componentes compartidos; Finanzas y RRHH
reimplementaban su propio sidebar (`QListWidget` crudo) y su propio
scaffold de listado (`FinancePage`/`HRPage`, sin paginación ni estados
vacío/error). "Command bars" no existe en ningún lado (no se construyó —
fuera del alcance elegido) y "Accesibilidad táctil" solo existe en el
teclado numérico, no en los botones base (tampoco tocado esta vuelta).

El usuario eligió el alcance grande: migrar Finanzas y RRHH al mismo
patrón, no solo documentar.

- **Nuevo `frontend/desktop/components/worklist_page.py::WorklistPage`** —
  extracción de `_ListPageBase` (que solo vivía dentro de
  `purchasing/pages/enterprise_pages.py`) a un componente genuinamente
  compartido. Soporta dos estilos de hook para no forzar una reescritura de
  las 26 páginas de Finanzas/RRHH:
  - override `_fetch()` (paginado/filtrado — patrón de Compras): el
    `_load()` por defecto lo invoca y llena la tabla.
  - override `_load()` directo (páginas simples — patrón de Finanzas/RRHH):
    llaman `self.set_table(model)` ellas mismas; la base igual decide el
    estado vacío después.
  `searchable`/`paginated` son ahora flags opcionales (default `True`,
  igual que Compras); Finanzas/RRHH los ponen en `False` porque sus
  métodos de presenter no aceptan `query`/`offset` todavía.
- **Compatibilidad de atributos**: las 26 páginas de Finanzas/RRHH ya
  usaban `self.table` (sin guion bajo) y `self._layout` directamente —
  `WorklistPage` expone ambos (alias de `self._table`) para no tener que
  tocar el cuerpo de ninguna página individual. `set_kpis()` sigue usando
  `modulos.ui_components.create_kpi_bar` (no se tocó — fuera de alcance).
  `notify(ok, message)` ahora es el aviso inline de Compras (nunca bloquea
  la pantalla), no `QMessageBox` — es el único cambio de UX visible en las
  26 páginas, y ninguna necesitó edición para adoptarlo (heredado del base).
- **Purchasing**: `_ListPageBase` en `enterprise_pages.py` pasó a ser una
  subclase de una línea (`icon = Icons.PURCHASES`) de `WorklistPage` — cero
  cambio de comportamiento, verificado con la suite completa de Compras.
- **`FinanceView`/`HRView`**: `QListWidget` crudo → `SideNav` (mismo
  patrón de `add_group()`/`add_section()` que usa
  `PurchasingModuleShell`). `FinancePage`/`HRPage` pasaron a ser
  subclases de dos líneas de `WorklistPage` (`searchable = paginated =
  False`). Bug menor de paso: `SideNav.add_group()` estaba definido dos
  veces de forma idéntica en `side_nav.py` — se eliminó el duplicado.
- **Sin capability gating**: se confirmó (no se tocó) que ni Finanzas ni
  RRHH filtran su sidebar por permisos — a diferencia de
  `PurchasingModuleShell`, que sí lo hace vía `visible_routes(capabilities)`.
  Explícitamente fuera del alcance de esta vuelta (es un cambio de
  autorización, no de sistema de diseño).
- **Verificación**: no existía ningún test de UI para Finanzas ni RRHH
  antes de esta vuelta. Se agregaron
  `tests/integration/finance/test_finance_ui_shell.py` y
  `tests/integration/hr/test_hr_ui_shell.py` — construyen la vista real
  contra una base de datos vacía recién sembrada (`bootstrap_finance`/
  `create_hr_schema`) y navegan **cada una** de las 19 + 9 páginas,
  confirmando que cargan sin excepción (ejercita el nuevo camino
  `ViewState.EMPTY` que ninguna tenía antes). Las 27 páginas cargaron a la
  primera, sin necesitar ajustes adicionales — confirma que el diseño de
  compatibilidad de atributos fue correcto.
- **Regresión real encontrada y corregida**: `test_purchasing_desktop_shell.py`
  buscaba los literales `"QSplitter"`/`"itemSelectionChanged"` directamente
  en el texto fuente de `enterprise_pages.py` — dejaron de estar ahí al
  moverse a `worklist_page.py`. Se actualizó el test para leer también el
  nuevo archivo compartido.
- **31 fallas pre-existentes descubiertas, no de esta vuelta**: esta fue la
  primera corrida de `tests/architecture/` completo (sin filtro) en toda la
  sesión — destapó fallas en módulos nunca tocados (Productos, Mermas,
  orquestador de refactor, migraciones de PK, menú lateral, etc.).
  Confirmado con `git status` que ninguno de los archivos involucrados en
  esas 31 fallas está entre los 11 archivos modificados esta vuelta — no
  se investigaron ni corrigieron (fuera de alcance).
- **2026-08-08 — LOSS-23, corte born-clean de Mermas**: eliminadas las rutas
  `waste`/`modulos.merma`, las tablas `mermas`, `inventory_waste_event` y
  `ajustes_inventario`, y las migraciones 097/129 que las recreaban. BI y
  reportes se repuntaron a `loss_cases`, `loss_lines` y
  `loss_classifications`. No hay rescate ni lectura dual; la base de desarrollo
  debe regenerarse. Detalle en `docs/refactor/LOSS_23_LEGACY_REMOVAL_REPORT.md`.
- **2026-08-08 — INV-1, catálogo canónico de permisos de Inventario
  (migración 179)**: `CANONICAL_MODULE_PERMISSIONS["INVENTARIO"]` pasó de un
  stub de 3 acciones (`ver`, `ajustar`, `transferir`) a ~70 acciones
  granulares (`almacen.*`, `ubicacion.*`, `movimiento.*`, `lote.*`,
  `reserva.*`, `conteo.*`, `ajuste.*`, `cuarentena.*`, `calidad.*`, `peso.*`,
  `bascula.*`, `recepcion.*`, `reposicion.*`, `temperatura.*`,
  `configuracion.*`, etc.), igualando el patrón ya usado por `COMPRAS`.
  `InventoryPermissions` (`backend/application/inventory/permissions.py`)
  cambió sus ~70 valores de `INVENTORY_*` (inglés) a `INVENTARIO.accion`
  (español canónico) manteniendo los mismos nombres de constante — cero
  cambios en los call sites que ya usaban `InventoryPermissions.X`.
  `InventorySessionPermissionChecker` perdió su puente
  `legacy_codes_for()` (que concedía cualquier mutación granular a quien
  tuviera el permiso legacy grueso `inventario.editar`, y cualquier lectura a
  `inventario.ver`) — ahora exige el código canónico exacto directamente en
  la sesión, igual que `ProcurementSessionPermissionChecker`. La migración
  179 es defensiva/documental como la 177: normaliza `modulo='INVENTORY'` →
  `'INVENTARIO'` si existiera, y **no** expande automáticamente
  `inventario.editar`/`ajustar`/`transferir` a las acciones granulares
  nuevas (escalamiento de privilegios prohibido) — un administrador debe
  otorgarlas explícitamente vía Configuración → Seguridad. Se retiraron
  también las 8 constantes `TRANSFER_*` no usadas por ningún caso de uso
  (el workflow de transferencias vive en el bounded context Transferencias,
  ver `docs/refactor/TRF-0_transfers_audit_and_plan.md`); la única gestionada
  por Inventario ahora es `IN_TRANSIT_VIEW` (`INVENTARIO.transito.ver`,
  sólo lectura). Se agregó `frontend/desktop/modules/inventory/capability_resolver.py`
  (`InventoryCapabilities`, mismo patrón que Compras) y se cableó
  `visible_entries()` (existía pero nadie la invocaba) en
  `page_registry.build_page_specs()`/`modulos/inventario_enterprise.py` para
  que la navegación lateral realmente oculte secciones sin permiso.
- **2026-09-04 — Compras UI, deduplicación de chrome + acciones al panel de
  detalle (sin cambios en `backend/`)**: `PurchasingModuleShell` renderizaba,
  antes del `QStackedWidget` de páginas, un `PageHeader` global ("Compras" +
  botón Actualizar), `ContextFilters`, un `KPIBar` global y un `AlertsBar`
  global — duplicando el `PageHeader` propio de cada página construida sobre
  `WorklistPage`. Se eliminó el `PageHeader`/`KPIBar`/`AlertsBar` del shell;
  el botón "Actualizar" se movió a la franja `ContextFilters` (única pieza de
  chrome global que sí es necesaria — el selector de almacén no existe en
  ningún otro lugar de la app) vía un nuevo método `ContextFilters.add_action()`.
  La clase `AlertsBar` se movió tal cual a
  `pages/procurement_dashboard_page.py` (su hogar natural — contenido de
  dashboard, no chrome de todas las páginas) y se pobló en `reload()` igual
  que antes (`self._alerts.set_alerts(self._presenter.analytics_alerts())`).
  `PurchasingModuleShell.reload()` conserva las badges de navegación del
  sidebar (`navigation_badges(kpis)`), que no dependían de los widgets
  eliminados.
  Por otro lado, `RequisitionsPage`/`QuotationsPage`/`OrdersPage`/
  `InvoicesPage` (en `pages/enterprise_pages.py`) fijaban sus botones de
  acción de negocio (Enviar/Aprobar/Rechazar/Crear RFQ/Crear orden/Compra
  directa, Capturar cotización/Comparar y adjudicar, Aprobar/Enviar/Recibir/
  Nueva versión, Conciliar/Liberar diferencia) en una fila fija debajo del
  splitter maestro-detalle vía `_build_row_actions()`, habilitándolos por
  estado con `_allowed_actions()` leyendo el texto de la celda de estado de
  la tabla (traducido a español). Esos botones se movieron a la barra de
  comandos propia de cada panel de detalle
  (`RequisitionDetailPanel`/`RfqDetailPanel`/`OrderDetailPanel` en
  `document_detail.py`, y el panel inline de `InvoicesPage` en
  `enterprise_pages.py`): se construyen una sola vez en `__init__` con las
  mismas fábricas de botón (`create_secondary_button` etc.), el
  `.setVisible(capabilities.xxx)` de cada uno se preservó exactamente igual
  que antes, y el habilitado/deshabilitado por estado ahora lee
  `detail.status`/`detail.awarded` directamente del DTO (código crudo, p. ej.
  `"APPROVED"`) en lugar de raspar el texto traducido de la tabla — mapas
  `_ACTIONS_BY_STATUS` nuevos en cada panel replican exactamente la misma
  lógica de habilitación que tenían los antiguos `_allowed_actions()`. Los
  manejadores de clic (`_submit`, `_approve`, etc.) permanecen en la página —
  el panel solo expone los botones (`panel.submit_button`, etc.) y la página
  los conecta con `.clicked.connect(...)` justo después de construir el
  panel en `_create_detail_panel()`, replicando el patrón ya existente de
  `page.direct_purchase_requested.connect(...)` en el shell — sin
  registro de callbacks genérico. Cuando `load_detail(None)` (nada
  seleccionado), la barra de comandos completa se oculta
  (`self._commands.setVisible(False)`) en vez de mostrar botones
  deshabilitados. `_build_row_actions`/`_allowed_actions` se eliminaron por
  completo de `enterprise_pages.py`; los no-ops de `WorklistPage` hacen que
  la fila de acciones desaparezca (solo queda la paginación
  Anterior/Siguiente cuando `paginated=True`).
  **Verificación**: `pytest tests/architecture/test_purchasing_desktop_shell.py
  tests/unit/procurement/ tests/integration/procurement/ -q` → 303 passed.
  Chequeo de sintaxis global sobre todo el árbol → sin errores. Smoke-import
  de `ModuloComprasEnterprise`/`create_enterprise_purchasing_view`/
  `PurchasingModuleShell` → OK.
  `tests/ui/test_purchasing_visual_closure.py` corre con
  `QT_QPA_PLATFORM=offscreen` (ya lo fija el propio archivo); 6 de 8 casos
  fallan mas son pre-existentes y ajenos a este cambio — ocurren enteramente
  dentro de `DirectPurchaseCreatePage`
  (`_DirectPresenter` de prueba no tiene `.capabilities()`) y
  `LogisticsRelatedPage` (ancho renderizado no coincide con el tamaño de
  ventana bajo el backend offscreen), ninguno de los cuales se tocó en esta
  vuelta; confirmado con `git status` que ambos archivos ya estaban
  presentes sin relación a los 5 archivos modificados aquí (shell, páginas
  de enterprise, panel de detalle, dashboard, test de arquitectura).

## Precios — migración 260: las acciones de `PRECIOS` llegan a `rol_permisos` (2026-09-17)

Migrar el vocabulario de Precios a `PRECIOS.<accion>` (decisión del usuario,
misma vuelta) hizo sus permisos **otorgables** desde Configuración → Seguridad →
Permisos, pero no se los otorgó a nadie. Medido en la base viva
(`data/spj_pos_database.db`): `SELECT COUNT(*) FROM rol_permisos WHERE
modulo='PRECIOS'` → **0**, y `SELECT COUNT(*) ... WHERE modulo='*' OR accion='*'`
→ **0** (no existe mecanismo de comodín en los datos). El módulo seguía siendo
operable sólo por el rol `admin`, que pasa por `ADMIN_ROLE_NAMES` en
`PermissionQueryService` sin consultar la base.

**El hallazgo que motivó la migración**: `system_owner` —el dueño de la
instalación, creado por `CreateInitialOwnerUseCase`— tiene 95 filas enumeradas en
`rol_permisos` y **ninguna de `PRECIOS`**, y NO está en `ADMIN_ROLE_NAMES`
(admin/superadmin/administrador), aunque sí está en `_ADMIN_ROLES` de
`backend/bootstrap/application_context.py`, que alimenta `is_admin()`. Dos listas
distintas para la misma pregunta. Consecuencia concreta y medida: el dueño de la
instalación **no podía autorizar un precio bajo mínimo** mientras que `admin` sí.
La divergencia entre ambas listas es PREVIA a este cambio y no se tocó aquí:
alinearlas concedería el comodín global `{"*"}` a ese rol en todo el ERP, que es
un ensanchamiento de privilegio y una decisión aparte.

**Deuda declarada, no resuelta**: la migración 206 siembra `system_owner` con un
producto cartesiano `_MODULOS × _ACCIONES` congelado en el código. Como
`INSERT OR IGNORE` ya corrió y esa lista no se deriva de
`CANONICAL_MODULE_PERMISSIONS`, todo módulo nacido después queda fuera en
silencio. `PRECIOS` es el primer caso; el próximo contexto acotado tendrá el
mismo problema. Derivar el sembrado del catálogo es la solución de raíz y se
descartó deliberadamente: aplicarla retroactivamente a instalaciones existentes
es una decisión de escalamiento de privilegios por derecho propio.

**Alcance**: `system_owner` y `admin` reciben las 23 acciones; `gerente` recibe
el juego operativo (19) **incluida `precio.minimo.excepcion`**, que es lo único
que vuelve alcanzable la autorización en caliente. `cajero` y `solo_lectura` no
reciben nada. Un rol ausente se omite, nunca se crea. Idempotente por
`UNIQUE(rol_id, modulo, accion)`, verificada en la base viva
(`sqlite_autoindex_rol_permisos_2`).

**Verificación**: `tests/integration/pricing/test_precios_permissions_seed.py`
(10 casos) — incluye uno que compara la lista transcrita en la migración contra
`ALL_PRICING_PERMISSIONS`, para que una errata o una acción olvidada se vean en
el test y no en producción.

## Proveedores — migración 261: `supplier_contacts.whatsapp_e164` (2026-09-17)

WhatsApp era uno de los grupos de datos del proveedor que faltaban. El contacto
sólo tenía `phone_e164`, y tratar ese número como WhatsApp es falso en la
práctica: el fijo de oficina y el móvil del contacto no coinciden, y WhatsApp es
el canal que esta instalación usa de verdad para pedidos y avisos.

**Dos patas, porque el esquema no tiene mecanismo de columna guardada.**
`backend/infrastructure/db/schema/supplier_schema.py` es DDL de creación pura
(`_DDL` + `_INDEXES` aplicados por `create_supplier_schema()`, todo
`CREATE TABLE IF NOT EXISTS`); medido: cero apariciones de `ALTER TABLE`,
`_column_exists` o `PRAGMA table_info` en ese archivo. Así que la columna se
añadió al `CREATE` —para instalaciones NUEVAS— y esta migración hace el `ALTER`
guardado para las EXISTENTES, a las que un `CREATE TABLE IF NOT EXISTS` no les
añade nada. Idempotente por `PRAGMA table_info`, no por `try/except`, que
también taparía un error distinto.

**Cadena completa, verificada eslabón por eslabón antes de escribir** (el riesgo
real de este cambio no es el `ALTER`, es que el dato se pierda en un salto
intermedio sin error visible): entidad `SupplierContact`, `_COLS` del
repositorio (12 → 13 columnas y marcadores del `INSERT`), hidratación en
`_to_entity`, `SELECT` de `SupplierDetailQueryService.contacts()`, fila del
presentador, columna de la tabla en la ficha, y campo del diálogo.
`AddSupplierContactUseCase` acepta `**fields` y `SupplierContact.create`
reenvía `**kwargs` al constructor, así que la capa de aplicación no necesitó
cambios.

**Decisión de captura**: el campo usa `PhoneInput`, el mismo componente que el
teléfono, porque es E.164 igual que él (regla §19); como texto libre entrarían
números que el canal de WhatsApp no puede usar. De paso se añadió validación al
TELÉFONO, que no se validaba (sólo el correo): `PhoneInput.is_valid()` acepta
vacío cuando no es obligatorio, así que nada de lo que hoy se guarda deja de ser
válido — sólo deja de aceptarse un número mal formado.

**Verificación**: `tests/integration/suppliers/test_supplier_whatsapp_migration.py`
(6 casos) prueba LAS DOS patas — que una instalación nueva ya trae la columna y
que la migración la añade a una tabla antigua—, además de idempotencia,
conservación de las filas existentes y el caso de tabla ausente.

## Proveedores — migración 262: contado/crédito y forma de pago preferida (2026-09-17)

Añade `is_credit` y `preferred_payment_method` a `supplier_commercial_terms`.
Las formas de pago válidas fueron **decisión del usuario**: Transferencia (SPEI)
y Efectivo — `PaymentMethod` sólo declara esas dos. Antes no existía ningún enum
de formas de pago en `backend`.

`PaymentTerms.is_credit` es `None` por defecto y se DERIVA de `credit_days > 0`,
para que las condiciones ya capturadas sigan siendo válidas; contado con días de
crédito o crédito sin días se rechazan. La migración RELLENA `is_credit = 1`
donde `credit_days > 0`: sin eso esas filas se hidratarían como "contado con días
de crédito" y la ficha del proveedor dejaría de abrir. `preferred_payment_method`
queda NULL en filas viejas — no hay de dónde deducirlo.

Mismo hallazgo de siempre: la pestaña "Condiciones" mostraba un texto FIJO; las
condiciones se guardaban y no se veían nunca. Se añadió
`SupplierDetailQueryService.commercial_terms()` y el resumen en la ficha.

**Verificación**: `tests/integration/suppliers/test_supplier_payment_terms_mode.py`
(11 casos). Suites de Proveedores 100 → 111. Ningún otro contexto importa el
`PaymentTerms` de Proveedores (Compras y Crédito tienen homónimos propios).

## Transferencias: el DESTINO también se comprueba contra las sucursales del usuario (2026-09-17)

**Decisión del usuario**, tomada sobre el hueco que quedó señalado al cerrar el
alcance por sucursal: el origen sí se comprobaba y el destino no.

`TransferAuthorizationPolicy.require` acepta ahora `destination_branch_id` (más
almacén y ubicación, ignorados igual que en el origen) y `CreateTransferRequest`,
`Edit`, `Submit`, `Approve` y `Reject` lo pasan. Se eligieron ESOS CINCO y no
todos los casos de uso: el resto ya seguía una regla correcta y distinta —cada
operación pide la sucursal donde OCURRE físicamente, surtido/empaque/despacho/
reserva el origen y recepción/recepción a ciegas/diferencias el destino—. Lo que
no encajaba era el ciclo de la solicitud, que compromete stock en las DOS.

**Consecuencia operativa, que no es menor**: quien alcance una sola sucursal ya
no puede crear ninguna transferencia, porque el destino es por definición otra.
Hace falta tener ambas sucursales en el alcance (`usuarios_sucursales`, o el
comodín del administrador). Esto no es un efecto colateral del cambio: la
pantalla ya lo imponía —`branch_options()` alimenta los dos desplegables con las
sucursales permitidas— y el backend es el que iba por detrás. Una regla que sólo
vive en la pantalla no protege a quien no usa la pantalla.

El mensaje de error dejó de decir "origen o destino" sin saber cuál y ahora
nombra la pata que falló, que es lo que permite pedir el permiso correcto.

**Pendiente relacionado**: `TransferRequirementEventHandler` (reposición de POS y
pedidos de cliente) crea solicitudes con `event["user_id"]`. Hoy NO está suscrito
en ningún sitio, así que no le afecta; el día que se conecte, el usuario que
dispara el evento necesitará alcance sobre ambas sucursales.

**Verificación**: `tests/integration/transfers/test_create_transfer_request_e2e.py`
(8 casos; el nuevo `test_a_destination_outside_the_users_branches_is_rejected`
comprueba además que no queda ninguna transferencia escrita).

## Precios: la sección "Configuración" deja de ser una ruta muerta (2026-09-17)

`pricing_settings` estaba declarada en `navigation.py` desde PRC-7 y `build_page`
devolvía `None`: la sección abría con "Esta sección aún no está construida". El
contador de `test_placeholder_routes_ratchet.py` pasa de `(5, 6)` a `(6, 6)`.

**No se creó tabla de configuración de Precios, a propósito.** Los parámetros de
este módulo no son interruptores guardados aparte, son consecuencia de los datos:
qué lista base rige, en qué moneda se cobra, con qué método se costea, cuántos
precios tienen mínimo, cuántos están acotados a una sucursal. Inventar una tabla
de ajustes habría producido controles que no gobiernan nada — peor que no tener
la pantalla, porque el usuario cambiaría un valor y el módulo seguiría igual.

La pantalla es de LECTURA y su columna de nota es la parte que importa: cero
listas base activas, dos listas base activas, varias monedas conviviendo o ningún
precio con mínimo son configuraciones rotas que, si sólo se imprime el valor, se
ven idénticas a las correctas.

**Verificación**: `tests/integration/pricing/test_pricing_settings_page.py`
(13 casos), uno de ellos la guardia general de que ninguna sección declarada en
el menú de Precios vuelva a quedarse sin página. Suites de Precios: 174 passed.

## Menú lateral: el test de navegación exige TODOS los módulos (2026-09-17)

`test_migrated_modules_navigation.py` fijaba nueve entradas (las de SHELL-16)
mientras `MIGRATED_MODULES_NAVIGATION_ITEMS` ya tenía dieciocho: tres casos
fallaban desde que se registraron Configuración, BI, Mermas, Producción, Pedidos,
Fidelización, Tarjetas, Activos y Precios.

Además de ampliarlo, los módulos **se descubren del disco**
(`frontend/desktop/modules/*/shell_registration.py`, estático con `ast`). Una
lista escrita a mano no puede detectar el fallo que este archivo existe para
evitar, y que el repositorio ya cometió dos veces —Activos con 12 archivos de UI
y Precios con seis páginas, ambos construidos y sin entrada en el menú—: el
olvido consiste justamente en no añadirse a la lista.

**Verificación**: 61 passed en `tests/unit/shell/sidebar/` y compañía; 371 passed
en `tests/integration/shell` + `tests/unit/shell`.

## SUP-6 — un solo maestro de proveedores (migración 263, 2026-09-17)

**Decisión del usuario**: corte completo, migración sólo registrada (no ejecutada
contra la base real).

### Lo que estaba roto, medido ejecutándolo

Había DOS buscadores de proveedores contra DOS tablas, con resultados
**disjuntos**:

    Módulo Proveedores -> `supplier_master`   (el maestro canónico)
    Compras            -> `proveedores`       (la tabla heredada)

y **nada en el código de producción escribía en `proveedores`** — sólo los tests.
Consecuencia: un proveedor dado de alta y aprobado hoy **no se podía elegir al
crear una compra**, y los heredados no aparecían en el módulo. No era un
descuido: la migración 119 dejó escrito que esos lectores migrarían "en SUP-6";
para Compras nunca ocurrió.

Agravante: `SupplierDirectoryQueryService.require_eligible` —la puerta que
autoriza la compra— leía también la tabla heredada. Aunque se arreglara sólo el
buscador, la compra se habría rechazado con "El proveedor canónico no existe".
Buscador y puerta tenían que moverse juntos, y ahora **comparten la misma
definición de "comprable"** (`is_purchasable`).

### Qué se hizo

* `supplier_search_query_service.py`: UN contrato (`SupplierSearchQuery`) y UN
  constructor de SQL, con presets que sólo AÑADEN restricciones — misma forma que
  `product_selection_query_service`. `SupplierDirectorySearchQueryService` (el
  módulo, ve borradores y pendientes) y `SearchProcurementSuppliersQueryService`
  (Compras).
* Migración **263**: copia los heredados al maestro **conservando el id**, porque
  `purchase_orders`, `direct_purchases`, `compras`, `recepciones`,
  `goods_receipts`, `supplier_invoices`, `contenedores` y las cotizaciones
  guardan `supplier_id` apuntando ahí. `proveedores.id` ya era TEXT/UUID, así que
  conservarlo no reintroduce identidades de otro tipo.
* Los ~21 JOIN de nombre y la puerta de elegibilidad, migrados. **Cero lectores
  de `proveedores` quedan en `backend/` ni `frontend/`.**

### Tres cosas que costó ver

1. **Los bloqueos.** `proveedores` los marca con dos columnas
   (`compras_habilitadas`, `bloqueado_financiero`) y el maestro con filas de
   `supplier_blocks`. Copiar sólo los datos habría **desbloqueado en silencio** a
   quien estaba bloqueado, volviéndolo elegible para comprar. La 263 traduce cada
   marca a su bloqueo. `PAYMENT_BLOCK` cuenta como impedimento para comprar
   porque en el modelo heredado `bloqueado_financiero` lo era.
2. **Columnas ambiguas.** `supplier_master` comparte nombres con las tablas de
   compras (`status`, `notes`, `active`, `created_at`). Al cambiar el JOIN, un
   `status` sin calificar volvía la consulta ambigua y `_query` se tragaba el
   `OperationalError` devolviendo `[]`: la pantalla quedaba vacía **sin ningún
   error**. Se resolvió uniendo una subconsulta acotada a `id, legal_name`, que
   elimina todas las colisiones de golpe en vez de ir descubriéndolas una a una.
3. **La normalización no acertaba nunca.** El maestro guarda `normalized_name`
   sin acentos ni espacios (`carnesdelnortesa`), y la búsqueda comparaba contra
   el texto en crudo (`LIKE '%carnes del%'`). Esa rama no coincidía jamás en
   cuanto el término tenía un espacio o un punto; sólo funcionaba por
   `legal_name`. Ahora el texto se normaliza igual que lo almacenado. Ojo: en
   Productos NO se pliegan acentos — la regla es normalizar igual que escribe el
   maestro de CADA contexto, no plegar siempre.

### Un fallo abierto que se cerró de paso

`SupplierProfileAdapter` devolvía, en el MISMO objeto, `active_blocks =
("PAYMENT_BLOCK",)` y `purchasing_enabled = True`: reportaba el bloqueo y a la
vez decía que se podía comprar, porque la elegibilidad se resolvía contra
`proveedores`, donde ese proveedor no tenía fila, y la ausencia degradaba a
permisivo. Un test fijaba ese comportamiento con el comentario "degrades to
permissive defaults". Ahora ambas salen del maestro y coinciden.

### Explicación del vacío

Se añadió `explain_empty` (SIN_PROVEEDORES / SIN_APROBAR / NO_COINCIDE /
BLOQUEADOS_PARA_COMPRAS) y se conectó a los campos de proveedor de Compras
—que aceptaban `empty_reason_provider` y nunca lo recibían, al revés que los de
producto— y al estado vacío del listado, que decía siempre "No hay proveedores
que coincidan" incluso con el catálogo vacío.

### Verificación

`tests/integration/suppliers/test_supplier_search_contract.py` (23 casos, el
central es `test_the_module_and_purchasing_see_the_same_suppliers`) y
`test_supplier_legacy_cutover_migration.py` (15 casos: id preservado, bloqueos
preservados, reejecución sin duplicar ni pisar lo capturado después).

Las pruebas de Compras y Logística NO se reescribieron para sembrar el maestro:
siguen sembrando lo heredado y pasan por la 263 mediante
`tests/integration/_supplier_cutover.py`, así que cada una prueba además que el
corte no rompe lo que ya funcionaba.

Suites `suppliers` + `procurement` + `logistics`: **433 → 475 passed**, cero
fallos.

## Fase 1 — la sucursal se ELIGE en Compras y en Precios (2026-09-17)

Reportado por el usuario: "en el módulo de compras no es posible seleccionar
sucursales en los diálogos". Confirmado, y peor de lo que sugiere el reporte.

### Lo que había

`RequisitionFormDialog` y `OrderFormDialog` capturaban la sucursal con
`StandardLineEdit`, una caja de TEXTO LIBRE. En la solicitud arrancaba **vacía**:
para crear una solicitud de compra había que escribir a mano el UUID de la
sucursal, así que en la práctica no se podía crear ninguna. En la orden venía
rellenada con la sucursal de la sesión, pero cambiarla exigía teclear otro UUID.

Viola §20 del prompt ("donde se seleccione … sucursal … debe usarse barra de
búsqueda/autocomplete") y es justo lo que la Fase 1 exige.

El almacén estaba igual, y con un agravante: `warehouse_options()` ya existía en
el presentador, acotado a la sucursal activa, y **nadie la llamaba**.

### Lo mismo en Precios

El barrido por el mismo patrón encontró `ProductPriceFormDialog` y
`BulkPriceDialog` con `StandardLineEdit(placeholder="Sucursal (vacío = todas)")`.
El diálogo de lote dice en su propio docstring que pedir un identificador
escrito a mano es pedirle al usuario un dato que no puede conocer — lo decía de
la categoría, mientras la sucursal justo debajo era exactamente eso.

### Qué se hizo

`branch_options()` en los presentadores de Compras y de Precios, resuelto con
`BranchScopeQueryService` y **acotado al alcance del usuario**: mismo orden que
Transferencias (`usuario → permitidas → consulta → resultados`), nunca listar
todas y esconder en la pantalla. Los cuatro diálogos usan ya `SearchableComboBox`.

En Precios el vacío SIGNIFICA algo (el precio rige en todas las sucursales), así
que "Todas las sucursales" es una opción explícita de la lista y no el resultado
de dejar un campo en blanco.

### Dos decisiones que evitan un daño silencioso

1. **La orden no inventa una sucursal que no se le ofreció.** Si la sucursal de
   la solicitud no está en el alcance del comprador, el campo queda VACÍO y el
   backend rechaza. Sustituirla por otra sería surtir a una sucursal distinta de
   la que pidió.
2. **Editar un precio no ensancha su alcance.** Si el precio editado está acotado
   a una sucursal fuera del alcance del usuario, esa sucursal se AÑADE a la lista
   para conservarla. Sin eso el combo caería en "Todas" y, como el caso de uso
   hace upsert por (lista, producto, sucursal), guardar habría creado un precio
   para TODAS en vez de modificar el de esa sucursal. No es fuga: la sucursal
   viene del renglón que el usuario acaba de abrir.

La preselección en la solicitud usa un ayudante que traga el error de
`default_branch()`: ese método LEVANTA cuando la sesión no trae sucursal activa,
y dejarlo propagar impediría abrir el diálogo para elegirla a mano — que es justo
lo que este arreglo habilita.

### Verificación

3 casos nuevos en `tests/integration/procurement/test_enterprise_ui.py` (incluido
`test_the_order_dialog_does_not_invent_a_branch_it_was_not_offered`) y 9 en
`tests/integration/pricing/test_pricing_branch_selector.py`. El fixture de
Compras necesitó la tabla `usuarios`: sin ella el alcance sale vacío — el fallo
cerrado correcto, pero deja el combo sin nada que ofrecer.

Suites pricing + procurement + suppliers + logistics: **655 passed**.

Barrido final: no queda ningún campo de texto libre para SELECCIONAR sucursal en
`frontend/`. Los `StandardLineEdit` de Configuración son para CREAR una sucursal
(razón social, RFC, dirección), no para elegirla.

## Fase 1 — Direcciones: un estándar para todos los módulos (migración 264, 2026-09-17)

**Decisiones del usuario**: un estándar utilizable en todos los módulos; API de
mapas tipo Mapbox **configurable desde Configuración**; autocompletar **a partir
del 5.º carácter**; cadena **Mapbox → Nominatim → manual**; conectar **todas las
pantallas de una vez**.

### Lo que había, medido

* `AddressInput` existía y **ninguna pantalla lo construía** (sólo pruebas). Su
  proveedor por omisión era `lambda _query: []`, disparaba desde la primera tecla,
  y `value()` devolvía sólo la etiqueta: tiraba la latitud y la longitud.
* **La geocodificación con Mapbox se construyó y se perdió.** El commit `42f0ed01`
  tenía proveedor Mapbox v6, respaldo Nominatim, caché LRU+TTL, workers
  asíncronos y **mínimo de 5 caracteres**. Vivía en `core/` y se borró con el
  legacy; sólo quedó `tests/architecture/test_address_uses_geocoding_service.py`,
  que apuntaba a tres archivos inexistentes y fallaba siempre.
* Cada módulo capturaba la dirección a su manera: Delivery en seis cajas de texto,
  Proveedores en cinco, Configuración en una (×3 diálogos), y Clientes en ninguna:
  `AddCustomerAddressUseCase` estaba completo y **sin ningún llamador**.
* Tres mecanismos construidos y nunca usados: las columnas `latitude`/`longitude`/
  `geocoding_source`/`validation_state` de `supplier_addresses`; `OrderAddress.
  mark_geocoded` (el caso de uso de captura de pedidos tiraba las coordenadas); y
  el propio `AddCustomerAddressUseCase`.

### Lo construido

* `backend/application/addresses/address_search.py`: el valor `StructuredAddress`,
  el puerto de proveedor, `AddressSearchService` con la cadena, y
  `MIN_QUERY_CHARS = 5` como **única fuente** de la cifra.
* `backend/infrastructure/maps/`: `MapboxAddressProvider` (v6, parsea el contexto
  completo —calle, número, colonia, municipio, estado, C.P.—, no sólo la
  etiqueta), `NominatimAddressProvider`, caché y la fábrica que lee
  Integraciones.
* `AddressInput` reescrito: consulta en `QThreadPool` con `request_id` para
  descartar respuestas viejas, espera a que se deje de escribir, rellena campos
  editables que son también la captura manual.
* **Configuración sin inventar nada**: Integraciones ya tenía CRUD real de
  definiciones, instancias y credenciales, `IntegrationCategory.LOCATION` ya
  existía y el token vive en el almacén de secretos. La **migración 264** siembra
  MAPBOX (instancia **inactiva**: todavía no hay token) y NOMINATIM (activa).
  Para activar Mapbox: Integraciones → Mapbox → Credenciales →
  `mapbox_access_token` → pegar el token → Activar.
* Conectado en: Proveedores (domicilio), Delivery (nuevo pedido), Configuración
  (empresa, alta y edición de sucursal) y **Clientes** (botón nuevo "Agregar
  dirección" en la ficha).

### Reglas que no son opcionales

* **Nominatim prohíbe el autocompletado** del lado del cliente en su servidor
  público, y limita a una petición por segundo. Por eso declara
  `supports_autocomplete = False` y el servicio NO lo llama mientras se escribe:
  responde `NEEDS_EXPLICIT_SEARCH` y la pantalla pide **Enter**. El respaldo
  existe; sólo cambia el gesto. El límite de una por segundo se hace cumplir con
  un candado de proceso.
* **Mapbox: geocodificación permanente.** Los resultados por omisión de su API son
  "temporales" y sus condiciones no permiten guardarlos. Este ERP guarda las
  coordenadas, así que se pide `permanent=true`. Si la cuenta no lo tiene
  contratado responde 403, la cadena pasa al respaldo y el motivo se ve.
* **Falla ≠ cero coincidencias.** Sólo una FALLA pasa al siguiente proveedor. La
  versión perdida devolvía `[]` ante todo, y un token caducado se veía igual que
  una calle inexistente.
* **Corregir a mano descarta las coordenadas.** Cambiar calle, número exterior,
  colonia, municipio, estado o C.P. tras elegir una sugerencia invalida lat/lon;
  guardarlas mandaría al repartidor a otro sitio. Interior y referencias no.

### Defectos atrapados por las pruebas antes de llegar a producción

1. **La caché compartida no se habría usado nunca.** `AddressSearchCache` define
   `__len__`, así que una caché vacía es falsa en Python y `cache or _NoCache()`
   la descartaba siempre.
2. **Sin el esquema de Integraciones se perdía también el respaldo** Nominatim,
   que no necesita configuración.
3. **Enter cerraba el diálogo.** En un `QDialog`, Enter en un `QLineEdit` activa
   el botón por defecto; como Enter es el gesto para buscar con Nominatim, buscar
   una dirección habría cerrado Proveedores/Clientes/Configuración a medio
   capturar. Comprobado con un `QLineEdit` normal antes de arreglarlo.

### Verificación

`tests/integration/addresses/` (66 casos: servicio, proveedores sin red,
configuración desde Integraciones, componente con hilos reales, extremo a extremo
por pantalla). La guardia de arquitectura se reescribió y ahora vigila el
estándar (7 casos; se comprobó que habría atrapado el código anterior). Delivery
ganó `test_a_geocoded_address_reaches_the_order_with_its_coordinates`.

Regresión: todas las suites afectadas iguales a la línea base; los fallos previos
(3 de MercadoPago en integraciones, 6+1 de `test_crm_21_*` en clientes) son
**exactamente los mismos nombres**. Delivery pasó de 235+1 fallo a 237 sin
fallos; el nombre del fallo previo no se imprimió, así que no se atribuye.

**Verificado contra el servicio real — sólo Nominatim**: una consulta explícita
("Avenida Juárez 100, Cuauhtémoc, CDMX") devolvió calle, número, colonia, C.P. y
coordenadas correctas. Destapó un detalle que ninguna documentación dejaba ver:
en la Ciudad de México la alcaldía viene en `borough` y `city` repite el estado,
así que el municipio salía "Ciudad de México". Se corrigió poniendo `borough`
primero y se fijó con una prueba sobre la forma real de la respuesta.

**Pendiente, no hecho**: Mapbox NO se ha probado contra su servicio real —no hay
token configurado—; su parseo se escribió contra el formato documentado de la
API v6. Conviene hacer una búsqueda real en cuanto se cargue el token.

## Fase 2 — Productos es la ÚNICA fuente de recetas (migración 265, 2026-09-18)

Re-auditoría de la Fase 2 contra el §12/§13 del prompt ("No crear un segundo
catálogo de recetas… `products` debe poseer la definición de receta/rendimiento;
`meat_processing` debe ejecutar esas definiciones"). La sesión anterior había
cerrado la otra mitad: Producción liberaba órdenes sin receta porque el puerto
estaba conectado a un nulo. Eso sigue en pie (5/5 pruebas).

### Lo que se midió

* Producción NO tiene catálogo de recetas propio: sus tablas son de ejecución
  (`process_outputs`, `yield_reconciliations`…). ✔
* Pero existían **tres** catálogos de recetas, y la explosión de COMPRAS (viva:
  se suscribe al arrancar) leía los dos que no eran el canónico:

      recipes / recipe_versions / recipe_components   ← lo escribe Productos
      product_recipes / product_recipe_components      ← nadie lo escribe
      recetas / receta_componentes                     ← nadie lo escribe

  Una receta creada hoy en Productos **nunca se aplicaba al comprar**.
* Ventas, la reconstrucción inversa, Producción y Mermas ya leían el canónico.

### Lo que se hizo

1. `purchase_recipe_explosion_bridge.py` usa la MISMA pareja que Ventas
   (`RecipeRepository.active_version_for_product` + `RecipeExplosionService`):
   una sola regla de explosión y una sola fuente. Dos cambios deliberados: sólo
   explota la versión ACTIVA (el legacy aceptaba cualquier receta con `activo=1`)
   y se incluye la merma de la receta, igual que Ventas.
2. **Migración 265.** Al llevar la explosión al canónico, las pruebas destaparon
   que **la 152 —el backfill legacy→canónico— dejaba toda receta migrada
   ilegible**: escribía `output_type='MAIN'` (el enum tiene `MAIN_PRODUCT`) y
   copiaba `tipo_receta` legacy tal cual (`PRODUCCION`, `COMBINACION`,
   `SUBPRODUCTO`, o `PROCESSING` por omisión), ninguno válido en `RecipeType`.
   La 265 traduce SÓLO lo que el legacy deja escrito (migración 085):
   `PRODUCCION→PRODUCTION_BOM`, `COMBINACION→SALES_EXPLOSION`,
   `PROCESSING→PROCESSING_RECIPE`. **`SUBPRODUCTO` no se adivina**: según la 085
   el dueño de esa receta es el producto que se DESPIEZA, y la 152 la copió al
   revés; queda legible (`PROCESSING_RECIPE`) pero sus versiones activas pasan a
   `UNDER_REVIEW` para que no consuman inventario hasta que alguien la
   clasifique. La 152 no se tocó (ya aplicada en bases reales): la 265 corre
   siempre justo después, en instalaciones nuevas y existentes.

Sin riesgo de datos: en la base real los tres catálogos están vacíos y la 152 ya
estaba aplicada (medido en sólo lectura).

### Verificación

`test_purchase_recipe_explosion_flip.py` 3 → 6 (los casos legacy ahora pasan por
152+265 como en una base real; nuevos: receta creada en Productos, borrador que
no explota, base sin esquema de Productos) y `test_recipe_backfill_type_repair.py`
(10, incluido uno que fija que sin la 265 la receta migrada es ilegible).
Productos 497 → 507, Inventario 585 → 588; los fallos previos (19+2 y 3+19) son
los mismos nombres.

### Hallado y NO hecho — pertenece a la Fase 10 (Meat Processing)

El §13 también pide que Producción registre esperado, real, diferencia,
rendimiento %, merma %, costo por output, lote origen y lote destino. Medido:

* La raíz de composición de Producción sólo conecta 4 casos de uso (crear,
  aprobar, liberar, cerrar orden). `RecordProcessOutputsUseCase` y
  `ReconcileYieldUseCase` **no tienen ningún llamador**: capturar lo producido y
  conciliar el rendimiento no es alcanzable desde la aplicación.
* `ReconcileYieldUseCase` recibe lo ESPERADO como parámetro en vez de derivarlo
  del perfil de rendimiento de Productos que la orden ya referencia; y concilia
  TOTALES por orden, no por producto de salida como pide el ejemplo del §13.
* Mermas (`production_loss_repository`) sí lee el esperado por salida
  (`yield_outputs.expected_yield_pct`) del catálogo canónico: la fuente existe.

Aparte: `backend/infrastructure/db/repositories/product_repository.py`
(`ProductRepository`) lee `productos` y `product_recipes` y no lo importa ningún
código de producción, sólo dos pruebas. Código muerto, no borrado aquí.

## Fase 3 — Compras: "no permite crear solicitud" y "permite confirmar una compra rápida" (2026-09-18)

Reportado por el usuario. Ambos síntomas se REPRODUJERON antes de tocar nada,
contra una COPIA de la base real (`data/spj_pos_database.db` no se tocó), con la
sesión construida como en el inicio de sesión real (`ApplicationContextBuilder` +
`LegacySessionAdapter`) y el cableado de eventos del arranque.

### "No permite crear nueva solicitud" — era la pantalla, no el backend

El caso de uso creaba la solicitud sin problema. Simulando teclado y ratón:
* Escribir el producto y pulsar **Enter cerraba el diálogo** sin líneas: el
  buscador sólo elegía con CLIC, y en un `QDialog` Enter activa "Aceptar".
* Escribir el producto sin clic en el resultado: "Agregar" **no hacía nada y no
  avisaba**.
* "Aceptar" sin líneas cerraba el diálogo y el aviso llegaba **después**, con la
  captura perdida.
* Además, editar el texto tras elegir no borraba la selección: "Agregar" añadía
  el producto ANTERIOR.

Arreglado en el componente compartido `EntitySearchInput` (↓/↑ recorren, Enter
elige el resaltado —el primero se resalta tras cada búsqueda—, Enter nunca llega
al diálogo, editar invalida la selección). Lo usan **14 pantallas de 7 módulos**,
así que el arreglo vale para todas. En `_LinesEditor`: "Agregar" dice por qué no
agrega, Enter en cantidad/precio agrega la línea. Los diálogos de solicitud y de
orden validan ANTES de cerrarse, incluido "producto capturado sin agregar".

### "Permite confirmar una compra rápida" — confirmaba lo que no debía

Medido: se creaba Y confirmaba, y la mercancía entraba al inventario, con
* un producto **en revisión** (no activo);
* el almacén de **otra sucursal**;
* **costo unitario cero** (hundía el costo promedio);
* pagos de contado **que no se podían contabilizar**.

El último es el más serio. La instalación tiene Caja general, Banco y Procesador;
**no tiene caja chica**. Midiendo las 5 fuentes que ofrecía la pantalla: sólo
Transferencia y Mercado Pago generaban asiento. Caja chica, Cuenta de tesorería y
Tarjeta autorizada se confirmaban **sin asiento contable** (CLAUDE.md §11): el
puente contable registraba una advertencia y la compra quedaba pagada. La
decisión de no adivinar la cuenta (sesión anterior, aprobada por el usuario) era
correcta; lo que faltaba es que la CONFIRMACIÓN se enterara.

Arreglado:
* `resolve_purchase_treasury_account` / `purchase_posting_problem`: la regla del
  puente, extraída a una función que usan el puente al asentar, la confirmación
  al validar (`PaymentSourceBookingPort` + `ProcurementPaymentSourceBookingAdapter`)
  y la pantalla al ofrecer fuentes. No pueden discrepar. Incluye el perfil
  contable PURCHASE, sin el cual el puente también fallaba después de confirmar.
* Crear y confirmar validan producto ACTIVO y comprable y almacén de la sucursal
  que admite compras; confirmar además revalida al proveedor (pudo bloquearse
  desde el borrador). Puertos existentes, sin SQL nuevo.
* **Costo > 0 en el dominio** (decisión del usuario), en `DirectPurchaseLine` y
  en `PurchaseOrderLine` — ésta ni siquiera rechazaba precios NEGATIVOS.
* La pantalla sólo ofrece las fuentes que se pueden asentar: en esta instalación,
  Transferencia bancaria y Mercado Pago.

### Pruebas que fijaban los defectos como contrato

`test_direct_purchase_ui.py` usaba un producto inexistente (`p1`), un almacén
inexistente (`wh-1`) y pagaba de caja chica sin contabilidad — y pasaba porque
no se comprobaba nada de eso. Ahora siembra un contexto real
(`tests/integration/procurement/_purchase_context.py`) y paga por transferencia.

### Verificación

Nuevos: `tests/ui/test_entity_search_keyboard.py` (8),
`test_requisition_dialog_capture.py` (9, los escenarios reproducidos),
`test_direct_purchase_ui.py` 5 → 13 (incluye que lo que se confirma SÍ deja su
asiento, con un bus local para no contaminar el global).

**Pendiente, deliberadamente**: la instalación no puede pagar de contado desde
caja chica hasta que Finanzas dé de alta una cuenta de tesorería de ese tipo;
`TREASURY_ACCOUNT` y `AUTHORIZED_CARD` siguen sin traducción (ambiguas, decisión
anterior del usuario) y por eso ya no se ofrecen.

Regresión amplia (2026-09-18): Compras 116 → 133, Finanzas, Proveedores,
Logística, Precios y Cárnico sin cambios; Productos (19+2) e Inventario (3+19)
con los mismos fallos previos por nombre. `tests/ui` destapó una regresión MÍA
DEL DÍA ANTERIOR: al conectar `supplier_search_reason` a la pantalla de compra
rápida, el doble de `test_purchasing_visual_closure.py` no lo tenía (ese día no
se corrió `tests/ui`). Al completarlo apareció que el doble tampoco tenía
`capabilities()`, que la pantalla ya pedía antes: ese caso fallaba de antes sin
llegar a medir el recorte. Completado el doble, 8/8. El fallo que queda en
`tests/ui` (asistente de instalación) es `No module named 'core'`, previo.

## Fase 4 — Factura de proveedor → conciliación → CxP (migración 266, 2026-09-18)

La sesión anterior dio la cadena a crédito por cerrada con UNA prueba que arma
los casos de uso a mano (sin servicio de tolerancias, sin el bus de la app).
Recorrida esta vez por la composición REAL sobre una copia de la base real,
estaba **muerta en producción**:

1. **La conciliación reventaba.** `ProcurementToleranceSettingsQueryService`
   exige `procurement.tolerance.{quantity,price,tax}.default` y lanza
   `LookupError` si faltan; nadie las sembraba. Ninguna factura podía conciliar
   ni generar CxP. → **Migración 266**: 0 % en las tres (decisión del usuario),
   `INSERT OR IGNORE` para no pisar valores del administrador.
2. **Toda factura con IVA salía como diferencia de impuesto.** La orden no
   guarda impuesto y la conciliación comparaba contra un `"0"` fijo; con
   `Tolerance`, esperado 0 exige real 0 exacto, así que ninguna tolerancia lo
   arreglaba. → Decisión del usuario: sólo se compara el impuesto que el
   documento DECLARÓ (`tax=None` = no declarado). Contra la orden no se compara;
   en compra rápida, que sí captura impuesto por línea, sí.
3. **Doble registro de la compra de contado.** Conciliar su factura creaba una
   CxP a un proveedor YA PAGADO y un segundo asiento (inventario cargado dos
   veces). → Se concilia pero no emite `ACCOUNT_PAYABLE_CREATE_REQUESTED`
   (§11: el contado termina en Tesorería). También en "liberar".
4. **La CxP nacía sin vencimiento.** → Decisión del usuario: fecha de factura +
   días de crédito de las condiciones comerciales del proveedor (0 si es de
   contado o no hay condiciones). `SupplierPaymentTermsPort` +
   `SupplierPaymentTermsAdapter` (lee la consulta de Proveedores, no la tabla);
   el traductor reenvía `payment_term_days` — su lista de campos es FIJA y lo
   perdía — y el puente de Finanzas calcula `due_date`.
5. **"Liberar diferencia" generaba deuda desde cualquier estado**, incluso sin
   recepción. → Decisión del usuario: sólo diferencias de precio, cantidad o
   impuesto y la factura sin documento de compra (`RELEASABLE_MATCH_RESULTS`).

Medido tras el cambio en la copia real: factura sin IVA → CxP 500 con
vencimiento; factura con IVA → concilia → CxP 580 y su asiento; compra de
contado + factura → concilia sin CxP ni segundo asiento.

**Verificación**: `test_invoice_to_payable_chain.py` (11) por la composición
real con bus LOCAL. Ninguna prueba previa cubría el IVA contra orden, la
restricción de liberación, el contado, el vencimiento ni la falta de
tolerancias. Compras 133 → 144; Finanzas, Proveedores, Logística y las de
pantalla sin cambios.

**Pendiente, no hecho** (§11 lo lista):
* **Notas de crédito**: no existen en ninguna capa.
* **Descuentos en factura**: la línea de factura no tiene campo de descuento.
* **Tolerancias por proveedor en su ficha**: `supplier_commercial_terms` guarda
  `quantity_tolerance`/`price_tolerance`, pero la conciliación las lee de
  `configuraciones` (`procurement.tolerance.<tipo>.supplier.<id>`): las de la
  ficha se ignoran. Mismo patrón de "capturado y no leído".
* La captura de factura acepta una orden en BORRADOR (la conciliación luego
  la frena con MISSING_RECEIPT, así que no genera deuda).

## Fase 5 — Productos → Precios: lo que se cobra (migración 267, 2026-09-18)

Medido sobre una copia de la base real con la sesión y la composición reales:

1. **La vigencia no existía para el motor.** `get_price` no mira fechas, así
   que un precio programado se cobraba desde que se capturaba y uno vencido se
   seguía cobrando. → `PricingRepository.effective_price(..., on_date)` (la fila
   de sucursal vigente, si no la de todas las sucursales vigente); el motor la
   usa para las listas base, de canal y de cliente. `get_price` se queda para
   quien EDITA precios (busca la fila guardada, no la vigente).
2. **El canal no existía para el motor.** Tomaba "la" lista de canal activa,
   cualquiera, en todas las ventas: la lista de WhatsApp a 120 se cobraba en el
   mostrador. → `active_channel_list(channel)`; el POS pide `POS` y Delivery
   el canal del pedido. Además el canal era texto libre en el diálogo: ahora
   se elige de `SALE_CHANNELS` (dominio de Precios; una prueba verifica que
   cada código exista en `OrderChannel`), se normaliza, y una lista de CANAL
   sin canal válido no se crea ni se ACTIVA (sí se lee: la base real tiene una).
3. **Delivery cobraba el precio de vitrina.** Sin cliente, sin cantidad, sin
   canal: ni listas de cliente ni volumen. → `price_for()` en el catálogo de
   captura, con las mismas entradas que el mostrador. Y el pedido guarda al
   cliente (decisión del usuario: opcional): `CaptureOrderUseCase(customer_id=)`
   y un buscador en "Nuevo pedido" con la MISMA búsqueda del mostrador
   (`CustomerLookupQueryService`, permiso `CLIENTES.buscar` de la sesión).
4. **El mínimo sólo existía en Precios.** Un descuento dejaba Pollo (mín. 95)
   en 90 sin pedir nada. → Decisión del usuario: bajo el mínimo pide la
   autorización en caliente de un descuento grande, exige motivo y queda en el
   evento `SALE_DISCOUNT_APPLIED` (outbox) con las líneas afectadas.
   `MinimumPricePolicy` (dominio de Ventas) calcula el precio efectivo con el
   descuento de línea y la parte proporcional del de la venta; sólo cuenta una
   línea que un DESCUENTO bajó (un precio de cliente ya bajo el mínimo es
   decisión de Precios y no bloquea descontar otra línea).
5. **La autorización en caliente era imposible en el mostrador.** El verificador
   de sesión sólo responde por el cajero y el autorizador debe ser OTRO: todo
   descuento que la necesitara se negaba siempre. Mismo defecto que Precios
   cerró el 2026-09-17 con `PricingAuthorizerPermissionChecker`; se movió a
   `backend/application/security/authorizer_permission_checker.py`
   (`AuthorizerPermissionChecker`, estándar único) y Ventas lo usa.
6. **El autorizador no se probaba con clave.** El POS pedía su UUID tecleado;
   Caja captura la clave y la DESCARTA. → `VerifyAuthorizerCredentialsUseCase`
   (mismas reglas y bloqueo por intentos que el login, sin abrir sesión); el
   diálogo de descuento pide usuario y clave y muestra por qué se rechaza.
7. **El descuento no tenía entrada en el mostrador.** Permiso, caso de uso y
   diálogo existían; ningún botón ni atajo lo abría. → botón "% Descuento"
   (sigue a `discount_apply`) y F5.
8. **Migración 267 — "Nuevo pedido" reventaba en producción.** La base real
   tiene la 226 aplicada con el esquema de entonces; `create_orders_delivery_schema`
   creció después y `CREATE TABLE IF NOT EXISTS` no agrega columnas: faltaban
   `customer_orders.pickup_verification_code`, `customer_order_lines.package_id`
   y 10 tablas (paquetes, trabajos de entrega, rutas, liquidaciones). Crear
   CUALQUIER pedido fallaba. Se midieron todas las `create_*_schema` contra la
   base real: sólo Delivery tenía deriva. 267 agrega las columnas y vuelve a
   correr el esquema. Sólo registrada.

Medido tras el cambio en la copia real (jose.rodriguez cobra, admin autoriza):
mostrador 100 (el 90 es de dentro de 30 días), pedido POS 100, pedido WhatsApp
120; descuento a 90 sin autorización → `BELOW_MINIMUM`; con admin y motivo →
aplicado y auditado; la búsqueda de clientes de "Nuevo pedido" encuentra al
cliente real.

**Verificación**: `test_pricing_channels_validity_minimum.py` (20),
`test_verify_authorizer_credentials.py` (8), `test_schema_drift_267.py` (4),
`test_pos_discount_and_price_list_ui.py` (9), `test_new_order_page.py` 11 → 15.
Precios, Pedidos/Delivery y seguridad sin regresiones; la prueba de atajos del
POS se actualizó (F5). Fallos previos, sin relación: módulos `core`/`config`
borrados, `test_action_buttons_use_the_same_variants...` (el botón "success"
ahora es variante `secondary`), y `inventory_balances` en las pruebas
unitarias de suspender/cobrar (la reconstrucción de Fase 7 consulta inventario
y esas pruebas no crean su esquema).

**Pendiente, no hecho**:
* **Caja descarta la clave del autorizador** (`HotAuthorizationDialog` de
  `cash_register`) y Compras autoriza sin identificar a nadie: deben usar
  `VerifyAuthorizerCredentialsUseCase`.
* **Precios no captura al autorizador** del precio bajo el mínimo en su UI: el
  caso de uso lo soporta, la pantalla no lo pide.
* El descuento de LÍNEA no tiene pantalla (sólo el de la venta).
* El mínimo que devuelve el motor es siempre el de la lista BASE; una lista de
  cliente o de canal no puede fijar su propio mínimo.

## Fase 6 — Ventas: Productos → Precios → Inventario → Finanzas (migración 268, 2026-09-18)

La sesión del 2026-09-14/15 cerró esta fase "sin cambios" verificando código.
Medida esta vez con una venta REAL (copia de la base, sesión de
jose.rodriguez, 10 Pollos comprados a $50 por la compra rápida, venta de 2 a
$100 en efectivo), la venta quedaba COMPLETED por $200 y:

1. **El inventario no se movía** (seguía en 10). Dos causas apiladas:
   - el cobro sólo confirmaba una reserva si la venta ya la traía, y sólo
     SUSPENDER la creaba;
   - aunque reservara, Ventas buscaba la existencia con la sucursal como
     almacén (`warehouse_id = branch_id`, parche documentado en
     `provision_default_warehouse.py` "hasta que las sucursales tengan
     almacenes"). Ya los tienen, y Compras recibe en ellos (Cadenas).
   → El cobro reserva y descuenta en su transacción. `SalesInventoryClient`
   vende del almacén ACTIVO de la sucursal con `allow_sales_allocation`
   (`WarehouseDirectoryQueryService.sales_warehouses_for_branch`). Si hay
   varios, da un error claro; si no hay ninguno, usa la sucursal como
   almacén, como antes. La salida lleva `unit_cost`.
2. **Sin existencia** → decisión del usuario: autorización en caliente.
   - Permiso nuevo `POS.venta.sin_existencia`; otro usuario lo valida
     (`AuthorizerPermissionChecker`) y debe dar motivo.
   - La salida queda negativa (`negative_allowed` + `authorized` de
     `NegativeInventoryPolicy`) y auditada en `SALE_COMPLETED`.
   - `InventoryShortageError` (subclase de `InventoryReservationFailedError`)
     separa la falta de existencia de otros fallos (permiso, reglas de lote),
     que no admiten esta autorización.
   - Si el descuento falla después de reservar, la reserva se libera.
3. **Caja**: sin turno, la venta se completaba igual y el efectivo quedaba
   fuera de todo corte (el efecto de caja corre después del commit).
   → Decisión del usuario: exigir turno ANTES de completar (`NO_OPEN_CASH_SHIFT`).
   La pantalla avisa antes de abrir el cobro. El diálogo de pago ya no repite
   `begin_checkout` ni duplica pagos al reintentar.
4. **Finanzas no se enteraba.** `SaleCompletedHandler` estaba completo y sin
   registrar; `sales_outbox` no tenía despachador; y el contrato estaba
   desalineado (el trinquete `test_erp_chain_wiring_ratchet` lo había
   anticipado).
   → `SALE_COMPLETED` lleva totales, pagos, cambio y costo de venta.
   `backend/application/sales/integrations/finance_translator.py` lo traduce:
   efectivo neto del cambio y liquidación por método. `wire_sales` se registra
   en `wire_cross_context_events`, y el POS despacha después del commit en
   modo estricto: si Finanzas falla, el evento queda PENDIENTE.
   `SALE_COMPLETED` sin consumidor no se marca despachado. El manejador no
   duplica la CxC que `SalesCreditClient` ya registra al cobrar a crédito;
   sólo agrega el asiento.
5. **Migración 268 — nadie más que admin/system_owner podía vender.** Ana
   (cajero) y demo (gerente) no tenían ni `POS.venta.linea_agregar`; los
   permisos finos del POS eran otorgables y nunca otorgados (mismo patrón que
   la 260). Decisión del usuario, "cajero vende, gerente autoriza":
   - cajero: vender, cobrar de contado, descuento chico, reimprimir, báscula y
     reservar/liberar inventario;
   - gerente, admin y system_owner: todo el vocabulario.

   Registrada, no aplicada.

Medido tras el cambio, en la copia real con 267 y 268 aplicadas:

| Caso | Resultado |
| --- | --- |
| Sin turno | `NO_OPEN_CASH_SHIFT`; la venta queda pendiente |
| Con turno | Se completa; inventario de 10 a 8; `SALE_ISSUE` a $50; asientos Venta 200/200 y Costo 100/100; `CASH_SALE` 200 |
| 20 con 8 en existencia | `STOCK_AUTHORIZATION_REQUIRED`; con admin y motivo, saldo −12 y auditado |
| Ana y demo | Ya pueden vender; sólo demo autoriza |

**Verificación**:
- `test_sales_checkout_settles_everything.py` (19) y
  `test_pos_checkout_dialogs.py` (6).
- `tests/integration/_pos_ready.py`: turno de caja y existencia para las
  pruebas que usan la composición real.
- Las pruebas que sólo PREPARAN una venta completada (facturas, tickets,
  devoluciones, rifas, reimpresión) construyen el cobro con
  `settle_inventory=False, require_cash_shift=False`: su comportamiento
  anterior, y no es su tema.
- `test_cash_effects_error_is_captured_without_blocking_completion` fijaba el
  contrato viejo; se reescribió con el nuevo.
- Delivery 245, Precios 110, Compras 144 y Finanzas 122 en verde.
- Fallos previos sin cambio: tablas legado en `test_sales_checkout`, y
  `inventory_balances` en fixtures de suspender/listar.

**Pendiente, no hecho**:
* **Devoluciones y reversos no llegan a Finanzas**: `SaleReversedHandler` sigue
  sin consumidor, así que el reverso no revierte ingreso ni costo. Es el
  siguiente hueco de la regla 11.
* **El canje de puntos se asienta como descuento**, no contra el pasivo de
  puntos: la venta no identifica el instrumento canjeado.
* **Las ventas no tienen folio** (`sale_number` nunca se asigna); el asiento usa
  el final del UUID.
* **`SaleCompletedCashHandler` NO debe cablearse**: el cobro ya registra Caja
  en directo y se duplicaría.
* **Productos compuestos (`SALES_EXPLOSION`)** siguen sin explotar al vender
  (hallazgo de 2026-09-15).
* **Con varios almacenes de venta por sucursal** no hay selector: error claro.
* **En la base real**: el turno de jose en Corregidora está en CLOSING y hay 0
  existencias. Hasta cargar inventario, toda venta pedirá autorización.

## Fase 7 — Reconstrucción inversa: ATP y consumo inverso (migración 269, 2026-09-19)

La Fase 7 original (2026-09-14/15) construyó el backend: explosión inversa,
ATP y el caso de uso que arma el producto con sus partes. Medido esta vez con
tu base y las pantallas reales, era inalcanzable:

1. **Fuente equivocada.** Leía sólo recetas de tipo Desensamble. El despiece
   que Productos captura y Cárnico EJECUTA es el **esquema de corte**: el mismo
   despiece había que definirlo dos veces, y el que de verdad se usa no se
   podía revertir.
   → Decisión del usuario: el esquema de corte es la fuente única.
   - `cutting_schemes.reverse_reconstruction_allowed` (migración **269**, por
     omisión 0).
   - `CuttingSchemeRepository.reversible_active_version_for_input`: exactamente
     un esquema activo, reversible y con versión ACTIVA; ninguno o varios →
     no se arma, nunca se adivina.
   - Se retiró la vía por recetas: el campo en `Recipe`,
     `SetReverseReconstructionAllowedUseCase` con su comando, y
     `RecipeRepository.reversible_active_version_for_product`.
     `recipes.reverse_reconstruction_allowed` (258) queda **inactiva**; no se
     borra porque ya existe en bases reales.
2. **La marca no se podía fijar** desde ninguna pantalla.
   → `SetCuttingReverseReconstructionUseCase` (permiso de despiece, auditado).
   En Productos → Despiece: columna "Armar con partes" y botón para
   permitirlo o quitarlo.
3. **El ATP no lo usaba nadie**, y un producto agotado **ni se podía
   seleccionar** en la cuadrícula del POS. Eso dejaba inalcanzable también la
   venta sin existencia con autorización de la Fase 6.
   → El catálogo del POS suma lo armable (`reconstructible_quantity`, con el
   aviso "N se arman con partes en existencia"). `ProductAvailabilityPolicy`
   ya no bloquea lo agotado: lo avisa ("requiere autorización al cobrar") y
   el cobro exige la autorización.
4. **El armado era un AJUSTE** (`ADJUSTMENT_IN/OUT`): cada pollo armado salía
   en los reportes de ajustes/merma.
   → `PRODUCTION_CONSUMPTION` / `PRODUCTION_OUTPUT`.
5. **Su costo no llegaba al costo promedio**, y el cobro de la Fase 6
   costeaba ANTES de armar: un producto que sólo se arma se vendía sin costo.
   → La reconstrucción alimenta `ProductCostProjectionHandler`, con el mismo
   contrato que usa Producción, idempotente. El cobro costea DESPUÉS de
   reservar.
6. **El cajero no podía armar**: le pedía `INVENTARIO.movimiento.crear_manual`.
   → El armado se somete a `INVENTARIO.reserva.crear`, el mismo permiso con
   que el cobro reserva (la 268 lo da a cajero y gerente). La política de
   autorización del caso de uso pasa a ser obligatoria; la guarda
   `test_inventory_authorization_fail_closed` lo marcaba.

**Medido en la copia real**:
- Despiece de Pollo Entero por kg (0.35 pechuga, 0.30 pierna, 0.12 ala)
  creado, aprobado, activado y marcado desde Productos.
- Compradas 3.5 / 3 / 1.2 kg de partes → ATP de **10 kg armables**. El
  catálogo muestra "Pollo Entero — disponible 10 — 10 se arman con partes".
- Venta de 4 kg con 0 kg directos: se completa sin suspender. Las partes bajan
  1.4 / 1.2 / 0.48 kg, con movimientos `PRODUCTION_*` de origen
  `RECONSTRUCTION`.
- Costo promedio del pollo $55.50/kg y costo de venta **$222** asentado.

**Otro defecto encontrado**: `attach_virtual_keyboard_action` (teclado virtual
compartido) reventaba de forma intermitente con "wrapped C/C++ object ... has
been deleted" al construir diálogos. Sip reutilizaba el envoltorio viejo de un
campo destruido. Se detecta con `sip.isdeleted` y se reemplaza. Explica la
intermitencia en Delivery (día 18) y en Descuento (día 19);
`test_virtual_keyboard_stale_controller.py` la reproduce sin el arreglo.

**Verificación**:
- `test_reverse_reconstruction_from_cutting_scheme.py` (8).
- Las 3 suites de la Fase 7 reescritas sobre esquemas de corte (15; ahora
  incluyen "una receta de Desensamble ya no reconstruye", "dos despieces
  reversibles son ambiguos" y "una versión inactiva no cuenta").
- `tests/integration/_reversible_cutting.py`: ayudante compartido.
- Resultados: Cárnico 364, Productos 507+19+2 y Inventario 590+3+19 (fallos
  previos idénticos), Delivery 245, Precios 110, Compras 144, Finanzas 122.
  El lote de Ventas/POS, 209, pasó cinco veces seguidas tras el arreglo del
  teclado.

**Pendiente, no hecho**:
* **Delivery no consulta el ATP** ni arma al capturar pedidos: es la Fase 8.
* El ATP de productos por peso se redondea a unidades enteras hacia abajo.
  Es una estimación conservadora de vitrina; el cobro arma el faltante
  exacto.
* El costo promedio usa un `tracked_quantity` que las ventas no descuentan
  (limitación previa del costeo).
* Las salidas `BY_PRODUCT` del despiece (p. ej. huacal) sí se exigen para
  armar; sólo se excluyen merma y pérdida.

---

## Fase 10 — Recetas → producción → rendimientos → merma → costos (2026-09-19/21)

**§10/§13/§14/§30 del prompt maestro.** Qué pasaba, medido con la sesión real
sobre copia de `data/spj_pos_database.db`:

* De ~50 casos de uso de Cárnico, la pantalla conectaba **4** (crear, aprobar,
  liberar, cerrar). No había forma de consumir la entrada, pesar las salidas ni
  conciliar; los puertos a Inventario, Costos y Mermas eran **nulos**, así que
  ninguna orden podía cerrarse jamás (`consumptions_posted`,
  `inventory_confirmed` y `costs_notified` nunca se ponían en verdadero).
* Y ni siquiera podía **crearse** una orden: el presenter exigía almacén de la
  sesión, y `LegacySessionAdapter.active_warehouse_id` es `""`.

**Decisiones del usuario** (2026-09-19):
1. **Casillas en Almacenes**: cada almacén declara para qué sirve
   (Venta/Compra/Producción/Cuarentena). Cárnico produce en el ACTIVO marcado
   «Producción»; si no hay, lo dice y manda a marcarlo. Mismo estándar de
   Ventas — un solo `WarehouseDirectoryQueryService.resolve_for_purpose`.
2. **Costo por valor de venta relativo**: cada corte bueno absorbe costo en
   proporción a `kg × precio de venta`. La merma no absorbe: su costo lo cargan
   los cortes buenos, que es lo que encarece el $/kg cuando baja el rendimiento.
3. **Autorización en caliente** (mismo estándar que mostrador y Precios): sin
   existencia de la entrada → otro usuario con `PRODUCCION.consumo.sobrescribir`;
   corte fuera de tolerancia → otro con `PRODUCCION.rendimiento.sobrescribir`.
   Siempre con usuario, clave y motivo, y nunca uno mismo.
4. **Esquema de corte + tolerancia global**: lo esperado sale del despiece
   capturado al liberar; la tolerancia (aviso/tolerancia/crítico %) es una sola,
   configurable en Cárnico → Configuración.
5. **Permisos**: "almacén produce, gerente aprueba".

**Construido**:
- `domain/meat_processing/services/cost_allocation_service.py`:
  `RelativeSalesValueCostAllocation`. La última salida buena absorbe el
  redondeo, así que lo repartido cuadra EXACTO con el costo de la entrada; una
  salida buena sin precio es error explícito, nunca un cero silencioso (§18).
- `application/meat_processing/use_cases/order_execution_use_cases.py`:
  `ProcessingOrderExecutionQueryService` (el plan que captura la pantalla) y
  `ExecuteProcessingOrderUseCase`, que **orquesta los casos de uso existentes**
  en el orden del §14 — iniciar → consumir → registrar salidas → calidad →
  recibir con lote y costo → resultado por corte → completar → conciliar (caso
  de merma si sale de tolerancia) → cerrar. Todo se valida **antes de mutar** y
  es **reanudable**: cada paso mira lo ya hecho en vez de duplicarlo.
- `infrastructure/integrations/meat_processing_ports.py`: los cuatro puertos que
  estaban nulos (consumo, recepción con lote y genealogía, costo proyectado,
  caso de merma por variación).
- `application/meat_processing/yield_settings.py` + página de Configuración.
- `infrastructure/db/repositories/meat_processing/output_results_repository.py`
  y el registro «Rendimientos → Por corte» (§13); la conciliación que ya existía
  es por ORDEN.
- UI: botón «Ejecutar» con reintento tras autorizar, diálogos de captura,
  autorización y resultado; casillas de uso en el alta/edición de Almacenes y
  columna «Usos» en la lista.

**Migraciones**: **270** (tabla `processing_output_results` + tolerancias
2/5/10 % en `configuraciones`, `INSERT OR IGNORE`) y **271** (siembra de los
permisos `PRODUCCION.*` por rol — mismo hueco que la 260 y la 268: eran
otorgables y nadie los tenía, sólo admin operaba por comodín de rol).

**Dos huecos más, encontrados al reproducir de punta a punta**:
1. **Corregidora tiene UN solo usuario.** Como quien crea una orden no la
   aprueba, hoy ninguna orden de esa sucursal podría aprobarse. La palanca es
   `usuarios_sucursales`, igual que en Transferencias: es dato, no código.
2. Al asignar a otro usuario esa sucursal seguía sin poder aprobar:
   **`assigned_branch_ids` se escribía desde el 2026-09-17 y NADIE lo leía**.
   Los composition roots de Cárnico y Mermas armaban `frozenset({branch})`, de
   modo que el nivel «sucursales asignadas» del alcance era hueco para todos.
   Cerrado con un único lector, `application/security/session_branch_scope.py`,
   usado por los dos; y los almacenes de alcance de Cárnico pasan a ser los de
   producción de TODAS las sucursales de alcance, no sólo la activa.

**Medido en la copia real** (jose crea, admin aprueba, 10 kg de pollo a $50):
orden **CLOSED**; pollo 10 → 0; pechuga 3.4, pierna 3.0, ala 1.2 en existencia
con **3 lotes** `OP-…`; merma no entra a existencia; ledger con
`PRODUCTION_CONSUMPTION` ×1 y `PRODUCTION_OUTPUT` ×3; costo $500 repartido
283.33 / 166.67 / 50.00 ($/kg 83.33 / 55.56 / 41.67) y variación de pechuga
−2.86 %, dentro de tolerancia.

**Verificación**: `test_cost_allocation_service.py` (9),
`test_processing_order_execution.py` (26), `test_warehouse_purposes.py` (10),
`test_meat_processing_execution_settings_and_seed.py` (11),
`test_meat_processing_execution_ui.py` (15), `test_session_branch_scope.py` (7).
Trinquetes de rutas actualizados: `mp_settings` deja de ser placeholder
(pendientes 16 → 15) y `mp_yields` pasa a ser la página de dos pestañas. La
suite genérica de registros (98) exige que TODO registro tenga sembrador, así
que «Por corte» trajo el suyo — ese trinquete hizo su trabajo.

**Pendiente, no hecho**:
* La tolerancia es global; no hay tolerancia por corte ni por especie.
* El caso de merma por variación NO postea inventario
  (`requires_inventory_posting=0`) a propósito: la merma ya está reflejada al no
  recibirla en existencia. Mermas la clasifica y valúa.
* Empaque y etiquetado siguen fuera del orquestador (pasos aparte).
* Reproceso (`REWORK`) no se dispara automáticamente desde una variación.

## Procesamiento — auditoría profunda: definición congelada, reservas reales, Calidad y Costos (migraciones 272 y 273, 2026-09-24)

Hallazgos corregidos (todos medidos antes de tocar):

| Hallazgo | Corrección |
|---|---|
| La ejecución releía el esquema de corte de Productos | `ProcessingRecipeSnapshot` se congela al PREPARAR (`processing_recipe_snapshots`, sólo INSERT); la ejecución lee sólo la foto |
| Liberar capturaba sólo ids y liberaba sin datos maestros; se liberaba desde APPROVED | `ProcessingMasterDataRequirementPolicy` por familia (despiece → esquema de corte, formulación → receta, empaque → especificación de empaque); `release()` exige READY |
| Reservas de papel (sin llamadores) y READY sin reserva | `PrepareProcessingOrderUseCase` reserva en Inventario (`ReserveStockForProductionUseCase`: lote y ubicación exactos, todo o nada); `material_requirement_allocations` guarda la reserva real; sin reserva no hay READY |
| Existencia negativa autorizable | Retirado: no hay consumo sin reserva (`EXCEEDS_RESERVATION`) |
| La ejecución liberaba calidad de sus propios outputs | Calidad propia (`quality_inspections`, segregación de funciones); Inventario retiene (QUARANTINED) y sólo Calidad libera; `RecordQualityDecisionUseCase` sólo registra una decisión que EXISTA en Calidad |
| Costo por valor de venta relativo calculado en Procesamiento | Contexto de Costos (`JointCostAllocator`: peso, valor de venta, valor neto realizable, estándar, factor); preflight antes de mover existencia; `PRODUCTION_OUTPUT_COSTED` → Precios, `PROCESSING_COST_ALLOCATED` → Finanzas (antes sin emisor) |
| `operation_id` armados por concatenación | UUIDv7 por paso, persistidos en `processing_execution_steps` antes de llamar a otro contexto (reanudable, idempotente) |
| `location_id or branch_id` | `StockLocationResolver`; sin ubicación, falla claro |
| `permissive_for_tests` por omisión en adaptadores | Concesiones declaradas por el contexto dueño (`IntegrationGrant`, mismo usuario, permisos cerrados) |
| Mermas escritas por repositorio y con diferencia 0 | Caso de uso de Mermas; la merma es `YieldReconciliation.yield_loss_weight` |
| Rendimiento con un solo producto sin precio no se podía costear | Con una sola salida que carga costo, se lleva el 100 % con cualquier método |
| Trazabilidad con un solo lote padre y UUIDs en pantalla | Padres desde los consumos aplicados (muchos a muchos); lotes por código, órdenes por fecha, sucursales por nombre |
| Nadie podía decidir calidad desde la aplicación | Calidad → «Por inspeccionar» (inspector con `CALIDAD.inspeccion.decidir`) |

Migraciones:
- **272**: esquemas de foto y de bitácora; `process_outputs` admite `NOT_REQUIRED` (reconstrucción sin perder filas); fotos reconstruidas desde las versiones capturadas; órdenes RELEASED sin reserva ni consumo vuelven a MATERIALS_PENDING.
- **273**: esquemas de Costos y Calidad; el costo histórico que la Fase 10 dejó en `processing_output_results` pasa a `processing_cost_allocations` (sin eventos) y la tabla se reconstruye sin columnas de costo; permisos `CALIDAD.inspeccion.*` a gerente/admin/system_owner y `PRODUCCION.material.asignar` a almacén (INSERT OR IGNORE).

Decisiones del usuario (2026-09-24) y lo hecho con ellas:
- **Compuestos en Ventas**: se venden por sus COMPONENTES. `SalesFulfillmentQueryService` (Productos) resuelve receta «Explosión de venta» o combo VIRTUAL (un `STOCKED_KIT` se vende de su stock), anidados, y falla claro ante ciclos o definición doble. Ventas reserva, descuenta y, al devolver, repone componentes; el costo de venta es la suma de los componentes; Inventario promete lo que alcanza el componente más escaso.
- **Ventas ↔ Producción**: Ventas SÓLO consulta a Inventario; no hay eventos ni consultas de producción (fuera de alcance por decisión).
- **Folio**: `OP-<código de sucursal>-00001`. El código es el de Configuración → Empresa y sucursales (`branch_profiles.code`, ahora editable); contador seguro `document_number_sequences` por prefijo, reservado en la misma transacción que la orden. **Migración 275**: perfil mínimo con código derivado del nombre (único) para sucursales sin perfil, columna `folio` con índice único, folios de órdenes existentes en orden de creación y contador alineado. Nota: al tener perfil, borrar físicamente una sucursal exige borrar antes su perfil (llave foránea); dar de baja sigue siendo desactivar.
- **Limpieza**: borrados `_execution_fixture.py` y seis pruebas de la cadena legacy (sus reglas de negocio pasaron a `tests/integration/sales/test_sales_composite_explosion.py`); **migración 274** retira `PRODUCCION.calidad.registrar_decision` de todos los roles.

## Procesamiento — búsqueda estándar en «Nueva orden» y Plan de producción (migración 276, 2026-09-25)

1. **«Nueva orden» no usaba el estándar de búsqueda de productos**: usaba un
   `EntitySearchInput` alimentado por `ProductQueryService.search_products`
   (preset de Inventario, sin sucursal, sin explicar vacíos). Ahora usa
   `ProductSearchBox` + `ProductSearchQuery` en la sucursal activa, con
   `explain_empty`, y el preset depende del proceso: formulación busca lo que se
   FABRICA (producibles); despiece/empaque/acondicionado buscan la ENTRADA
   (`SearchProductionInputsQueryService`).
2. **Plan de producción habilitado** (antes placeholder: el dominio existía sin
   persistencia ni casos de uso). Decisiones del usuario: un plan por sucursal y
   DÍA; líneas manuales, desde la reposición de Inventario (sugerencias abiertas,
   la más reciente por producto, sólo producibles) y desde el pronóstico de BI
   (`ProductionPlanningService` real, compuesto con el lector de ventas
   unificadas y los repositorios de pronóstico; sin historia no sugiere);
   convertir una línea crea la orden APROBADA por quien aprobó el plan (con
   folio), y quien aprobó el plan no convierte (segregación). La línea guarda el
   proceso y el producto objetivo (la entrada en despiece). **Migración 276**:
   `production_plans` (único por sucursal y día) y `production_plan_lines`.

## Compras — compra rápida visible y unidades de compra desde Productos (FASE 2-3, 2026-09-25, sin migración)

1. **"No pasa nada" al guardar la compra rápida**: medido sobre la base real, el
   borrador SÍ se guardaba (CD-2026-000001), pero el único aviso era una línea de
   texto pequeña, la captura seguía editable, y tras confirmar la tabla nunca se
   repintaba (la compra seguía a la vista). Ahora: aviso destacado del Design
   System (`QLabel[role="banner"]`, estados error/éxito, en `qss_builder`), folio
   en el resumen («Documento»), captura bloqueada tras guardar («Nueva compra»
   desbloquea con operación nueva), tabla vacía y folio confirmado tras
   confirmar. Modalidad y Condición abren con valor real (antes placeholder que
   guardaba "Pago inmediato" sin mostrarlo).
2. **Búsqueda de productos**: `explain_empty` relajaba primero el TEXTO; con un
   solo producto habilitado en la sucursal, buscar otro existente decía "ninguno
   coincide". Ahora relaja primero sucursal/estado conservando el texto
   (SIN_HABILITAR_EN_SUCURSAL / SIN_ACTIVOS). La compra rápida busca, explica y
   costea con la sucursal del DOCUMENTO (antes la de la sesión) y pasa
   `empty_reason_provider` al diálogo (antes nunca explicaba). La fila de estado
   de `EntitySearchInput` ajusta línea (antes quedaba cortada).
3. **FASE 3 — unidades desde Productos**: `PurchaseProductConfigDTO` (contrato
   existente de Productos §31) ahora trae unidad base, presentaciones
   (`product_unit_conversions` hacia/desde la base, específica del producto gana
   a la global, vigencia respetada) y base de precio; tolera esquemas reducidos y
   conexiones sin `sqlite3.Row`. Compras lo lee por
   `ProcurementProductCatalogAdapter.purchase_profile` (`PurchaseProductProfile`).
   `CreateDirectPurchaseUseCase` DERIVA unidad de inventario y factor del maestro
   (ignora lo que mande la pantalla) y rechaza una presentación no configurada
   (`UNIT_NOT_CONFIGURED`). El diálogo «Agregar producto» perdió "Producto por
   peso" y "Factor de conversión": se ELIGE la unidad de compra, se ve la
   equivalencia y los kilos que entran; precisión 3 para peso. Captura en
   Productos → Catálogo → «Unidades de compra» (alta y retiro; nuevo
   `SetUnitConversionActiveUseCase`, nunca se borra).
4. **Costo al inventario**: `DIRECT_PURCHASE_RECEIVED` mandaba cantidad en unidad
   de inventario con costo de la unidad de compra (2 cajas de 20 kg a $400 → 40 kg
   a $400/kg). Ahora costo por unidad de inventario.
5. **Permisos**: `PRODUCTOS.unidad.gestionar` y `PRODUCTOS.conversion.gestionar`
   no estaban en el puente de permisos y caían a `PRODUCTOS.ver`; ahora exigen
   edición.
6. Borrado `frontend/desktop/modules/purchasing/pages/direct_purchase_page.py`
   (código muerto, sin referencias).

Pendiente: `OrderFormDialog` (Órdenes) aún captura el factor a mano — entra en
FASE 5 (PR→OC).

### Compras con catálogo GLOBAL (decisión del usuario, 2026-09-25)

Las compras NO se filtran por habilitación de sucursal: `ProcurementProductCatalogAdapter.search`
busca en todo el catálogo comprable y usa la sucursal del formulario sólo para
MARCAR (`enabled_in_branch`, vía `_BaseProductSearch.enabled_in_branch` de
Productos). El resultado dice «CÓDIGO · deshabilitado para esta sucursal» y el
tooltip de la fila «Habilítalo en Productos → Sucursales y surtidos.»
(`SearchOption.tooltip`, pintado por `EntitySearchInput`). El producto sigue
siendo seleccionable y comprable. La explicación de vacío de Compras ya no
menciona habilitación. Ventas/Inventario siguen filtrando por sucursal.

## Compras FASE 5 — solicitud → orden de compra (migración 277, 2026-09-25)

1. **No se podía crear ninguna orden en producción**: «Nueva orden» y «Crear
   orden» (desde solicitud) exigían `default_warehouse()` antes de abrir el
   diálogo y `LegacySessionAdapter.active_warehouse_id` es siempre `""`. Ahora
   sucursal y almacén se eligen en el formulario (el almacén se recarga al
   cambiar de sucursal y se preselecciona si es único). `open_order_form` es la
   única entrada.
2. **El diálogo crea la orden y sólo se cierra si se creó**: antes un rechazo
   del backend llegaba DESPUÉS de cerrar y se perdía la captura. Error como banner
   arriba del diálogo. `operation_id` estable por captura (doble clic = una orden).
3. **Sin precio 0**: las líneas que vienen de una solicitud sin costo estimado
   quedan «Falta precio» (nunca se siembra 0) y el diálogo no acepta hasta
   capturarlo («Capturar precio»). También «Quitar línea».
4. **Reglas del maestro en la orden** (`product_master_rules.py`, compartido con
   la compra rápida): almacén de la sucursal, producto activo y comprable, unidad
   de compra configurada en Productos; el factor lo deriva el maestro (el campo
   «Conversión» tecleado desapareció). Validación ANTES de reservar el folio: una
   línea inválida ya no deja hueco en la secuencia OC.
5. **Migración 277**: `purchase_order_lines.purchase_unit` / `inventory_unit`.
6. **Recepción de OC → inventario**: mandaba la cantidad en unidad de compra y sin
   costo; ahora cantidad aceptada × factor y costo por unidad de inventario.
7. **Nombres, nunca ids**: `product_name` en las líneas de solicitud, orden,
   factura y comparación de cotizaciones (`queries/product_names.py`); paneles de
   detalle, recepción y adjudicación muestran el nombre.
8. Diálogos con líneas usan `DialogMetrics.WIDTH_LG`; el buscador de producto va
   en su propio renglón.

Pendiente (FASE 6): una solicitud sigue admitiendo UNA sola orden (la primera la
marca SOURCED) y la adjudicación no genera órdenes.

## Compras FASE 6 — adjudicación → órdenes de compra (migración 278, 2026-09-25)

1. **La adjudicación era un callejón sin salida**: sólo escribía
   `purchase_awards`/`purchase_award_lines`. Nuevo
   `GeneratePurchaseOrdersFromAwardUseCase` (`award_order_use_cases.py`): agrupa
   las líneas adjudicadas por proveedor y crea UNA orden por proveedor con el
   precio COTIZADO y la cantidad ADJUDICADA, mediante el mismo
   `CreatePurchaseOrderUseCase` (mismas reglas del maestro de FASE 5). Las
   órdenes llevan `source_requisition_id`, `source_rfq_id` y `source_award_id`.
2. **Idempotencia por (adjudicación, proveedor)**: el caso de uso devuelve la
   orden existente y la **migración 278** agrega el índice único parcial
   `purchase_orders(source_award_id, supplier_id)`. Reintentar tras un fallo
   genera sólo las que falten.
3. **Varias órdenes por solicitud**: la primera orden marcaba la solicitud
   SOURCED y bloqueaba la segunda. Ahora se admite APROBADA o PARCIALMENTE
   ABASTECIDA, y el estado se calcula por COBERTURA (cantidad ordenada × factor
   de todas sus órdenes no rechazadas vs. lo pedido).
4. **La RFQ se cierra al adjudicar** (antes quedaba en «Borrador»).
5. Pantalla: botón «Generar órdenes» en el detalle de Cotizaciones (activo
   mientras falte alguna), y se ofrece automáticamente justo después de
   adjudicar. El diálogo muestra proveedor, líneas, total y orden (o «Por
   generar»), pide el almacén (preseleccionado si es único) y sólo cierra si
   todo se generó. Estado de invitación y de RFQ en español.
6. **(cierre del pendiente, mismo día)** «Generar órdenes» es ATÓMICO:
   `CreatePurchaseOrderUseCase.create_in(uow, …)` crea dentro de una transacción
   ajena y el caso de uso de adjudicación genera las de todos los proveedores en
   UNA sola; si la de un proveedor falla se revierten todas (y no se queman folios).

## Compras FASE 7 — orden de compra completa y confirmación del proveedor (migración 279, 2026-09-25)

1. **Encabezado (§23)**: fecha requerida y prometida, condición de pago (Contado,
   Crédito 7/15/30/45/60), forma de entrega (Entrega del proveedor / Recolección en
   proveedor), moneda con tipo de cambio obligatorio si no es MXN, dirección de
   entrega, centro de costo, proyecto, contrato y notas («Más datos»). El detalle
   muestra comprador, sucursal y almacén por NOMBRE.
2. **Líneas**: descuento e IVA por línea (descuento ≤ importe), subtotal, cantidad en
   unidad de compra y de inventario. Total = Σ(cantidad × precio − descuento + IVA).
3. **Confirmación del proveedor (§24)**: `send_order(acknowledge=True)` marcaba la
   orden como confirmada SIN ningún dato; se eliminó. Nuevo
   `AcknowledgePurchaseOrderUseCase` (permiso `COMPRAS.orden.confirmar`, que existía
   sin usarse): referencia del proveedor, fecha de entrega confirmada, cantidad
   confirmada por línea, comentarios, quién y cuándo. Las EXCEPCIONES (confirma
   menos/más de lo pedido, entrega posterior a la requerida) se calculan, se guardan
   y viajan en `PURCHASE_ORDER_ACKNOWLEDGED`. Botón «Registrar confirmación» sólo en
   órdenes Enviadas; el detalle distingue «Enviada — sin confirmación del
   proveedor» de «Confirmada por el proveedor (ref. …)».
4. **Migración 279**: columnas de encabezado y confirmación en `purchase_orders`;
   `discount`, `tax`, `confirmed_quantity` en `purchase_order_lines`.
5. **Bitácora legible**: acciones en español, nombre del usuario (no su id), hora
   local; el historial ya no se queda pintado al cambiar de orden.

## Compras/Costeo FASE 13 — promedio móvil con existencia real (2026-09-28, sin migración)

1. **Bug crítico (§31)**: `ProductCostProjectionHandler` usaba `tracked_quantity`,
   que sólo SUMABA entradas y nunca restaba salidas. Caso obligatorio: 100 kg @ $40,
   salen 90, entran 10 @ $60 → daba $41.82; ahora $50.00.
2. La cantidad previa se le pregunta a Inventario
   (`backend/application/inventory/queries/costing_stock_query_service.py`):
   existencia total del producto (costo global → todas las sucursales/almacenes)
   menos lo que la MISMA operación ya asentó en `inventory_ledger` (su
   `operation_id` es único). Así el resultado es igual si Inventario procesa la
   entrada antes o después que Costeo (ambos escuchan el mismo evento). Existencia
   negativa cuenta como 0. Sin inventario canónico en la base, respaldo al contador
   anterior.
3. **Bug encontrado de paso**: dos líneas del MISMO producto en un evento — la
   idempotencia es por (producto, operación) y la segunda se tomaba por «ya
   aplicada» y se perdía (cantidad y costo). Ahora se consolidan (cantidad total,
   costo ponderado) antes de aplicar.
4. Verificado de punta a punta con el bus real sobre copia de la base: dos compras
   rápidas de Alas con una salida de 90 kg entre ellas → costo promedio $50.00.

Pendiente (FASE 12): política de costo GLOBAL/PER_BRANCH (§32); hoy el costo sigue
siendo global.

## Compras/Costeo FASE 12 — política de costo multi-sucursal (2026-09-29, sin migración)

1. **§32**: el costo era global "en silencio". Nueva política
   `configuraciones.costing.cost_policy` (`GLOBAL` por omisión / `PER_BRANCH`) en la
   tabla de ajustes EXISTENTE (no se creó una nueva), cambiada sólo con
   `SetCostPolicyUseCase` (permiso `PRECIOS.configuracion.gestionar`), auditada como
   `COST_POLICY_CHANGED` en `pricing_outbox`.
2. `ProductCostProjectionHandler` mantiene SIEMPRE las dos vistas: promedio de
   empresa (`branch_id=''`) y el de la sucursal del evento, cada uno con su propia
   existencia real (`CostingStockQueryService.on_hand_before(..., branch_id=)`).
   Cambiar de política rige de inmediato, sin recalcular.
3. `ProductCostingService` (`backend/application/pricing/cost_policy.py`) decide:
   promedio y último costo de compra de empresa y de sucursal, y cuál rige.
   `ProductCostQueryService` (→ `PricingReadFacade`, Ventas) y el costo de
   referencia de Compras (`ProductPurchaseCostReadService`, que tenía su propio
   SQL) pasan por la política. Sin dato en la vista que manda, se usa la otra
   (nunca "sin costo" habiendo uno).
4. **§30**: un cambio de costo nunca toca el precio de venta (prueba fija).
5. Precios → Configuración: selector «Política de costo» (único control editable
   de la pantalla) y fila en la tabla; Costos muestra «Empresa» o la sucursal por
   nombre.

## Compras/Logística FASE 8-11 — compra en origen de punta a punta (2026-09-30, migración 280)

1. **Origen = domicilio del proveedor (FASE 8)**. `supplier_addresses.label` (nombre
   del domicilio, p. ej. «Bodega»); `SupplierOriginQueryService` expone los
   domicilios como orígenes. La OC guarda `origin_supplier_address_id` +
   `origin_address_snapshot`; con entrega `SUPPLIER_PICKUP` el origen es
   obligatorio. `LogisticsShipment.create()` exige el domicilio si el origen es
   el proveedor.
2. **Contenedores y carga (FASE 9)**. Tipos y contenedores se registran desde la
   pantalla; se localizan por código o QR (secreto de firma en
   `configuraciones.logistics.qr_signing_secret`, generado una vez). Cada línea
   cargada lleva lote/caducidad/peso/temperatura según el perfil del producto
   (Productos manda). Se borró el repositorio duplicado `qr_container_repository.py`.
3. **Tránsito y llegada (FASE 10)**. Nuevas transiciones `start_transit`, `arrive`,
   `start_receiving`, `close`; tabla `logistics_arrival_counts` (conteo por
   contenido: recibido, aceptado, peso). Permiso `LOGISTICA.embarque.recibir`.
4. **Recepción (FASE 11)**. `receive_and_close` genera UNA recepción por OC
   (operación uuid5 embarque+OC → idempotente), una línea por lote;
   `ReceivePurchaseOrderUseCase` valida contra el perfil (lote, caducidad, peso,
   temperatura), acumula por línea de OC, registra el rechazo como
   `QUALITY_FAILURE` y pasa lote/caducidad/peso a Inventario.
   `GoodsReceipt.shipment_id`; bug previo: la caducidad nunca se releía.
5. Composición: `backend/application/logistics/composition.py`
   (`build_logistics_services`) — Logística ya no dependía de nadie que la armara
   desde que se borró `core/events/wiring.py`. La sesión real no trae almacén:
   el destino sale del documento.
6. Hallazgo en base real: al cerrar con varios contenedores la custodia repetía
   `operation_id` (UNIQUE) → ahora `"{operación}:{contenedor}"`; prueba de regresión.

Huecos conocidos: la compra directa con recepción diferida no tiene caso de uso
(el cierre rechaza fuentes DIRECT_PURCHASE); permisos `LOGISTICA.*` fuera de
`permission_catalog` (sólo administradores); recepción fraccionaria (§27) y
`fulfillment_mode` de compra rápida sin implementar.

## Compras FASE 14 — Finanzas/CxP: conciliación de tres vías al día (2026-09-30, migración 281)

Reproducido en copia de la base real antes de corregir.

1. **Precio neto e IVA declarado**: una OC a $42 con $100 de descuento (neto $40) y
   $320 de IVA conciliaba una factura a $42 SIN IVA (CxP de $1,260 en vez de $1,392).
   Ahora se compara el precio NETO de descuento y, si la orden declaró impuesto
   (FASE 7), el IVA prorrateado a lo que ESA factura cobra. Orden sin impuesto
   capturado: no se compara (decisión del usuario 2026-09-18). Tolerancia de un
   centavo por redondeo (`ROUNDING_ALLOWANCE`).
2. **Aceptado por LÍNEA de la orden**: `goods_receipt_lines.purchase_order_line_id`
   existía en la entidad desde la FASE 11 pero NO se guardaba (sin columna). Migración
   **281**: columna + relleno de recepciones viejas sin ambigüedad. Lo recibido sin
   vínculo se reparte línea por línea (`allocate_accepted_quantities`); antes cada
   línea de un mismo producto tomaba el total.
3. **Compra rápida**: su recepción está en unidad de inventario (125 kg) y la factura
   en unidad de compra (5 costales); la conciliación y el prellenado ya convierten.
4. **Duplicados**: «A-100» = «a-100 » (mayúsculas/espacios) y el mismo folio fiscal
   (UUID del CFDI) con otro número también es duplicado.
5. **Recepción POSTERIOR de compra rápida** (`ReceiveDirectPurchaseUseCase`, botón
   «Recibir mercancía» en el historial): el modo «con recepción pendiente» no podía
   recibirse nunca → ni inventario, ni factura conciliable, ni CxP.
6. **Llave foránea en producción**: el pool abre con `foreign_keys=ON`; guardar una
   orden/compra/recepción borraba y reinsertaba sus líneas, y en cuanto una factura
   apuntaba a una línea, recibir el resto o reversar FALLABA. `_save_children` hace
   upsert por id y borra sólo lo que el documento ya no tiene.
7. Pantalla de facturas: «Liberar diferencia» reventaba (TypeError: faltaba el
   capturista); estados traducidos; quién liberó por NOMBRE; renglón con la CxP
   (folio, estado, saldo, vencimiento) leído de Finanzas; captura prellenada con lo
   PENDIENTE de facturar, total propuesto, «Editar línea»; se quitó el campo «Línea de
   OC» que pedía teclear un UUID. Documentos facturables de TODAS las sucursales.
8. Asiento de contado con el FOLIO (`CD-2026-000003`), no el UUID. Fechas de los
   asientos de compra en día LOCAL (`backend/shared/business_dates.py`): de noche el
   asiento caía en el día —y a fin de mes en el periodo— siguiente.

## Compras FASE 15 — Sin UUID ni estados técnicos en pantalla (2026-09-30)

* `backend/application/procurement/queries/display_refs.py`: Product/Supplier/Branch/
  Warehouse/User/ContainerDisplayRef + `DisplayRefResolver` («código · nombre»; si no
  existe, texto genérico, NUNCA el id). `product_labels` («CAR-000001 · Alas») en las
  lecturas de Compras y Logística (`product_names` queda para Inventario/Cárnico).
* `enterprise_view_models.py` es la ÚNICA traducción de estados (recepción, compra
  directa, diferencia, prioridad, naturaleza, tipo de documento, estado según tipo);
  filtros de estado derivados de los mismos mapas; textos del §20 («Pendiente de
  aprobación», «Confirmada por proveedor», «Recibida parcialmente»). La gráfica del
  resumen usa `ORDER_STATUS_LABELS` igual.
* **Recepciones** nunca funcionó: la página llamaba `receipts()`/`receipt_detail()`
  inexistentes y mostraba «object has no attribute 'receipts'»; ahora lista todas las
  recepciones con producto, almacén, origen y facturas por nombre.
* Filtro de periodo y fechas de las listas en hora LOCAL (`date(created_at,'localtime')`):
  lo capturado después de las 18:00 desaparecía de las listas hasta el día siguiente.
* Siglas en inglés del flujo («PR», «PO») → «Solicitud», «Orden de compra».
* Prueba: `tests/integration/procurement/test_no_technical_text_in_ui.py` recorre todas
  las páginas con documentos en muchos estados.

## Compras FASE 16 — UI/UX final (2026-09-30, migración 282)

* **Recibir una orden** por LÍNEA (ligada a su línea de OC) y con la trazabilidad que
  Productos exige (lote, caducidad, peso real, temperatura): antes una sola fila por
  producto sin esos datos → un producto con lote no se podía recibir desde Órdenes.
* **Peso variable** (§17, §41-2) por CAPACIDAD de Productos (`catch_weight_enabled` +
  `price_basis`), nunca por categoría: 5 cajas, 127.850 kg a $95/kg = $12,145.75; entra
  el peso real si la unidad de inventario es de peso; costo $95/kg. Migración **282**:
  `direct_purchase_lines.net_weight/pricing_basis/inventory_by_weight`. La OC no exige
  peso (se pesa al recibir). Bases soportadas: PER_KILOGRAM y PER_PIECE_WITH_ACTUAL_WEIGHT.
* Auditoría estática del módulo: sin `setStyleSheet`, sin colores, sin `QPushButton`
  crudos, sin acciones genéricas al fondo.

## Compras FASE 17 — Pruebas E2E del §41 (2026-09-30)

`tests/e2e/test_procurement_master_prompt_e2e.py`: base NACIDA con el arranque real
(`run_database_bootstrap_sequence`, todas las migraciones) + bus de eventos real en un
bus local. 11 pruebas: compra rápida completa, peso variable, abarrote 125 kg, PR→OC,
adjudicación dividida, compra en origen, promedio $50, sin UUID/estados, permisos,
crédito → CxP → pago (debe = haber). Hallazgo: la recepción en origen publicaba su
outbox por su cuenta en el bus global; ahora usa el despachador del presentador.

## Compras — cierre de pendientes (2026-09-30, migraciones 283-287)

1. **Permisos (283)**: `backend/application/logistics/permissions.py` publica
   `ALL_LOGISTICS_PERMISSIONS` → LOGISTICA entra al catálogo (era inotorgable). Medido:
   `rol_permisos` sólo tenía las 5 acciones gruesas de COMPRAS y ninguna de LOGISTICA,
   así que ningún rol no administrador operaba órdenes, recepciones ni embarques.
   Siembra por función (decisión del usuario): system_owner/admin/gerente todo;
   almacen ver + RECIBIR (recepción, llegada/conteo, escaneo, mover/liberar
   contenedores, etiquetas); cajero/solo_lectura/repartidor nada.
2. **Una sola lista base (284)**: activar otra lista base la REEMPLAZA en la misma
   operación (`ActivatePriceListUseCase._side_effects`, decisión del usuario). Datos:
   queda `BASE`, se desactiva `ORIGIN-00001` (ambas sin precios; mandaba la más
   reciente sin que nadie lo eligiera).
3. **Surtido de la compra rápida (285, §11)**: `FulfillmentMode` (inmediata,
   posterior, entrega del proveedor, recolección en proveedor) separado del TIPO
   (mercancía/servicio/gasto) que antes compartía combo. Recolección exige la bodega
   del proveedor (id + foto). Compra en origen sólo ofrece compras directas
   CONFIRMADAS con recolección, y `receive_and_close` ya las recibe
   (`ReceiveDirectPurchaseUseCase` con lo contado: aceptado, rechazo, lote, peso).
4. **Recepción fraccionada (286, §27)**: `product_unit_conversions.allow_fractional_receipt`
   por presentación (Productos → Unidades de compra, casilla y botón; auditado). Si
   no se permite, la recepción exige unidades completas; si sí, el diálogo captura
   «4 costales + 22 kg sueltos» = 4.88. Por omisión se permite (no cambia nada vigente).
5. **OC a precio por kg (287)**: `purchase_order_lines.pricing_basis/inventory_by_weight`
   desde Productos (la OC no exige peso). Importe estimado = cantidad × kg nominales ×
   $/kg; al recibir se paga el PESO REAL aceptado; la factura se prellena y concilia en kg.
6. FASE 4 verificada: Compras no tiene campos para editar unidad ni factor; el que
   manda la compra rápida se ignora (manda Productos).

## Ventas/POS — devoluciones con reembolso, puntos por compra y canje (2026-10-02, migración 289)

Cierra las decisiones que la re-auditoría de Ventas dejó abiertas (detalle en
`docs/refactor/SALES-23_reauditoria.md` §5).

1. **Devolución parcial:** reembolso por el método original, efectivo primero
   (dominio `refund_service`; el importe absorbe la parte del descuento a nivel
   venta); crédito → nota de crédito sobre la CxC; efectivo desde el turno con tope
   y autorizador; `SaleReturnedHandler` (espejo de la venta + costo de venta) y
   `SaleReversedHandler` suscritos en `wire_sales`.
2. **Puntos por compra:** `LoyaltyAccrualPolicy` + `AccrueSalePointsUseCase` /
   `RemoveSalePointsUseCase` / `RestoreSaleRedemptionUseCase`, por el bus de Ventas
   con política DELEGADA (`SALES_GRANT`). Caducidad FIFO sobre el remanente.
   Ajustes en Fidelidad → Configuración (`UpdateLoyaltyProgramSettingsUseCase`).
3. **POS:** «Puntos a ganar» real, botón/diálogo de canje, cancelar/reversar
   devuelve el canje, el outbox se despacha también tras devolver/reversar/cancelar.
4. **Suspender con faltante** reserva lo disponible.
5. **Migración 289** (idempotente, sin pisar nada): permisos `GROWTH_ENGINE.puntos.
   canjear` (cajero, gerente, admin, system_owner), `CAJA.reembolso.ver/solicitar/
   autorizar` (gerente, admin, system_owner), `GROWTH_ENGINE.ver/configuracion.ver/
   configuracion.editar` (admin, system_owner); tope REFUND $5,000 (sólo si no hay
   ninguno); reglas de puntos en `configuraciones`. Verificada en copia de la base
   real: 19 permisos, tope y 3 reglas.

## Ventas/POS — re-auditoría del prompt maestro (2026-10-01/02, migración 288)

Re-pegado del prompt maestro de Ventas/POS sobre un POS ya construido (SALES-0..22).
Se midió el POS vivo contra una COPIA de la base real (capturas a 1366×768 y
1920×1080) en vez de releer el prompt. Detalle completo:
`docs/refactor/SALES-23_reauditoria.md`.

1. **P0 — no se podía cobrar nada recibido por Compras.** La reserva de Ventas
   buscaba un saldo SIN lote y Compras siempre recibe con lote: "Sin balance
   disponible para reservar" y la venta atorada en cobro. `ReserveStockForSaleUseCase`
   hereda la reserva por lotes de Producción (estrategia `sales.allocation_strategy`,
   FEFO por omisión). Vender sin existencia autorizado saca primero de los lotes;
   la devolución vuelve al lote del que salió; el reverso repone TODAS las líneas
   (antes sólo la primera: misma identidad de movimiento).
2. **Folio comercial (288).** `sales.sale_number` no lo asignaba nadie. El cobro
   reserva `V-<código de sucursal>-000001` del contador seguro de documentos, en la
   misma transacción; la 288 agrega el índice único parcial.
3. **Ticket de venta.** `PrinterService` se borró con `core/` y el shell pasaba
   `printer_service=None`: el POS no imprimía nada. `SalesTicketPrinter` rutea por
   Document Output (`SALE_TICKET` por sucursal) y renderiza ESC/POS; el cobro pide el
   ticket DESPUÉS de confirmar. Sin impresora configurada lo dice, no revienta.
4. **Cables a oscuras cerrados:** autorizador de devolución/reverso (la política de
   sesión sólo responde por el cajero), canje de puntos (cliente de Fidelidad sin
   política), salud de dispositivos (leía `hardware_config`, tabla sin escritores).
5. **Reglas nuevas de dominio:** sin precio no hay línea (`PricingUnavailableError`;
   la base real no tiene ningún precio y el carrito vendía a $0); peso con gramos
   (`WeightPolicy`); sólo el efectivo admite cambio; `CashPaymentPolicy` calcula el
   cambio; descuento por porcentaje en el dominio.
6. **Pantalla (layout del contrato intacto):** COBRAR dominante (salía gris), barra
   con cajero/sucursal/caja/dispositivos/Corte Z, captura de peso, corregir/quitar
   línea, Devolución F10, Reimprimir/Factura sobre la venta cobrada elegida,
   Reanudar con selector, Cancelar con motivo, cambio visible, descuentos rápidos,
   cliente asignado visible, filtro de categorías (mandaba el nombre, filtraba por id).

## Fidelidad — re-auditoría LOY-29 (2026-10-02, migraciones 290 y 291)

Re-pegado del prompt maestro de Fidelidad; se midió el módulo vivo contra una
COPIA de la base real con los dos usuarios reales. Detalle completo:
`docs/refactor/LOY-29_reauditoria.md`.

* **290 — permisos.** El dueño tenía 4/58 acciones de `GROWTH_ENGINE` y 0/27 de
  `TARJETAS_FIDELIDAD`: módulo visible e inoperable. Dueño y admin reciben todo;
  gerente el juego operativo; cajero nada nuevo. Idempotente; un rol ausente se
  omite.
* **291 — tablas legacy.** Retira 38 tablas de Fidelidad/Growth Engine/Tarjetas/
  Rifas que no tienen lector ni escritor y estaban vacías (más la configuración de
  fábrica `config_programa_fidelidad`). Una tabla con filas se conserva y se avisa.
  En el mismo cambio se retiró la doble lectura de saldo sobre `loyalty_ledger` y
  Cliente 360 dejó de leer `loyalty_snapshots`.
* Sin cambios de esquema canónico: la UI completa, la consulta de registros, la
  resolución de tarjeta del POS, la auditoría de eventos y las correcciones de
  dominio (segregación de programas, reverso sin saldo negativo, motivo de
  reimpresión, reverso de tarjeta) son código.

### 292 — el QR de las tarjetas deja de guardarse en claro (2026-10-03)

`loyalty_card_tokens.token` → `token_hash` + `token_prefix` + `token_version`;
`loyalty_digital_card_projections.qr_token` → `token_id`; nueva
`loyalty_card_secrets` (secreto HMAC de la instalación). Reconstrucción de tablas
con `legacy_alter_table=ON` porque la base real trae una vista legacy rota que
hacía fallar el RENAME y, con él, el arranque. Filas previas: huella con versión
0 (resuelven; para reimprimir hay que rotar el QR). Real: 0 filas.

### 293 — tarjetas preimpresas y asignación (2026-10-03)

`loyalty_cards.customer_id`/`membership_id` admiten NULL (estado `UNASSIGNED`);
reconstrucción con `foreign_keys=OFF` + `legacy_alter_table=ON` y
`foreign_key_check` al final. Nueva `loyalty_card_assignments` (una por tarjeta,
idempotente por `operation_id`).

### 294 — Fidelidad, vales, cupones y sorteos llegan a contabilidad (2026-10-03)

Decisión del usuario: contabilizar puntos, cupones, vales, boletos y cualquier
programa de fidelidad. Tablas de estado del puente (`loyalty_finance_links`,
`loyalty_finance_point_credits`, `loyalty_finance_point_allocations`);
`commercial_obligations` se reconstruye para admitir `SWEEPSTAKES_PRIZE` (el
CHECK enumera los tipos; `foreign_keys=OFF` + `legacy_alter_table=ON` por la
vista legacy rota de la base real); en un catálogo de Finanzas ya sembrado se
agregan la cuenta 2136 "Provisión de premios de sorteos" y el perfil
`SWEEPSTAKES_PRIZE` (la siembra se salta si el catálogo existe; ahora completa
lo que falte). Real: 0 obligaciones previas; la copia real asentó 4 pólizas
cuadradas. Detalle en `docs/refactor/LOY-29_reauditoria.md` §3e.

### 295 — reglas de acumulación y combinación de beneficios (2026-10-03)

Decisión del usuario: las reglas salen de Fidelidad y el POS las ejecuta.
`loyalty_rules` (definición declarativa validada por el dominio),
`loyalty_sale_evaluations` (desglose por compra, también historial de visitas),
`loyalty_rule_applications` (usos por regla, UNIQUE regla+venta) y
`loyalty_stacking_rules` sembrada con todo permitido salvo varios cupones por
venta. Sin reglas activas, la acumulación es idéntica a la de la 289. Detalle en
`docs/refactor/LOY-29_reauditoria.md` §3f.

### 296 — cupones y vales en la caja (2026-10-03)

`sale_coupons` (cupones que Fidelidad aprobó y apartó para la venta) y el permiso
`POS.pago.vale` para cajero, gerente, admin y dueño (mismo reparto que los pagos
de contado de la 268; `INSERT OR IGNORE`). El perfil contable `PREPAID_VOUCHER`
(vale prepagado vendido en caja: Dr caja / Cr 2132) se agrega a un catálogo ya
sembrado por la misma vía que la 294.

### 297 — recompensas de producto con inventario y cumpleaños (2026-10-03)

`loyalty_reward_products`, `loyalty_reward_deliveries` (salida y costo de cada
entrega), `loyalty_birthday_grants` (beneficio de cumpleaños una vez al año) y
`customer_birthdays` (Clientes; sólo con consentimiento). Detalle en
`docs/refactor/LOY-29_reauditoria.md` §3g.

### 298 — `loyalty_birthday_grants.year` a TEXT (2026-10-03)

La 297 dejó `year INTEGER` dentro de la llave primaria compuesta; la validación
de arranque (ninguna columna de llave primaria entera) la rechazó y la
aplicación no abría ("La DB no nació UUIDv7 limpia"). Se reconstruye con
`year TEXT` conservando las filas; las migraciones corren antes de la
validación, así que el siguiente arranque pasa. Prueba de regresión: ninguna
tabla nueva de Fidelidad/Clientes tiene llave primaria entera.


### 299 — estados de listas de precio y una sola lista base activa (2026-10-04)

Contexto: en la base real `BASE01` estaba ACTIVA con cero precios (y no había un
solo precio en el módulo). Una lista activa es inmutable, así que quedaba vacía
para siempre; además el catálogo del POS leía la lista llamada `BASE` (ya
INACTIVA) y nunca la activa.

La migración (idempotente, sin borrar filas):

1. Normaliza `price_list.status`/`kind` SÓLO cuando la variante es inequívoca
   (mayúsculas/espacios de un valor canónico: `'active'` → `ACTIVE`). Cualquier
   otro valor se deja intacto y se registra en el log; el repositorio lo informa
   con `UnknownPriceListStatusError` (valor real) y la pantalla lo muestra como
   "No reconocido («valor»)".
2. Reaplica la regla de la 284 (queda la lista que se llama `BASE`, si no la más
   reciente) por si la normalización destapó una segunda base activa; las demás
   pasan a INACTIVE.
3. Crea el índice único parcial `ux_price_list_single_active_base`
   (`kind='BASE' AND status='ACTIVE'`). El DDL vive en `pricing_schema.py`
   (`ensure_single_active_base_index`), que no lo crea si hoy hubiera dos.

Cambios de código que acompañan (no son DDL): activar y aprobar exigen al menos
un precio no vencido (`EMPTY_LIST`); sólo DRAFT/UNDER_REVIEW reciben precios
(INACTIVE dejó de ser editable); individual, lote y escala por volumen comparten
guardas de estado, permiso (`BRANCH_PRICE_MANAGE` para precio de sucursal) y
alcance; el upsert de `product_price` ahora guarda la vigencia; la escritura usa
la fila EXACTA (lista, producto, sucursal) — antes fijar un precio de sucursal
con el general existente reventaba con `IntegrityError`; el catálogo del POS lee
la lista base ACTIVA con vigencia y precio por sucursal, igual que el cobro.

**Recuperar una lista activa vacía ya existente** (no se toca en la migración:
desactivarla en silencio dejaría a la instalación sin lista base):
Listas de precio → seleccionar la lista → Duplicar (la copia nace en Borrador)
→ Precios por producto → capturar precios en la copia → Enviar a revisión →
Aprobar y Activar con OTRO usuario (segregación de funciones). Al activarse, la
copia reemplaza a la lista vacía, que queda INACTIVE como historial. Verificado
sobre copia de la base real (2026-10-04): `BASE01` → `BASE01-2` con 3 precios;
cobro y tarjeta del POS coinciden.
