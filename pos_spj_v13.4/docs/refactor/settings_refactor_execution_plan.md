# SET-0 — Plan de ejecución del bounded context Settings / Device Management / Document Output / Customer Display

Estado: `SET-0 AUDITORIA_COMPLETA`, `SET-1 COMPLETO 2026-08-22` (permisos
granulares + `ConfiguracionAuthorizationPolicy` (`require`/`has_permission`/
`authorize_exception`) cableada en el presenter real; segregación
creador≠aprobador en versiones de plantilla; secretos SMTP + MercadoPago
ambos en `SecretStoreGateway`; auditoría en caliente para cambios de
estado críticos — ver "Avance SET-1"), `SET-2 DOMINIO_COMPLETO`
(Configuration Governance: `backend/domain/settings/`), `SET-3
ESQUEMA_COMPLETO` (migración 208 + repositorios de infraestructura),
`SET-4 COMPLETO` (overrides + cache), `SET-5 COMPLETO`
(`CompanyProfile`/`BranchProfile`), `SET-6 COMPLETO` (`Workstation`;
CRUD real en la UI desde 2026-08-22, ver "Avance SET-6" continuación),
`SET-7 COMPLETO` (Device Management; Asignaciones con UI real desde
2026-08-22, ver "Avance SET-7" continuación), `SET-8 COMPLETO` (Impresoras;
Perfiles conectado + Rutas de impresión con UI real desde 2026-08-22,
ver "Avance SET-8" continuación),
`SET-9 COMPLETO` (Básculas/lectores; capacidades WEIGH/SCAN_1D/SCAN_2D
conectadas desde 2026-08-22, ver "Avance SET-9" continuación), `SET-10 COMPLETO` (Cajones/
terminales: gateways/asignación/pruebas/seguridad; capacidades
DRAWER_PULSE/pago conectadas desde 2026-08-22, ver "Avance SET-10"
continuación — cierra la familia SET-7..10 de perfiles con capacidades),
`SET-11 COMPLETO` (Document Output: Templates/Versiones ya CRUD;
activar/desactivar familia de plantilla + edición conectadas con UI
real desde 2026-08-22, ver "Avance SET-11" continuación — Renderers/
PrintJobs/Worker confirmados como límite de alcance, no gap),
`SET-12 COMPLETO` (Tickets: Secciones/DTO/Routing/Reimpresión; Ventas
cortado a un productor real de `PrintJob` vía routing/reprint desde
2026-08-22, ver "Avance SET-12" continuación — rendering/device-targeting
físico siguen fuera de alcance, sin hardware real),
`SET-13 COMPLETO` (Marketing en tickets: Campaigns/Rules/FOMO policy/
Loyalty summary; mensajes reales en tickets del POS de escritorio + CRUD
de campañas desde 2026-08-23, ver "Avance SET-13" continuación), `SET-14 COMPLETO` (Etiquetas: Label templates/
Variables/Serialización/Routing; INV-26 imprime etiquetas reales vía
`NetworkLabelPrintGateway` desde 2026-08-23, ver "Avance SET-14"
continuación — primer gateway físico real de todo el track, sin
validación de hardware físico), `SET-15 COMPLETO` (Sorteos: Integración
con Sweepstakes/Plantilla/Boleto/Reimpresión; sales_pos emite+imprime
boletos reales desde 2026-08-23, ver "Avance SET-15" continuación —
corrigió una razón de bloqueo incorrecta de la auditoría original),
`SET-16 COMPLETO`
(Numeración: Sequences/Reservas/Reset/Idempotencia; Procurement cortado a
`reserve_and_get()` atómico desde 2026-08-23, ver "Avance SET-16"
continuación — cierra un race condition real, no solo conecta código
sin usar), `SET-17 COMPLETO`
(Customer Display: Displays/Layouts/Modes/Gateway; Ventas cortado a un
Gateway real de segunda pantalla vía `CustomerDisplayWindow`/
`SalesCustomerDisplayClient` desde 2026-08-25, ver "Avance SET-17"
continuación — primer Gateway del track sin frontera de hardware físico,
corrigió un supuesto erróneo del propio plan sobre el bootstrap de
Workstation), `SET-18 COMPLETO`
(Contenido y publicidad: Content/Campaigns/Placements/Approval/Metrics;
CRUD real + rotación real de anuncios en la pantalla idle de sales_pos
desde 2026-08-28, ver "Avance SET-18" continuación — corrigió dos bugs
reales, uno de visibilidad de ventana Qt heredado de SET-17 y otro de
persistencia en el repositorio de campañas),
`SET-19 COMPLETO` (Integraciones: Definitions/Instances/Credentials/
Health/Webhooks; CRUD real + corte real de la resolución de credencial
de MercadoPago desde 2026-08-28, ver "Avance SET-19" continuación —
diseño conservador con fallback al comportamiento original en cada
fallo, la superficie de mayor riesgo (pagos en vivo) que este track ha
tocado), `SET-20 COMPLETO` (WhatsApp y notificaciones: Accounts/
Templates/Channels/Routing; CRUD real + corrección real del hueco de
parámetros faltantes en `whatsapp_service/messaging/templates.py::
send_event_template()` desde 2026-08-28, ver "Avance SET-20" continuación
— la única ronda de este track que edita el código propio del
microservicio WhatsApp, reimplementado localmente, nunca importado
cruzando el límite CLAUDE.md §14), `SET-21 COMPLETO` (Feature flags: Flags/
Rules/Rollout/Approval; CRUD real de Flags + origen real de solicitudes
de cambio desde 2026-08-28, ver "Avance SET-21" continuación — la
pantalla de Aprobar/Rechazar/Aplicar existía pero nada creaba un
`FeatureFlag` ni originaba un `FeatureFlagChangeRequest`, así que nunca
tenía nada real que aprobar), `SET-22 COMPLETO` (Apariencia: Themes/
Tokens/Light-dark/Density; CRUD real de los 4 pilares desde 2026-08-28,
ver "Avance SET-22" continuación — el corte más grande de este track por
número de entidades nuevas con CRUD; mismo hueco de origen que SET-21
pero en 4 entidades en vez de 2), `SET-23 COMPLETO` (Offline: Cache/
Version/Sync/Expiration; CRUD real del pilar "Expiration" (`CacheExpirationPolicy`)
desde 2026-08-28, ver "Avance SET-23" continuación — a diferencia de
SET-21/22, "Cache"/"Version"/"Sync" (`OfflineCacheEntry`) se dejó
deliberadamente de solo lectura: es un artefacto de runtime que
escribiría un consumidor real de lectura offline-first, y ese
consumidor no existe — construir un formulario para crearlo a mano no
reflejaría ningún flujo real; Offline deja de ser la única sección sin
página dedicada — ver §"Avance SET-2" a §"Avance SET-23" abajo).
Fase UI/UX
(fuera de la numeración SET-N, ver §"Avance UI/UX"): primer frontend
PyQt5 para los 9 bounded contexts — `frontend/desktop/modules/
configuracion/`, todas las 9 secciones con página dedicada y escritura
real tras el repegado de SET-21/22/23 (2026-08-28); repegado de UI/UX el
mismo día conectó el badge de solicitudes pendientes del sidebar
(existía en el modelo de datos desde la fase original, nunca se
computaba) — ver "Avance UI/UX" continuación. SET-25 (Eliminación de
legacy) re-auditado el mismo día (Actualización 5) — bloqueos
originales confirmados vigentes, único hallazgo ejecutado: 2 lecturas
de `mercado_pago_service.py` migradas de SQL crudo a
`PaymentProviderSettingsService` — ver
`docs/refactor/SET-25_legacy_removal_report.md`. Usuarios/Roles/
Auditoría (10ª sección de Configuración, primer caller real de la capa
"FASE 6" dormida `backend/application/use_cases/save_user_use_case.py`)
construido el mismo día — ver "Avance Usuarios y Roles" abajo.
Inventario de legacy realizado (`docs/refactor/settings_legacy_inventory.md`).

## Alcance

Cuatro bounded contexts nuevos, gobernados por un único punto de entrada de
navegación **Configuración**:

- `backend/domain/settings/` — Configuration Governance (definitions,
  values, scopes, versiones, feature flags, empresa/sucursal/estación).
- `backend/domain/device_management/` — dispositivos, perfiles, asignación,
  salud/diagnóstico.
- `backend/domain/document_output/` — plantillas de documento/etiqueta,
  print jobs, routing, numeración/folios.
- `backend/domain/customer_display/` — pantalla del cliente, contenido,
  campañas publicitarias, mensajes de ticket.

Integraciones (WhatsApp, email, mapas, pagos, webhooks) y Feature Flags se
implementan como una sección de `settings/` que orquesta, sin duplicar,
`backend/security/secrets/` (ya construido) para credenciales.

## Brechas bloqueantes (de la auditoría SET-0)

1. `configuraciones` tiene dos definiciones de tabla incompatibles en la
   misma migración; solo la primera se crea (drift silencioso).
2. Secretos en texto plano (SMTP, WhatsApp, Twilio, MercadoPago) sin
   conectar al `SecretStoreGateway` ya existente en `backend/security/secrets/`.
3. `hardware_config` tiene PK en `tipo` únicamente — no soporta
   configuración real por sucursal/estación pese a tener `sucursal_id`.
4. UI accediendo hardware directo (`modulos/etiquetas.py`,
   `hardware/cajon_dinero.py`, `hardware/lector_qr.py`,
   `core/services/hardware_service.py`) — cero gateways reales conectados,
   solo stubs en la capa moderna (`StubCashHardwareGateway`,
   `StubScaleGateway`).
5. Tres pipelines de etiquetas paralelos y dos constructores de ticket de
   delivery independientes, ambos con SQL embebido en la clase de
   renderizado.
6. Folios/numeración vía `MAX(document_number)+1` sin contador atómico
   confirmado (`support_repositories.py::next_number`).
7. `permission_catalog.py` no tiene una clave unificada `CONFIGURACION`/
   `SETTINGS` — solo 3 stubs (`CONFIG_HARDWARE`, `CONFIG_MODULOS`,
   `CONFIG_SEGURIDAD`), a diferencia de todo bounded context ya migrado.
8. Webhook de MercadoPago sin verificación de firma (`MP_WEBHOOK_SECRET`
   definido pero nunca leído) — riesgo de seguridad real, no solo deuda
   técnica.
9. Violación REGLA CERO ya presente:
   `migrations/standalone/096_configuration_services_schema.py` inserta un
   literal entero `1` en una PK `TEXT`.
10. Credenciales de arranque hardcodeadas (`admin`/`admin123`, `demo`/`demo`,
    SHA-256 sin sal) — no explotables pero deben eliminarse.
11. `docs/refactor/modules/configuracion.md` tiene marcadores de conflicto
    de git sin resolver (líneas 242-481) y no debe citarse como autoridad
    hasta resolverse aparte.

## Prior art a reusar como molde (no reinventar)

- `migrations/standalone/175_cash_register_bounded_context_schema.py` +
  `176_cash_register_configuration_schema.py` — único bounded context con
  configuración tipada jerárquica `SYSTEM→COMPANY→BRANCH→REGISTER→USER`,
  `PrintJob`/`PrintAudit` con `CHECK` constraints y `reprint_reason`
  obligatorio, y sync por dispositivo (`local_sequence`/
  `last_synced_sequence`).
- `backend/application/cash_register/hardware.py` — Protocols de hardware
  (`CashDrawerGateway`, `ReceiptPrinterGateway`, `PaymentTerminalGateway`).
- `backend/infrastructure/printing/cash_register_renderers.py` — pipeline
  dual HTML/ESC-POS ya limpio, sin SQL embebido.
- `migrations/standalone/171_logistics_bounded_context_schema.py` —
  `logistics_print_jobs`/`logistics_container_labels`, molde para
  `LabelTemplate`/`PrintJob` de etiquetas.
- `backend/security/secrets/` — `SecretStoreGateway`,
  `EncryptedLocalSecretStore`, `WindowsCredentialManagerSecretStore` — usar
  directo, no reconstruir.
- `core/ticket_escpos_renderer.py` + `core/tickets/ticket_print_model.py` —
  renderer de ticket de venta ya orientado a modelo de datos, molde para
  `document_output`.
- `backend/application/sales/queries/customer_display_query_service.py` —
  único artefacto de Customer Display; base de diseño (greenfield, sin
  legacy que retirar).

## Reglas a preservar con characterization tests

- La resolución de valor efectivo de configuración sigue el orden de
  herencia: específico → ámbito padre → empresa → global → default.
- Ningún valor activo se sobreescribe en sitio; toda edición crea una nueva
  versión (`ConfigurationValue`, estado `DRAFT→...→ACTIVE`).
- Un `PrintJob` fallido puede reintentarse sin duplicar impresión física.
- Una reimpresión de documento sensible (corte Z, boleto de sorteo) exige
  permiso + motivo auditado, y conserva folio/participación original.
- Ningún secreto se devuelve completo a la UI tras guardarse (solo
  `masked_value`).
- El bloque publicitario en pantalla del cliente nunca oculta datos
  transaccionales (producto, cantidad, precio, total, pago, cambio).
- Feature flags no sustituyen permisos ni viceversa.

## Secuencia y gates

| Fase | Resultado | Gate |
| --- | --- | --- |
| SET-0 | Auditoría de legacy + plan de ejecución | Este documento + `settings_legacy_inventory.md` |
| SET-1 | Permisos granulares, scopes, segregación, auditoría, secretos conectados | **Hecho** — 39 tests nuevos (unit + integración), ver "Avance SET-1" (continuación 2026-08-22) |
| SET-2 | Configuration Governance: `ConfigurationDefinition`/`Value`, versiones, vigencia, policies, eventos | **Hecho** — `tests/unit/settings/` (93 passed), ver "Avance SET-2" |
| SET-3 | Esquema born-clean UUIDv7 (`configuration_*` **hecho**; `device_*`/`document_*`/`customer_display_*` esperan a sus SET respectivos) | **Hecho para `configuration_*`** — 32 tests de integración, ver "Avance SET-3" |
| SET-4 | `ConfigurationResolutionService` (herencia/fallback/cache) | **Hecho** — ver "Avance SET-4" |
| SET-5 | `CompanyProfile`/`BranchProfile` (extiende `sucursales`, no la reemplaza — ver "Avance SET-5") | **Hecho** — 205 tests, ver "Avance SET-5" |
| SET-6 | `Workstation` (registro, estado, versión, offline) | **Hecho** — 235 tests, ver "Avance SET-6" |
| SET-7 | Device Management: `Device`/`DeviceProfile`/asignación (nuevo, no reemplaza `hardware_config` todavía — ver "Avance SET-7") | **Hecho** — 312 tests, ver "Avance SET-7" |
| SET-8 | Impresoras: perfiles, routing, failover | **Hecho** — 365 tests, ver "Avance SET-8" |
| SET-9 | Básculas/lectores: puertos, protocolo, diagnóstico | **Hecho** — 426 tests, ver "Avance SET-9" |
| SET-10 | Cajones/terminales: gateways (contratos, sin E/S real — ver "Avance SET-10"), asignación, pruebas, seguridad | **Hecho** — 479 tests, ver "Avance SET-10" |
| SET-11 | Document Output: `DocumentTemplate`/`PrintJob`/worker (nuevo, no reemplaza `print_job_log` todavía — ver "Avance SET-11") | **Hecho** — 575 tests, ver "Avance SET-11" |
| SET-12 | Tickets: secciones, DTO por módulo, reimpresión (`ticket_delivery.py`/`ticket_printer_service.py` NO eliminados en este corte — ver "Avance SET-12") | **Hecho** — 627 tests, ver "Avance SET-12" |
| SET-13 | Marketing en tickets + FOMO responsable | **Hecho** — 703 tests, ver "Avance SET-13" (incluye `marketing_claim_validation_policy`) |
| SET-14 | Label Management: templates/variables/serialización/routing (los 3 pipelines legacy de etiquetas NO eliminados en este corte — ver "Avance SET-14") | **Hecho** — 731 tests, ver "Avance SET-14" |
| SET-15 | Boletos de sorteo integrados con Sweepstakes (cutover real a sales_pos desde 2026-08-23, ver "Avance SET-15") | **Hecho** — 734 tests, ver "Avance SET-15" |
| SET-16 | `DocumentNumberSequence`: sequences/reservas/reset/idempotencia (Procurement cortado a generador atómico real desde 2026-08-23 — ver "Avance SET-16") | **Hecho** — 754 tests, ver "Avance SET-16" |
| SET-17 | Customer Display: Displays/Layouts/Modes/Gateway (Ventas cortado a un Gateway real de segunda pantalla desde 2026-08-25, `CustomerDisplayQueryService` NO tocado — ver "Avance SET-17") | **Hecho** — 777 tests, ver "Avance SET-17" |
| SET-18 | Contenido y publicidad: Content/Campaigns/Placements/Approval/Metrics (CRUD real + rotación real de anuncios en sales_pos desde 2026-08-28 — ver "Avance SET-18") | **Hecho** — 847 tests, ver "Avance SET-18" |
| SET-19 | Integraciones: Definitions/Instances/Credentials/Health/Webhooks (CRUD real + corte real de MercadoPago desde 2026-08-28 — ver "Avance SET-19") | **Hecho** — 917 tests, ver "Avance SET-19" |
| SET-20 | WhatsApp y notificaciones: Accounts/Templates/Channels/Routing (CRUD real + corrección real del hueco de parámetros en whatsapp_service desde 2026-08-28 — ver "Avance SET-20") | **Hecho** — 962 tests, ver "Avance SET-20" |
| SET-21 | Feature flags: Flags/Rules/Rollout/Approval (`FeatureFlagService`/`feature_flags` legacy NO tocados en este corte — ver "Avance SET-21") | **Hecho** — 1019 tests domain-layer; **CRUD real + origen de solicitudes desde 2026-08-28, 1617 tests verdes** — ver "Avance SET-21" continuación |
| SET-22 | Apariencia: Themes/Tokens/Light-dark/Density (`theme_engine.py`/`ThemeService`/`frontend/desktop/themes/`/claves `configuraciones` legacy NO tocados en este corte — ver "Avance SET-22") | **Hecho** — 1078 tests domain-layer; **CRUD real de los 4 pilares desde 2026-08-28, 1617 tests verdes** — ver "Avance SET-22" continuación |
| SET-23 | Offline: Cache/Version/Sync/Expiration (`sync/` engine/tablas `sync_*`/`ConfigurationCache`/`AddressCache` legacy NO tocados en este corte — ver "Avance SET-23") | **Hecho** — 1121 tests domain-layer; **CRUD real de Expiration desde 2026-08-28, 1628 tests verdes** — ver "Avance SET-23" continuación |
| SET-24 (redirigido) | UI/UX: primer frontend PyQt5 para los 9 bounded contexts | **Hecho** — 36 tests; **badge real de solicitudes pendientes en el sidebar desde 2026-08-28, 1637 tests verdes** — ver "Avance UI/UX" continuación |
| SET-25 | Eliminación de legacy | **Auditado, mayormente bloqueado** — ver `docs/refactor/SET-25_legacy_removal_report.md`. 2 imports muertos eliminados (255 tests, cero regresiones); 8 de 10 ítems requieren migración de consumidores reales que ningún SET anterior ejecutó a propósito (regla CLAUDE.md "NO eliminar funcionalidad operativa sin migración completa"). **Re-auditado 2026-08-28 (Actualización 5)**: bloqueos confirmados vigentes; único hallazgo nuevo ejecutado — `mercado_pago_service.py`'s `mp_webhook_url`/`mp_return_url` migrados de SQL crudo a `PaymentProviderSettingsService`, 1647 tests verdes. |

## Siguiente corte recomendado: SET-1

1. Registrar clave unificada de permisos para Configuración/Settings en
   `core/security/permission_catalog.py`, siguiendo la convención punteada
   `MODULO.accion` ya usada por POS/CRM/FINANZAS/PRODUCTOS (no la
   convención `CASH_*`), con acciones separadas por sub-área (governance,
   devices, documents, customer_display, integrations, feature_flags).
2. Definir segregación de funciones (§59 del prompt maestro): quien crea
   una configuración crítica no la aprueba; quien diseña plantilla fiscal
   no la activa solo; quien administra secretos no ve operación financiera.
3. Conectar `SecretStoreGateway` (ya construido) como único mecanismo de
   almacenamiento de credenciales; migrar SMTP/WhatsApp/Twilio/MercadoPago
   fuera de columnas TEXT planas.
4. Corregir la verificación de firma faltante en el webhook de
   MercadoPago (`whatsapp_service/webhook/mercadopago.py`) como parte de
   este mismo corte de seguridad, no como deuda separada.
5. Auditoría en caliente (§60) para: rotación de secreto, cambio de
   impresora fiscal, reimpresión de corte Z/boleto, activación de
   integración crítica.

Tests prioritarios: catálogo de permisos sin duplicar código de módulo
`'CONFIGURACION'` legacy; segregación creador≠aprobador en al menos una
policy; cero secreto en texto plano tras la migración de SMTP/WhatsApp;
firma HMAC obligatoria en webhook de MercadoPago; auditoría con
`before`/`after` enmascarado para campos `sensitive`.

## Avance SET-1

- **Hecho** — Webhook de MercadoPago (`whatsapp_service/webhook/mercadopago.py`)
  ahora valida `X-Signature` (`ts`/`v1`) contra `MP_WEBHOOK_SECRET` siguiendo
  el esquema oficial de MercadoPago (`manifest = "id:{data.id};request-id:{x-request-id};ts:{ts};"`,
  HMAC-SHA256, comparación con `hmac.compare_digest`), igualando el rigor ya
  existente en el webhook de WhatsApp (`middleware/hmac_validator.py::verify_signature`).
  Nueva función compartida `verify_mp_signature` en el mismo módulo. Si
  `MP_WEBHOOK_SECRET` no está configurado, la notificación se acepta sin
  validar pero ahora con `logger.warning` explícito (antes era silencioso).
  Cobertura: `whatsapp_service/tests/test_mercadopago_webhook_signature.py`
  (9 tests, unit + integración vía `TestClient`) — verde.
- **Pendiente** — el resto de los puntos 1, 2, 3 y 5 de "Siguiente corte
  recomendado" (catálogo de permisos unificado, segregación de funciones,
  migración de credenciales SMTP/WhatsApp/Twilio a `SecretStoreGateway`,
  auditoría en caliente) no se ha iniciado; requiere decisión de diseño
  previa sobre convención de permisos (`MODULO.accion` vs. `CASH_*`, ver
  riesgo correspondiente) antes de tocar código de catálogo compartido.
- **Hecho** — eliminado el segundo `CREATE TABLE IF NOT EXISTS configuraciones`
  muerto en `m000_base_schema.py::_create_core_config` (§0.2 del inventario).
  Verificado sin regresión: mismo conjunto exacto de tests, idéntico con y
  sin el cambio (vía `git stash`); bootstrap fresco confirmado con
  `scripts/bootstrap_db.py`. Documentado en `migrations/MIGRATION_LOG.md`.

> **Corrección (2026-08-21, mismo día):** el primer recuento de esta
> sección decía "45 failed / 150 passed" y "45 tests ya escritos y en
> rojo". Ese número estaba inflado por un **bug de cwd propio de esta
> auditoría, no del repositorio**: se corrió `pytest` desde
> `pos_spj_v13.4/pos_spj_v13.4/` (el paquete interno) en vez de desde la
> raíz del repo, y varios tests de `tests/architecture/` resuelven rutas
> relativas tipo `Path("pos_spj_v13.4/interfaz/menu_lateral.py")` que solo
> existen desde la raíz — con el cwd equivocado esos tests fallaban con
> `FileNotFoundError` disfrazado de fallo funcional. Re-ejecutado desde la
> raíz correcta (`cd pos_spj_v13.4 && python -m pytest pos_spj_v13.4/tests/
> -k "config or settings" --ignore=pos_spj_v13.4/tests/integration
> --ignore=pos_spj_v13.4/tests/ui`, por fuera de la carpeta interna), el
> recuento real es **26 failed / 177 passed** — 19 de los 45 originales
> eran falsos negativos de cwd, no deuda real. La lista corregida de rojos
> genuinos queda abajo.

### Continuación (2026-08-22) — cierra los puntos 1, 2, 3 y 5 pendientes

Usuario repegó el prompt original de "SET-1 — Seguridad" (Permisos /
Alcances / Segregación / Autorización / Secretos / Auditoría / Tests).
Auditado antes de tocar nada: el catálogo de permisos (`CONFIGURACION`/
`DISPOSITIVOS`/`DOCUMENTOS`/`PANTALLA_CLIENTE`, ~62 códigos) ya existía
desde el corte anterior, pero **nada los verificaba en runtime** — ningún
comando del presenter de Configuración llamaba a una policy de
autorización; `mp_access_token` (MercadoPago) seguía en texto plano vía
un segundo lector SQL crudo (`services/mercado_pago_service.py::
_get_token()`), exactamente el gap que el corte anterior había dejado
documentado como pendiente; no existía segregación de funciones para la
aprobación de versiones de plantilla de documento (a diferencia de
`feature_flag_approval_policy`, que sí la tenía desde SET-21); y no había
ninguna auditoría en caliente persistida para Configuración.

- **Autorización (nuevo)**: `backend/application/configuracion/
  authorization.py` — `ConfiguracionAuthorizationPolicy` (`require`/
  `has_permission`/`authorize_exception`) + `PermissionChecker` Protocol +
  `AllowAll`/`DenyAllConfiguracionPermissionCheckerForTests` +
  `SessionPermissionChecker` (adaptador real que envuelve
  `core.session_context.SessionContext.tiene_permiso()` — reusa la MISMA
  infraestructura de grants por sucursal (`rol_permisos`/
  `usuario_permisos`/`usuario_sucursal_permisos`) que ya usa
  `core/permissions.py::verificar_permiso()` en el resto de la app,
  ninguna tabla ni mecanismo nuevo). Mirror exacto del patrón ya
  establecido en `backend/application/inventory/authorization.py`
  (estándar Compras/Inventory, ver memoria `feedback-permissions-compras-
  standard`). `ConfiguracionPresenter` ganó `authorization=None`/
  `audit_log_repository=None` (opcionales — un presenter construido sin
  ellos sigue sin aplicar ningún control, exactamente el comportamiento
  previo, así que ninguno de los ~700 tests existentes se rompió); los 14
  comandos mutadores ahora llaman a `self._authorize(permission_code)`
  antes de invocar su use case (`change_device_status`/
  `change_template_version_status` resuelven el código dinámicamente
  según la acción — p. ej. `BLOCK`/`RETIRE` exige
  `DISPOSITIVOS.deshabilitar`, no el mismo `DISPOSITIVOS.editar` que
  `ACTIVATE`/`DEACTIVATE`). `configuracion_routes.py` (wiring real de
  `main.py`) y `shell_registration.py` (wiring del shell nuevo) ambos
  cablean ahora un `ConfiguracionAuthorizationPolicy` real con
  `SessionPermissionChecker`, más el nuevo repositorio de auditoría.
- **Permisos (extensión)**: `ConfiguracionPermissions` (`backend/
  application/configuracion/permissions.py`) ganó 8 constantes nuevas
  (`DISPOSITIVOS_CREAR/EDITAR/DESHABILITAR`,
  `DOCUMENTOS_PLANTILLA_CREAR/EDITAR/APROBAR/ACTIVAR`) — todas
  referencian códigos que YA existían en el catálogo desde el corte
  anterior, ninguno inventado.
- **Alcances**: resuelto por reuso, no por código nuevo — el alcance de
  una configuración (GLOBAL→EMPRESA→SUCURSAL) ya lo resuelve
  `ConfigurationResolutionService` desde SET-4; el alcance de un permiso
  de usuario (¿en qué sucursal aplica?) ya lo resuelve
  `usuario_sucursal_permisos` vía `SessionContext.tiene_permiso()`
  (soporta wildcard de módulo `"MODULO.*"` desde CRM-29) —
  `SessionPermissionChecker` delega ahí directamente, cero tablas o
  policies nuevas.
- **Segregación (real gap encontrado y cerrado)**:
  `DocumentTemplateVersion.approve()` (SET-11) aceptaba
  `approved_by_user_id` sin comparar contra `created_by_user_id` — quien
  crea una versión podía aprobarse a sí mismo. Nueva excepción
  `TemplateApprovalSegregationError` (`backend/domain/document_output/
  exceptions.py`); el propio `approve()` ahora rechaza cuando
  `approved_by_user_id == created_by_user_id` (si `created_by_user_id`
  es `None` — versión legacy/sin registrar — no hay nada contra qué
  segregar y no bloquea). Mismo criterio que
  `feature_flag_approval_policy.assert_can_approve` (SET-21), aplicado
  esta vez a nivel de entidad porque Document Output no tiene un módulo
  de policies separado para esto. Verificado sin romper los tests de
  integración existentes (`test_configuracion_document_template_use_cases.py`
  ya aprobaba con `actor_user_id` distinto de `created_by_user_id`).
- **Secretos (cierra el gap explícito del corte anterior)**:
  `PaymentProviderSettingsService.mp_access_token` migrado a
  `SecretStoreGateway`, mismo patrón que `EmailSettingsService.
  smtp_password` (`SECRET_NAME`, nunca se persiste en `configuraciones`
  en texto plano). `services/mercado_pago_service.py::_get_token()`
  — el "segundo consumidor con SQL crudo" que el corte anterior dejó
  documentado sin tocar — ahora lee del mismo `SecretStoreGateway` vía
  `build_default_secret_store()`. Sin backfill de filas existentes
  (mismo precedente ya aceptado con `smtp_password`: el valor plano
  queda huérfano en `configuraciones`, nunca más leído; el operador debe
  recapturar el token una vez). `whatsapp_service/webhook/
  mercadopago.py` (verificación de firma HMAC) no se tocó — ya estaba
  resuelto en el corte anterior.
- **Auditoría en caliente (nuevo)**: migración 224
  (`backend/infrastructure/db/schema/configuracion_security_schema.py`)
  crea `configuracion_authorization_log`
  (`AuthorizationGrant` — quién solicitó, quién autorizó, por qué) y
  `configuracion_audit_log` (before/after enmascarado vía
  `sensitive_data_redaction.py::redact_mapping`) — mismo molde ya
  probado por `inventory_authorization_log`/`inventory_audit_log`
  (migración 121), cada bounded context con su propia tabla, nunca
  compartida. `ConfiguracionAuthorizationLogRepository`/
  `ConfiguracionAuditLogRepository` (`backend/infrastructure/db/
  repositories/settings/configuracion_security_repositories.py`).
  Cableado en el presenter para las transiciones que sí están en el
  checklist del corte anterior ("cambio de estado crítico"): bloqueo/
  retiro de dispositivo y aprobación/activación de versión de plantilla.
  Deliberadamente NO se audita edición rutinaria (rename de dispositivo,
  guardado de perfil de empresa/sucursal) — permiso sí, auditoría
  persistida no, mismo límite de alcance que la lista original del plan
  ("rotación de secreto, cambio de impresora fiscal, reimpresión de
  corte Z/boleto, activación de integración crítica"). La rotación de
  secretos (SMTP/MercadoPago) vive en la capa legacy `core/services/` y
  no se cableó a esta tabla nueva en este corte — permanece como hook
  futuro, no se forzó tocar el call site de `modulos/configuracion.py`.
- **Tests**: 39 nuevos, todos verdes — `tests/unit/configuracion/
  test_configuracion_authorization.py` (17: require/has_permission/
  authorize_exception/SessionPermissionChecker), `tests/unit/
  configuracion/test_configuracion_presenter_authorization.py` (8:
  enforcement end-to-end contra el presenter real con use cases falsos —
  incluye el caso "sin policy wireada, cero regresión"), `tests/unit/
  settings/test_configuration_value_objects.py::TestAuthorizationGrant`
  (7), `tests/unit/document_output/
  test_document_template_and_version.py` (3: rechaza mismo usuario,
  permite revisor distinto, permite cuando no hay creador registrado),
  `tests/integration/configuracion/
  test_configuracion_security_repositories.py` (4, contra SQLite
  real/en memoria vía `_born_clean_db.make_db()` — extendido con la
  migración 224). `tests/integration/test_configuracion_use_case_flows.py::
  test_save_smtp_and_payment_provider_flow` actualizado (ya no espera
  `mp_access_token` en texto plano). Suite completa de Configuración
  revalidada: 75 passed (`tests/integration/configuracion` + guardrails
  de arquitectura, era 71), 666 passed (`tests/unit/test_configuracion_
  ui_workspace.py` + `tests/unit/settings` + `tests/unit/document_output`
  + `tests/unit/device_management` combinados) — cero regresiones.
  Verificado además end-to-end contra la factory real
  (`create_configuracion_view()`) con una `SessionContext` real: usuario
  sin el permiso → bloqueado sin tocar el use case; usuario con el
  permiso otorgado vía `set_permisos()` → pasa la autorización y llega
  al use case real.
- **Precaución de entorno (nueva, para sesiones futuras)**: este
  directorio de trabajo tiene un **segundo `.git` anidado** dentro de
  `pos_spj_v13.4/pos_spj_v13.4/` (un clon independiente en la rama
  `main`, distinto del repo real en `claude/erp-financial-bounded-
  context-uqxz6b`). Correr `git stash`/`git stash pop` desde dentro de
  ese subdirectorio opera sobre el clon equivocado y produce un diff de
  miles de archivos sin sentido (nada se pierde en disco — los archivos
  siguen ahí — pero el status resultante es una distracción peligrosa).
  Nunca usar `git stash` en este árbol de trabajo; para descartar una
  hipótesis usar en su lugar una copia/diff manual o un test aislado.
  También confirmado: ejecutar `python <script>.py` que construye un
  widget PyQt5 real (`QWidget`/`QMainWindow`) sin haber creado antes una
  `QApplication` explícita revienta el proceso a nivel de SO (el shell
  reporta código de salida 127, sin traceback) — construir
  `QApplication.instance() or QApplication([])` primero, como ya hacen
  todos los fixtures `app` de los tests con PyQt5.

## Hallazgo importante para la próxima sesión: ya existe un red-test-suite de destino

Al correr la suite de tests de config/settings desde la raíz correcta del
repo (excluyendo los que abren UI Qt real, que crashean con `Windows fatal
exception: access violation` en `modulos/configuracion.py::_cargar_usuarios_v13`
— **crash pre-existente, confirmado independiente de este corte, no
bloqueante para el rebuild pero sí para volver a ejecutar esa suite en
este entorno**), aparecen **26 tests genuinamente en rojo** (no 45 — ver
corrección arriba) que codifican parte del diseño objetivo de este mismo
prompt maestro:

- `tests/architecture/test_configuracion_scope.py::test_configuracion_work_queue_closed_scope_and_selected_identity`.
- `tests/unit/test_configuracion_dtos.py` (2 tests),
  `test_configuracion_refactor_services.py` (6 tests, incl.
  `test_config_repository_requires_uuid_configuration_schema_for_canonical_runtime`
  — espera que `ConfigRepository` **rechace** un esquema legacy con PK
  entera, hoy en cambio revienta con `OperationalError` genérico en vez de
  un error de validación explícito),
  `test_configuracion_transactions.py` (3 tests).
- `tests/test_wa_repositories.py::TestWhatsAppConfigRepository`,
  `TestWhatsAppAdminService` (7 tests).
- `tests/test_printer_service_config_validation.py` (3 tests),
  `tests/test_ticket_layout_repository_regression.py`,
  `tests/test_fase1_uiux_module_guards.py::test_config_hardware_importa_spacing_module_level`,
  `tests/test_loyalty_repository_phase2.py::test_referral_config_and_referrals_and_at_risk_and_birthdays`
  (este último probablemente ajeno a Configuración — capturado solo por el
  filtro `-k`).

Los 19 que resultaron ser falsos negativos de cwd (y por tanto **ya
pasan** hoy, sin necesidad de tocarlos): toda la familia
`tests/architecture/test_settings_module_*.py`,
`test_menu_uses_configured_permissions.py`,
`test_settings_branch_selector_no_default_principal.py`,
`test_settings_dialog_buttons_spanish.py`, `test_settings_header_compact.py`,
`test_settings_ui_tables_actions.py`, `test_page_header_compact.py`,
`test_address_uses_geocoding_service.py::test_configuracion_uses_async_address_autocomplete_component`,
`test_phone_widget_is_standard.py::test_configuracion_uses_phone_widget_for_phones`.
Esto es una noticia mejor de lo que parecía: gran parte del diseño de UI
objetivo (navegación, permisos aplicados al menú, componentes estándar) ya
está implementado y verificado, no pendiente.

Esto confirma lo que ya apuntaba `docs/refactor/modules/configuracion.md`
(iteración `CONFIGURACION-05-MUTATIONS` DONE, `CONFIGURACION-06-DOMAIN_RULES`
como siguiente paso, antes de que ese documento quedara con conflictos de
merge sin resolver): **una sesión previa ya empezó este mismo refactor**
bajo la numeración `CONFIGURACION-NN`, con tests de caracterización ya
escritos contra el diseño objetivo, pero la implementación (`ConfigRepository`,
`SettingsModuleServices`, `modulos/config_hardware.py`, etc.) no los
satisface todavía. **Antes de continuar con SET-2/SET-3 (Configuration
Governance, esquema born-clean)**, la próxima sesión debe:

1. ~~Resolver los marcadores de conflicto de `docs/refactor/modules/configuracion.md`~~
   **Hecho (2026-08-21)** — conflicto resuelto conservando ambas narrativas
   como historial con una nota de reconciliación factual (verificada contra
   el árbol de trabajo actual, no contra lo que cada narrativa afirmaba).
   **Decisión del usuario (2026-08-21):** convención de permisos = dotted
   `MODULE.action`, siguiendo la mayoría del catálogo existente (POS, CRM,
   FINANZAS, PRODUCTOS, COMPRAS), **no** el estilo plano `CASH_*`. **Hecho**
   — registradas 4 claves nuevas en `core/security/permission_catalog.py`:
   `CONFIGURACION` (governance + empresa/sucursal/estación + integraciones +
   feature flags + apariencia), `DISPOSITIVOS`, `DOCUMENTOS`,
   `PANTALLA_CLIENTE`. Aditivo puro: los 3 stubs legacy
   (`CONFIG_HARDWARE`/`CONFIG_MODULOS`/`CONFIG_SEGURIDAD`) que
   `interfaz/menu_lateral.py` sigue usando **no se tocaron** — la
   navegación unificada de §14 del prompt maestro es un paso de UI
   posterior, no parte de este corte. Cobertura:
   `tests/architecture/test_settings_permission_catalog.py` (8 tests,
   verde). Verificado sin regresión contra
   `test_permission_catalog_matches_menu_modules.py`,
   `test_permission_matrix_uses_catalog.py`,
   `test_permission_matrix_catalog_first.py` (el único fallo observado en
   la suite de arquitectura, `test_no_raw_sqlite_connect_outside_pool`
   sobre `tools/crm/backfill_legacy_customers.py`, es preexistente y ajeno
   a Configuración/permisos).
2. Decidir si esta iniciativa (`SET-*`, alcance ampliado a Device
   Management/Document Output/Customer Display por el nuevo prompt
   maestro) **continúa** la numeración `CONFIGURACION-NN` ya iniciada o la
   **reemplaza** formalmente — no mantener las dos numeraciones vivas en
   paralelo.
3. Usar estos 26 tests rojos genuinos (no 45 — ver corrección arriba) como
   parte del contrato de aceptación de SET-2 en vez de escribir
   characterization tests nuevos desde cero. **Siempre correr la suite
   desde la raíz del repo** (`cd pos_spj_v13.4`, no
   `cd pos_spj_v13.4/pos_spj_v13.4`) para evitar falsos negativos de cwd.
4. Migración de secretos (SET-1, punto 3): **hecho para `smtp_password`**
   — `EmailSettingsService` ahora enruta la contraseña SMTP a través del
   `SecretStoreGateway` ya construido (`backend/security/secrets/`, vía el
   nuevo factory compartido `backend/security/secrets/default_secret_store.py::build_default_secret_store()`,
   reusado también por `backend/bootstrap/wiring/shared_wiring.py` para no
   duplicar la selección de plataforma Windows Credential Manager ↔
   encrypted-local). El campo ya no se guarda en la tabla `configuraciones`
   en texto plano; la UI (`modulos/configuracion.py`) sigue funcionando
   exactamente igual (mismo contrato `get_settings()`/`save_settings()`,
   `SettingsModuleServices.from_connection()` inyecta el secret store por
   default sin cambios en el call site). **Pendiente, explícitamente
   fuera de alcance de este corte**: `mp_access_token` (MercadoPago) tiene
   un **segundo consumidor con SQL crudo** — `services/mercado_pago_service.py::_get_token()`
   lee `configuraciones` directo, fuera de `PaymentProviderSettingsService`
   — migrarlo requiere actualizar ese lector también, no solo el servicio
   de guardado; se deja documentado para no mezclarlo con este corte ya
   verificado. También pendiente: `email_config.smtp_pass` — tabla
   **huérfana**, confirmado que ningún código escribe en ella
   (`grep -rn "INSERT INTO email_config\|UPDATE email_config"` → 0
   resultados); `core/services/reporte_email_service.py` (reportes
   programados por email) la lee pero siempre encuentra la tabla vacía, por
   lo que `enviar_reporte_diario()` es efectivamente no-op hoy. No se tocó
   en este corte — decidir en SET-11 (Document Output/Notifications) si se
   revive sobre el mismo `SecretStoreGateway` o se elimina como legacy
   muerto.

## Avance SET-2 — Configuration Governance (dominio puro)

**Hecho** — `backend/domain/settings/` completo, siguiendo el molde ya
establecido por `backend/domain/crm/` y `backend/domain/cash_register/configuration.py`
(dataclasses `slots=True`, `.create()` con validación + `new_uuid()`,
`repository_ports.py` con Protocols, `events.py` con constantes + payload
builder). Cero dependencias de framework/UI/infraestructura — no hay
todavía persistencia (eso es SET-3, esquema born-clean).

- `enums.py` — `ValueType` (18 tipos de §8), `ScopeType` (16 ámbitos de
  §6, con `CODE_BASED_SCOPES` para MODULE/CHANNEL/PROCESS que no son
  UUIDv7), `ConfigurationValueStatus` (9 estados de §10).
- `value_objects/` — `ConfigurationKey` (formato `modulo.parametro`),
  `ConfigurationScope` (GLOBAL sin id; el resto exige UUIDv7 salvo los
  ámbitos por código), `EffectivePeriod` (vigencia tz-aware, mismo patrón
  que `backend/domain/cash_register/configuration.py`), `VersionNumber`,
  y `configuration_value_object.py` con `validate_type_shape()` — una
  forma Python por `ValueType` (Decimal para DECIMAL/MONEY/PERCENT, nunca
  float; `COLOR_TOKEN` **rechaza literales hex** y exige un token con
  puntos, aplicando §51 directo en el dominio).
- `entities/` — `ConfigurationDefinition.create()` (valida
  allowed_scopes no vacío, default_scope ⊆ allowed_scopes, ENUM/MULTI_ENUM
  exigen allowed_values, default_value tipado); `ConfigurationValue` con
  máquina de estados completa (`submit_for_approval`/`approve`/`auto_approve`/
  `reject`/`cancel`/`activate`/`expire`/`mark_rolled_back`) y
  `create_next_version()` — un cambio nunca edita una fila ACTIVE in-place,
  siempre encadena una nueva vía `previous_version_id` (§10-11, §63).
- `policies/` — `configuration_validation_policy` (compone type-shape +
  allowed_values + `validation_schema` con `min`/`max`/`min_length`/
  `max_length`/`pattern` — deliberadamente no es JSON-Schema completo, ver
  su docstring), `configuration_inheritance_policy` (orden de
  especificidad por defecto, más específico primero, GLOBAL al final —
  ver `DEFAULT_SPECIFICITY_ORDER`), `configuration_approval_policy` y
  `configuration_activation_policy` (segregación de funciones §59-60:
  quien crea no aprueba, quien aprueba una definición `approval_required`
  no activa sola), `configuration_rollback_policy` (`build_rollback_draft`
  marca la versión actual ROLLED_BACK y devuelve un DRAFT nuevo con el
  valor anterior, nunca resucita la fila vieja), `sensitive_configuration_policy`
  (`mask_for_display`/`assert_can_view_raw` — nunca toca el secreto crudo,
  solo el nombre de referencia hacia `SecretStoreGateway`).
- `services/configuration_resolution_service.py` — `ConfigurationResolutionService.resolve()`
  recibe una lista de `ConfigurationValue` candidatas ya obtenidas (el
  repositorio/QueryService las trae, en un SET posterior) más un
  `ScopeContext` (ids concretos del ámbito actual) y camina la cadena de
  herencia; cae al `default_value` de la definición si nada aplica; lanza
  `ConfigurationValueNotFoundError` si tampoco hay default.
- `repository_ports.py`, `events.py`, `exceptions.py` — Protocols sin
  implementación (SET-3), 11 eventos canónicos + `build_event_payload()`,
  8 excepciones de dominio (`ConfigurationDefinitionNotFoundError` …
  `SensitiveConfigurationAccessDeniedError`).
- **Tests**: `tests/unit/settings/` — 93 tests, verdes (value objects,
  ambas entidades, las 6 policies, el servicio de resolución con casos de
  herencia multi-nivel, expiración y aislamiento entre definiciones).
  Verificado con `pytest tests/unit/settings/ -v` (93 passed) y sintaxis
  global limpia (`pos_spj_v13.4` + `whatsapp_service`).

**Pendiente tras SET-3**: `ConfigurationCache` con invalidación por evento
(§55), wiring a `EventBus` (los eventos de `events.py` existen pero nada
los publica todavía — eso es capa de aplicación, un SET posterior), y el
primer consumidor real (probablemente `CompanyProfile`/`BranchProfile`/
`Workstation` de SET-5/SET-6, o migrar `hardware_config` a este modelo en
SET-7).

## Avance SET-3 — Esquema born-clean + repositorios de infraestructura

**Hecho** — persistencia real para el dominio de SET-2, ver
`migrations/MIGRATION_LOG.md` (entrada `208_settings_configuration_governance_schema`)
para el detalle completo. Resumen:

- Migración `migrations/standalone/208_settings_configuration_governance_schema.py`
  (registrada en `migrations/engine.py`), DDL en
  `backend/infrastructure/db/schema/settings_schema.py`:
  `configuration_definitions` + `configuration_values`, `CHECK` de UUIDv7
  en cada PK, `CHECK IN (...)` para `value_type`/`scope_type`/`status`,
  índice único `(definition_id, scope_type, COALESCE(scope_id,''), version)`
  y único parcial `(operation_id) WHERE operation_id IS NOT NULL`.
- Repositorios `backend/infrastructure/db/repositories/settings/`
  (`SqliteConfigurationDefinitionRepository`, `SqliteConfigurationValueRepository`,
  `value_serialization.py`) implementando los Protocols de SET-2's
  `repository_ports.py` sin modificarlos.
- Alcance deliberadamente acotado a lo que SET-2 ya definió
  (`ConfigurationDefinition`/`ConfigurationValue`) — **no** incluye
  `device_*`/`document_*`/`customer_display_*` del enunciado original de
  SET-3 en la tabla de fases; esos llegan con SET-7/SET-11/SET-17 cuando
  sus dominios respectivos existan.
- **Tests**: `tests/integration/settings/test_configuration_repositories.py`
  (32 tests contra SQLite real en memoria vía el fixture born-clean
  compartido) + los 93 de SET-2 = **125 tests verdes**. Cubre: round-trip
  exacto de los 19 `ValueType` (Decimal nunca float, datetime tz-aware,
  MULTI_ENUM como tupla, JSON_SCHEMA como dict), rechazo de
  `operation_id`/`(definition,scope,version)` duplicados vía
  `sqlite3.IntegrityError`, `create_next_version()` persistiendo como fila
  nueva encadenada, y resolución de herencia end-to-end leyendo de
  repositorios reales (no solo listas en memoria como en SET-2).
- `tests/integration/_born_clean_db.py` (fixture compartido de DB en
  memoria) actualizado con la migración 208.

**Nota honesta sobre guardrails de arquitectura**: al correr
`pytest tests/architecture/ -k "no_raw_sqlite or migration or schema or engine"`
tras SET-3, 4 tests fallan — los 4 son **preexistentes, confirmados
independientes de este corte**:
`test_clean_birth_guardrails.py::test_services_repositories_ui_do_not_create_schema`
y `test_no_schema_changes_outside_migrations.py::test_no_create_or_alter_table_outside_migrations`
ya listaban **20+ archivos** `backend/infrastructure/db/schema/*_schema.py`
existentes (`authentication_schema.py`, `crm_schema.py`, `finance_schema.py`,
`sales_schema.py`, `inventory_schema.py`, ...) como violaciones antes de
que `settings_schema.py` existiera — es decir, el patrón "DDL en un
módulo `backend/infrastructure/db/schema/*.py`, invocado solo por su
migración" que este mismo documento (y `207_authentication_schema.py`,
que sirvió de molde) sigue **ya está en rojo en todo el repo**, no es
un patrón nuevo que yo haya introducido. `settings_schema.py` se sumó a
una lista ya larga, no creó una categoría de fallo nueva. `test_no_raw_sqlite_connect_outside_pool`
(`tools/crm/backfill_legacy_customers.py`) y
`test_expiry_damage_contract.py::test_loss10_schema_and_inventory_boundary_are_explicit`
(módulo Losses, sin relación con Settings) también preexistían. Arreglar
esos guardrails es trabajo separado, de alcance repo-wide, no de SET-3.

## Avance SET-4 — Herencia y resolución: Scopes, Fallback, Overrides, Cache, Tests

**Hecho**. Scopes/Fallback ya tenían su núcleo en SET-2/SET-3
(`ConfigurationScope`, `resolution_order()`, `ConfigurationResolutionService`,
probados end-to-end contra repositorios reales) — SET-4 cierra lo que
faltaba: **Overrides** (nunca aplicado hasta ahora) y **Cache** (nuevo).

- **Overrides** — `policies/configuration_inheritance_policy.py` gana
  `canonical_override_scope(definition)` (el `default_scope` de la
  definición, o GLOBAL si no tiene uno) y `assert_override_allowed(definition, scope_type)`:
  cuando `override_allowed=False`, solo el ámbito canónico puede tener un
  valor propio — ningún BRANCH/WORKSTATION/etc. puede sobreescribir.
  Deliberadamente independiente de `inheritance_enabled` (uno gobierna
  *dónde puede escribirse* un valor; el otro gobierna *cómo cae* la
  resolución en lectura) — un test explícito (`test_is_independent_of_inheritance_enabled`)
  deja esa distinción en el contrato, no solo en el docstring.
- **Cache** — `services/configuration_cache_service.py`:
  `ConfigurationCache` + `ConfigurationCacheKey` (compuesta de
  `definition_id` + firma del `ScopeContext`, insensible al orden de
  inserción del dict). Invalidación **siempre por evento, nunca por TTL**
  (§55, "no cachés eternas sin versión"): `ACTIVATED`/`SCHEDULED`/
  `EXPIRED`/`ROLLED_BACK` invalidan todo lo cacheado de esa `definition_id`
  (una activación en BRANCH puede cambiar lo que resuelve un WORKSTATION
  hijo por fallback, así que se invalida la definición completa, no solo
  el scope exacto que cambió); `CACHE_INVALIDATED` soporta invalidación
  total o dirigida. Deliberadamente **compuesto, no heredado**:
  `ConfigurationCache` no envuelve ni reemplaza
  `ConfigurationResolutionService` (que sigue puro/sin estado) — el patrón
  de uso (cache-check → resolve-on-miss → cache-put → invalidate-on-event)
  queda documentado como test de composición
  (`TestCacheResolutionComposition`), listo para que la futura
  QueryService de aplicación lo replique.
- **Tests nuevos**: `test_configuration_overrides_policy.py` (6),
  `test_configuration_cache_service.py` (17), más 4 casos nuevos
  añadidos a `test_configuration_resolution_service.py` (scope presente en
  el contexto pero fuera de `allowed_scopes` → ignorado; empate entre dos
  candidatos ACTIVE en el mismo ámbito → gana el `effective_from` más
  reciente; herencia deshabilitada probada end-to-end contra el
  servicio completo, no solo contra `resolution_order()` aislado). Total:
  **151 tests verdes** para Configuration Governance
  (`pytest tests/unit/settings/ tests/integration/settings/`).
- Wiring real a `EventBus` (para que `ConfigurationCache.handle_event`
  reciba eventos de verdad en vez de llamadas directas en tests) sigue
  siendo trabajo de capa de aplicación — no hay `EventBus`/casos de uso
  para Configuración todavía; eso llega con la primera SET que construya
  `application/settings/`.

## Avance SET-5 — Empresa y sucursales

**Hecho** — ver `migrations/MIGRATION_LOG.md` (entrada
`209_settings_company_branch_profile_schema`) para el detalle completo.
Resumen:

- **`CompanyProfile`** (`backend/domain/settings/entities/company_profile.py`) —
  genuinely nuevo (§0 del inventario ya había confirmado que no existe
  tabla "empresa" en el schema legacy). Valida `default_currency` (ISO
  4217, 3 letras), `default_locale` (forma `xx-XX`), email/website con
  regex ligero; `logo_asset` usa el nuevo VO `AssetReference` (§15: "no
  almacenar logos como rutas arbitrarias") en vez de un string de ruta.
  Sin restricción de singleton en el dominio — "multiempresa futuro" del
  prompt maestro queda abierto, la aplicación decide cuántas usar.
- **`BranchProfile`** (`backend/domain/settings/entities/branch_profile.py`) —
  **decisión de alcance explícita, no un simple checkbox**: no reemplaza
  `sucursales` (identidad viva referenciada por FK desde ventas,
  inventario, caja, RRHH y ~15 contextos más — cortarla es una migración
  cross-cutting dedicada, no parte de un SET de Configuración).
  `BranchProfile.id` **es** el mismo UUIDv7 que `sucursales.id`
  (`branch_id` es una FK 1:1, no una segunda identidad) y aporta
  exactamente los campos que `sucursales` nunca tuvo: `ticket_header`/
  `ticket_footer`, `social_links`, `map_reference` (nuevo VO, coordenadas
  Decimal + `place_id`, sin integración de geocoding real — eso es
  Integraciones, un SET posterior), `warehouse_ids`,
  `default_workstation_profile_id`. "Las sucursales pueden sobreescribir
  configuraciones permitidas" (§16) **no** es un campo de `BranchProfile`
  — es simplemente un `ConfigurationValue` en `ScopeType.BRANCH` con el
  mismo id (SET-2/SET-4 ya lo soportan).
- Nuevos VOs: `AssetReference` (referencia UUIDv7, nunca una ruta),
  `MapReference` (Decimal lat/lng validado en rango, nunca float).
- Migración `209_settings_company_branch_profile_schema` (DDL en
  `create_company_branch_profile_schema`, función separada de la 208 a
  propósito — modificar una migración ya "cerrada" no es seguro una vez
  que corrió en una instalación real). Repositorios
  `SqliteCompanyProfileRepository`/`SqliteBranchProfileRepository`.
- **Tests**: `test_company_and_branch_profile_entities.py` (dominio) +
  `test_company_and_branch_profile_repositories.py` (infraestructura,
  incluida la verificación de que `branch_id` sin `sucursales`
  correspondiente falla con `IntegrityError`, y que `code` es único).
  Un caso reveló que `id == branch_id` siempre hace que `save()` (upsert
  por `id`) nunca pueda colisionar por `branch_id` — el test se corrigió
  para afirmar el upsert real en vez de una colisión inalcanzable; se
  dejó documentado en el propio test para que nadie la reintroduzca por
  error. **Total tras SET-5: 205 tests verdes.**

## Avance SET-6 — Estaciones

**Hecho** — ver `migrations/MIGRATION_LOG.md` (entrada
`210_settings_workstation_schema`) para el detalle completo. Resumen:

- **`Workstation`** (`backend/domain/settings/entities/workstation.py`) —
  11 tipos y 5 estados de §17. Los 5 estados
  (`ACTIVE/INACTIVE/MAINTENANCE/BLOCKED/RETIRED`) se reutilizaron
  **exactamente** de `cash_registers`/`pos_terminals`
  (`migrations/standalone/175_cash_register_bounded_context_schema.py`) —
  mismo vocabulario de ciclo de vida de hardware/estación en todo el
  repo, no un tercer conjunto de nombres.
- **Registro** — `Workstation.create()` + `check_in()`: el heartbeat
  periódico que una estación real reportaría, actualiza `last_seen_at` y
  opcionalmente `application_version`; rechazado desde BLOCKED/RETIRED
  (una estación bloqueada o retirada no puede "seguir viva").
  Deliberadamente **no** es un evento de dominio por llamada (un
  heartbeat cada pocos segundos generando un evento sería ruido) — los
  eventos cubren cambios de estado, no cada latido.
- **Estado** — máquina completa: `activate()`/`deactivate()`/
  `enter_maintenance()`/`exit_maintenance()`/`block(reason)`/`unblock()`/
  `retire()`. RETIRED es terminal (ninguna transición sale de ahí,
  probado explícitamente incluyendo el intento de retirar dos veces).
- **Versión** — `application_version` se actualiza vía `check_in()`, no
  por un setter directo — siempre va de la mano de "la estación reportó
  actividad", nunca se edita a mano sin evidencia de que la estación
  corrió esa versión.
- **Offline** — `offline_enabled` (toggle) + `is_online(at, staleness_threshold)`:
  el dominio nunca decide un umbral de "cuánto es demasiado" por su
  cuenta — eso lo define quien llama (una futura `ConfigurationValue` en
  `ScopeType.GLOBAL`/`BRANCH`, coherente con §53's "políticas offline son
  gobernadas por Configuración, no hardcodeadas").
- Migración `210_settings_workstation_schema` (separada de 208/209/210
  a propósito, mismo razonamiento que las anteriores). `branch_id` FK a
  `sucursales(id)` — una estación siempre pertenece a una sucursal ya
  existente, mismo patrón que `branch_profiles`.
- **Tests**: `test_workstation_entity.py` (máquina de estados, registro,
  is_online) + `test_workstation_repository.py` (persistencia real, FK,
  unicidad de `code`, `list_by_branch`/`list_active`). **Total tras
  SET-6: 235 tests verdes.**

### Continuación (2026-08-22) — "General" pasa de solo-lectura a CRUD real

Usuario pidió "set-6" — mismo patrón que Dispositivos/Documentos/Empresa:
el dominio (`Workstation`, arriba) ya estaba completo desde el corte
original, pero la sección "General" de la UI de Configuración solo
listaba estaciones activas, sin ninguna acción de escritura. Se convierte
en la **6ª sección con CRUD real** (de 10 secciones totales — Feature
Flags, Apariencia, Dispositivos, Documentos, Empresa y sucursales,
General).

- **Gap real de dominio encontrado y cerrado**: `Workstation` tenía
  `check_in()`/`set_offline_enabled()` pero ninguna forma de editar
  `name`/`device_identifier`/`operating_system` tras el registro — se
  agregó `update_details()`, mismo precedente que
  `Device.rename()`/`update_notes()` y `CompanyProfile.update_identity()`.
  Funciona desde cualquier estado (editar datos descriptivos no es una
  transición de ciclo de vida).
- `WorkstationRepositoryPort`/`SqliteWorkstationRepository` ganaron
  `list_all()` — la vista de gestión necesita ver y actuar sobre
  estaciones bloqueadas/inactivas/retiradas, no solo `list_active()`,
  mismo cambio que Dispositivos.
- Nuevo `backend/application/use_cases/configuracion/
  workstation_use_cases.py`: `RegisterWorkstationUseCase`,
  `UpdateWorkstationUseCase`, `ChangeWorkstationStatusUseCase` (UNA clase
  para las 7 transiciones vía `WorkstationStatusAction`, mismo molde que
  `ChangeDeviceStatusUseCase`).
- `ConfiguracionWorkspaceQueryService._page_general` cambiado a
  `list_all()` (antes `list_active()`); nuevo `get_workstation()` +
  `WorkstationDetailViewModel`.
- Permisos: reutilizados los 5 códigos ya registrados
  (`estacion.ver/crear/editar/bloquear/retirar`) — ninguno inventado.
  Cableados en `ConfiguracionAuthorizationPolicy` vía el presenter:
  BLOCK→`estacion.bloquear`, RETIRE→`estacion.retirar`, el resto
  (ACTIVATE/DEACTIVATE/ENTER_MAINTENANCE/EXIT_MAINTENANCE/UNBLOCK)→
  `estacion.editar`. Auditoría en caliente (migración 224, SET-1) para
  BLOCK/RETIRE únicamente, mismo límite de alcance que Dispositivos.
- Nueva `pages/estaciones_page.py` (conserva el nombre de clase
  `GeneralPage`/`page_id="config_general"` — el placeholder genérico que
  reemplaza, la entrada del sidebar sigue llamándose "General") + 9
  botones de acción + `dialogs/workstation_dialogs.py`
  (`WorkstationCreateDialog`/`WorkstationEditDialog`/
  `BlockWorkstationDialog`).
- Cableado en los 3 puntos: presenter, `configuracion_routes.py` (app
  real), `shell_registration.py`.
- Verificado end-to-end contra la factory real con SQLite real: registrar
  → editar → mantenimiento → salir de mantenimiento → bloquear → retirar
  (retirar desde bloqueado SÍ está permitido — RETIRED es alcanzable
  desde cualquier estado no-terminal, confirmado correcto contra el
  propio diagrama de la entidad) → confirmado que un usuario sin el
  permiso `estacion.crear` es bloqueado ANTES de tocar el use case →
  confirmado que el audit log solo registra BLOCK/RETIRE, no
  mantenimiento/desbloqueo. Tests: 91 nuevos (unit + integración), todos
  verdes; suite completa revalidada sin regresiones (37 widgets PyQt5 en
  este archivo, era 31; 639 en settings+document_output+device_management
  combinados). **Siguiente**: 4 secciones aún de solo lectura (Pantalla
  del cliente, Integraciones, Notificaciones, Offline) de 10 totales
  (6 con CRUD real: Empresa y sucursales, General, Dispositivos,
  Documentos, Feature Flags, Apariencia); §65-68 Resumen dashboard y §70
  clasificación formal de legacy siguen abiertos.

## Avance SET-7 — Device Management

**Hecho** — primer bounded context nuevo fuera de
`backend/domain/settings/`: `backend/domain/device_management/`. Ver
`migrations/MIGRATION_LOG.md` (entrada `211_device_management_schema`)
para el detalle completo. Resumen:

- **Decisión de alcance explícita (misma lógica que SET-5/`sucursales`)**:
  esta SET **no reemplaza `hardware_config`** — esa tabla legacy (PK en
  `tipo` solo, sin ámbito real de sucursal/estación, ver auditoría SET-0)
  sigue siendo lo que `core/services/hardware_service.py`,
  `modulos/config_hardware.py` y `hardware/*.py` leen hoy. Cortar esos
  consumidores hacia el modelo nuevo es trabajo de SET-8 (impresoras),
  SET-9 (básculas/lectores) y SET-10 (cajones/terminales)
  específicamente — no de este corte fundacional de Devices/Profiles/
  Assignments/Capabilities.
- **Devices** (`entities/device.py`) — instancia concreta de hardware,
  máquina de estados **idéntica en forma** a `Workstation`
  (`backend/domain/settings/entities/workstation.py`) — mismos 5 estados,
  mismas transiciones, RETIRED terminal — definida de forma independiente
  (no importada) para no crear una dependencia `device_management` →
  `settings`.
- **Profiles** (`entities/device_profile.py`) — la plantilla de conexión/
  capacidades reutilizable que uno o más `Device` referencian.
  `ConnectionProfile` (VO) exige `SerialPortProfile` tipado para SERIAL o
  `NetworkEndpoint` tipado para NETWORK/HTTP/WEBSOCKET — nunca un dict
  genérico sin validar (§18-19). **§19 aplicado en el dominio, no solo
  documentado**: `ConnectionProfile.create()` rechaza cualquier
  `extra_parameters` cuya clave tenga apariencia de secreto
  (`password`/`token`/`secret`/`credential`/`apikey`/`private_key`/
  `auth*`) — probado con 6 variantes de clave incluida mezcla de
  mayúsculas. La única vía legítima para una credencial es
  `credential_reference`, un nombre hacia `SecretStoreGateway`
  (`backend/security/secrets/`, ya construido en SET-1), nunca el secreto
  crudo.
- **Capabilities** — `DeviceCapability` (VO: `code` + `parameters`
  opcionales, p. ej. `WEIGH` con `{"max_weight_kg": "30"}`) en vez de una
  entidad con tabla propia — los 20 códigos de `DeviceCapabilityCode`
  cubren los 8 de impresora de §23 (cut/drawer_pulse/qr/barcode/image/
  unicode/color/duplex) más los implicados por el resto de tipos de
  dispositivo de §18 (báscula, escáner, cajón, terminal, pantalla,
  sensor). Desviación deliberada del layout de §12.3 (que sugiere
  `entities/device_capability.py`) — una capacidad no tiene ciclo de vida
  propio, es un atributo tipado del perfil, documentado como tal en el
  propio VO.
- **Assignments** (`entities/workstation_device_assignment.py` +
  `policies/device_assignment_policy.py`) — `assign()`/`unassign()`, más
  `assert_role_compatible_with_device_type()` (los 11 roles de §20
  mapeados a los tipos de dispositivo que legítimamente pueden cumplirlos
  — p. ej. `LABEL_PRINTER` como rol nunca acepta un `THERMAL_PRINTER` como
  dispositivo, aunque ambos "impriman"). El conflicto real —dos
  dispositivos activos en el mismo rol de la misma estación— se impide en
  schema (índice único parcial `(workstation_id, role) WHERE active=1`,
  §62), no solo en el dominio; probado en integración: segundo intento
  falla con `IntegrityError`, y tras `unassign()` la reasignación a otro
  dispositivo funciona.
- Migración `211_device_management_schema` — `devices.branch_id` FK a
  `sucursales`, `devices.profile_id` FK a `device_profiles`,
  `workstation_device_assignments.workstation_id` FK a `workstations`
  (migración 210) — esta migración depende del schema de Settings, nunca
  al revés.
- **Tests**: `tests/unit/device_management/` (perfil+VOs de conexión,
  entidad Device, asignación+política de roles) +
  `tests/integration/device_management/` (persistencia real NETWORK y
  SERIAL, las 3 FKs, unicidad de `code`, conflicto de asignación activa).
  **Total tras SET-7 (Settings + Device Management): 312 tests verdes.**

### Continuación (2026-08-22) — "Asignaciones" cierra el 4º pilar de SET-7

Usuario pidió "SET-7". Auditado antes de construir: de los 4 pilares del
corte original (Devices/Profiles/Capabilities/Assignments), el round de
Dispositivos (SET-25 follow-up #2) ya había cerrado Devices y Profiles
con CRUD real; Capabilities no necesita UI propia (es un atributo
tipado del perfil, no una entidad con ciclo de vida — ver arriba); pero
**Assignments** (`WorkstationDeviceAssignment` — qué dispositivo cumple
qué rol en qué estación) seguía sin ninguna UI ni caso de uso, pese a
tener dominio, política de compatibilidad de roles, repositorio y
constraint de esquema completos desde el corte original. Se decide
colocar la acción en la página de Estaciones (General), no en
Dispositivos — una asignación es inherentemente estación-céntrica (una
estación cubre varios roles: impresora de recibo, báscula, cajón,
etc.), mismo patrón de tabla secundaria por selección que Documentos
usa para Versiones.

- **Sin gaps de dominio** — `WorkstationDeviceAssignment.assign()`/
  `unassign()` y `device_assignment_policy.
  assert_role_compatible_with_device_type()` ya estaban completos;
  `DeviceAssignmentConflictError` ya existía en el dominio, sin usar
  hasta ahora — confirma que el propio autor original ya había previsto
  este caso exacto ("a lo sumo un dispositivo activo por rol") y dejó el
  error listo para cuando se construyera el caso de uso. Se agregó
  únicamente `DeviceAssignmentNotFoundError` (para `unassign()` con un
  id inexistente), mismo patrón sibling que `DeviceNotFoundError`/
  `DeviceProfileNotFoundError`.
- Nuevo `backend/application/use_cases/configuracion/
  device_assignment_use_cases.py`: `AssignDeviceUseCase` (valida
  compatibilidad rol↔tipo, verifica que el rol no esté ya ocupado antes
  de insertar — nunca deja que el `IntegrityError` del índice único
  parcial llegue a la UI) y `UnassignDeviceUseCase`. Reasignar un rol
  requiere desasignar primero explícitamente (dos acciones, no un swap
  silencioso) — decisión deliberada para que quede claro qué dispositivo
  dejó de cumplir el rol, no solo cuál lo cumple ahora.
- `ConfiguracionWorkspaceQueryService` ganó `list_devices()` (dispositivos
  activos con su tipo, vía join con `DeviceProfile` — `Device` no
  guarda el tipo directamente) y `list_workstation_assignments(workstation_id)`.
- Permiso reutilizado: `DISPOSITIVOS.asignar` (ya registrado en el
  catálogo desde SET-1, sin usar hasta ahora). Ambas acciones
  (asignar/desasignar) quedan **siempre** auditadas en
  `configuracion_audit_log` (a diferencia de dispositivos/estaciones,
  donde solo bloquear/retirar se audita) — una asignación equivocada
  puede enrutar mal un documento fiscal, mismo espíritu que "cambio de
  impresora fiscal" en el checklist de auditoría original de SET-1.
- `pages/estaciones_page.py` gana una tarjeta "Dispositivos asignados"
  (tabla secundaria recargada al seleccionar una estación) +
  `dialogs/device_assignment_dialogs.py::AssignDeviceDialog` (selector
  de rol de los 11 valores de §20 + selector de dispositivo).
- Verificado end-to-end contra la factory real: asignar impresora al rol
  PRIMARY_RECEIPT_PRINTER → confirmado que un segundo intento al mismo
  rol falla con `DeviceAssignmentConflictError` (mensaje claro, no
  `IntegrityError` crudo) → confirmado que asignar una impresora al rol
  SCALE falla por incompatibilidad de tipo → desasignar → reasignar al
  rol ahora libre funciona → confirmado que un usuario sin
  `DISPOSITIVOS.asignar` es bloqueado antes del use case → confirmado
  que el audit log registra tanto ASSIGN como UNASSIGN. Tests: 20 nuevos
  (unit + integración), todos verdes; regresión completa limpia (97 en
  `tests/integration/configuracion` + guardrails de arquitectura, era 87;
  424 en settings+document_output; 248 en device_management, sin
  regresiones en ninguno). **Siguiente**: 4 secciones aún
  de solo lectura (Pantalla del cliente, Integraciones, Notificaciones,
  Offline); §65-68 Resumen dashboard y §70 clasificación formal de
  legacy siguen abiertos. SET-8/9/10 (impresoras/básculas/cajones)
  todavía no tienen UI de "pruebas" de conexión — deliberadamente fuera
  de este corte, ya que requieren gateways de hardware reales que este
  repo aún no implementa (solo Protocols/stubs).

## Avance SET-8 — Impresoras: perfiles, routing, failover, test

**Hecho** — extiende `backend/domain/device_management/` (SET-7) con lo
específico de impresión (§21, §23, §25). Ver `migrations/MIGRATION_LOG.md`
(entrada `212_print_routing_schema`) para el detalle completo. Resumen:

- **Perfiles** — `DeviceProfile` (SET-7) no se modificó; se agregó
  `policies/printer_profile_policy.py::assert_valid_printer_profile()`
  como validación adicional solo para perfiles de impresora: `paper_profile`
  debe ser uno de los 8 valores canónicos de §23
  (`PAPER_58MM`/`PAPER_80MM`/`A4`/`LETTER`/`LABEL`/`CARD`/`PDF`/`VIRTUAL`)
  y `protocol` uno de 6 protocolos reconocidos
  (`ESC_POS`/`ZPL`/`PDF`/`HTML`/`RAW`/`VIRTUAL`) — "no asumir que toda
  impresora es ESC/POS" (§23) aplicado en código, no solo documentado;
  probado con los 13 tipos de dispositivo (9 no-impresora rechazados
  explícitamente, uno por tipo) y con un protocolo inventado rechazado.
- **Routing** — `PrintRoute` (`document_type` + `primary_device_id` +
  `fallback_device_ids`, ámbito opcional empresa/sucursal/estación/
  módulo/canal por §25) y
  `policies/print_routing_policy.py::resolve_route()`, que elige la ruta
  activa más específica que coincide (mismo principio "más específico
  gana" que `ConfigurationResolutionService` de SET-2/4, reimplementado
  de forma independiente — las dimensiones de ruteo no son la misma
  jerarquía de ámbitos de Configuración). `document_type` es un string
  libre validado, deliberadamente **no** un enum importado de
  `document_output` (SET-11 no existe todavía) — evita acoplar
  `device_management` a un bounded context que aún no se ha construido.
- **Failover** — `select_device()` recorre primary→fallback y devuelve el
  primer dispositivo para el que la función `is_available` (inyectada por
  quien llama, nunca resuelta aquí con hardware real) responda true;
  devuelve `DeviceSelection` con `used_failover` explícito — para que
  "tuvimos que usar el respaldo" sea un hecho observable/registrable, no
  un detalle interno perdido.
- **Test** — `PrinterTestResult`: registro histórico append-only
  (éxito/fallo, mensaje, quién, cuándo) de pruebas de impresión bajo
  demanda. Deliberadamente acotado a impresoras (no un
  `DeviceHealthCheck`/`DeviceDiagnosticSession` universal de §21 para
  todo tipo de dispositivo) — cada SET de hardware específico
  (básculas/lectores en SET-9, cajones/terminales en SET-10) construye su
  propio registro de prueba acotado, en vez de una infraestructura de
  diagnóstico prematura y genérica antes de que exista un segundo caso de
  uso real que la justifique.
- Migración `212_print_routing_schema` (separada de 211, mismo
  razonamiento de siempre). Índice único por `(document_type, ámbito
  exacto)` impide rutas duplicadas — probado: mismo ámbito exacto choca,
  mismo `document_type` en sucursales distintas no choca.
- **Tests**: `test_printer_profile_policy.py`,
  `test_print_route_and_routing_policy.py`,
  `test_printer_test_result_entity.py` (dominio) +
  `test_print_routing_repositories.py` (infraestructura — incluida la
  resolución de ruta y selección con failover contra rutas/dispositivos
  reales leídos de SQLite, no solo listas en memoria). **Total tras SET-8
  (Settings + Device Management): 365 tests verdes.**

### Continuación (2026-08-22) — "Perfiles" completado + "Rutas de impresión" (Routing/Failover) con UI real

Usuario pidió "SET-8". Auditado antes de construir: de los 4 pilares
(Perfiles/Routing/Failover/Test), "Perfiles" tenía la política de
validación (`printer_profile_policy.py`) construida desde el corte
original pero **nunca conectada** — `RegisterDeviceProfileUseCase` (del
round de Dispositivos) ni siquiera aceptaba `paper_profile`/`protocol`/
`driver_name` como parámetros, y el diálogo de creación de perfil no
tenía esos campos; "Routing"/"Failover" (`PrintRoute`) tenía dominio,
política de resolución y repositorio completos desde SET-8 original,
pero cero casos de uso y cero UI — mismo patrón "dominio listo, cero
CRUD" de todos los rounds anteriores; "Test" (`PrinterTestResult`) se
deja fuera de este corte a propósito, mismo límite documentado que
SET-9/SET-10 — requiere un gateway de hardware real que este repo solo
tiene como Protocol/stub.

- **Perfiles (cierre real)**: `RegisterDeviceProfileUseCase` ganó
  `paper_profile`/`protocol`/`driver_name`; cuando `device_type` es uno
  de los 4 tipos de impresora (`PRINTER_DEVICE_TYPES`), llama a
  `printer_profile_policy.assert_valid_printer_profile()` — §23 ("no
  asumir que toda impresora es ESC/POS") ahora se aplica al registrar,
  no solo documentado. `DeviceProfileCreateDialog` ganó los 3 campos
  (siempre visibles, como serial_port/host — solo validados cuando
  aplican).
- **Routing/Failover (nuevo)**: `backend/application/use_cases/
  configuracion/print_route_use_cases.py`:
  `CreatePrintRouteUseCase`/`UpdatePrintRouteUseCase`/
  `ChangePrintRouteStatusUseCase` (2 transiciones vía
  `PrintRouteStatusAction`, mismo molde "una clase, varias acciones").
  Nueva excepción `PrintRouteConflictError`. `PrintRouteRepositoryPort`/
  `SqlitePrintRouteRepository` ganaron `list_all()` (vista de gestión
  necesita ver rutas inactivas también). Permiso reutilizado:
  `DISPOSITIVOS.configuracion.gestionar` (ya registrado, sin usar hasta
  ahora). Ambas acciones de creación/edición/cambio de estado quedan
  **siempre** auditadas — una ruta mal configurada enruta directamente
  mal un documento fiscal, mismo espíritu "cambio de impresora fiscal"
  que Asignaciones (SET-7 follow-up) ya estableció.
- **2 bugs reales encontrados y corregidos por smoke-testing manual
  antes de escribir los tests formales** (ninguno de los dos es
  hipotético — ambos reprodujeron con datos reales contra SQLite):
  1. El índice único del esquema (`ux_print_routes_scope`, §62) cubre
     **toda fila sin importar `active`** — una ruta desactivada sigue
     ocupando su ámbito exacto. El chequeo de conflicto inicial de
     `CreatePrintRouteUseCase` solo miraba `list_candidates()` (activas
     únicamente), así que "desactivar y volver a crear en el mismo
     ámbito" pasaba el chequeo de dominio pero reventaba con un
     `IntegrityError` crudo de SQLite al guardar. Corregido: el chequeo
     ahora usa `list_all()` filtrado por `document_type`, sin importar
     `active`.
  2. `UpdatePrintRouteUseCase` llamaba `set_primary_device()` antes que
     `set_fallback_chain()` — promover un dispositivo que YA estaba en
     el respaldo directo a principal fallaba porque `set_primary_device()`
     valida contra la lista de respaldo **todavía vieja**. Mismo patrón
     "desmarcar antes de marcar" ya aplicado a `SetDefaultThemeUseCase`/
     `ChangeTemplateVersionStatusUseCase`, generalizado aquí a 3 pasos:
     limpiar el respaldo primero (`set_fallback_chain(())`), fijar el
     nuevo principal, y solo entonces fijar el respaldo final — así la
     validación primary↔fallback siempre corre contra el estado final
     correcto sin importar en qué dirección se mueve el dispositivo.
- No hay componente de multi-selección en este repo — el respaldo
  (`fallback_device_ids`) se captura como **códigos de dispositivo
  separados por coma** en el diálogo (`_FallbackCodesField`, mixin
  compartido por crear/editar, mismo patrón que `_BranchHoursFields` de
  Empresa), resuelto contra la misma lista `device_options` que ya
  alimenta el selector de principal — sin endpoint nuevo. `PrintRoute`
  no soporta editar `document_type`/ámbito tras crearse (solo
  principal/respaldo/activar/desactivar) — el mensaje de conflicto es
  honesto sobre esto, nunca sugiere "eliminar" (no existe delete).
- `pages/dispositivos_page.py` gana una tarjeta "Rutas de impresión"
  (tabla independiente, no depende de qué dispositivo esté seleccionado
  — una ruta no está scoped a un solo dispositivo) + `dialogs/
  print_route_dialogs.py`.
- Verificado end-to-end contra la factory real: perfil de impresora con
  paper_profile inválido rechazado → ruta creada → segundo intento al
  mismo ámbito rechazado con error de dominio limpio (no
  `IntegrityError`) → desactivar la ruta → tercer intento al mismo
  ámbito **sigue** rechazado (confirma el fix del bug 1) → promover el
  dispositivo de respaldo a principal funciona (confirma el fix del bug
  2) → usuario sin `DISPOSITIVOS.configuracion.gestionar` bloqueado
  antes del use case → audit log con CREATE/DEACTIVATE/UPDATE. Tests: 27
  nuevos, todos verdes; regresión completa limpia (424
  settings+document_output, 248 device_management, sin caídas en
  ninguna). **Siguiente**: 4 secciones aún de solo lectura (Pantalla del
  cliente, Integraciones, Notificaciones, Offline); §65-68 Resumen
  dashboard y §70 clasificación formal de legacy siguen abiertos. "Test"
  de impresoras (SET-8) y las "pruebas" de SET-9/SET-10 siguen fuera de
  alcance por la misma razón de siempre — sin gateway de hardware real.

## Avance SET-9 — Básculas y lectores: puertos, protocolos, estabilidad, diagnóstico

**Hecho** — extiende `backend/domain/device_management/` con lo
específico de básculas y lectores (§22). Ver `migrations/MIGRATION_LOG.md`
(entrada `213_scale_reader_diagnostics_schema`) para el detalle completo.
Resumen:

- **Puertos** — reutiliza `SerialPortProfile` (SET-7) sin cambios; no
  hizo falta una VO nueva. Probado explícitamente con una configuración
  de báscula real (COM4, 4800 baud, paridad E, 7 bits) para confirmar que
  el mismo tipo sirve a impresoras seriales (SET-8) y básculas por igual.
- **Protocolos** — `ScaleProtocol` (6 valores) validado por
  `policies/scale_profile_policy.py`, que además **exige la capacidad
  `WEIGH`** en todo perfil de báscula (sin ella no puede pesar nada — se
  rechaza al crear el perfil, no se descubre después). Mismo tratamiento
  para lectores vía `policies/reader_profile_policy.py`
  (`BARCODE_SCANNER`→`SCAN_1D`, `QR_SCANNER`→`SCAN_2D`) — probado que un
  lector 1D no satisface el requisito de uno 2D, no son intercambiables.
- **Estabilidad** — `WeightReading` (Decimal, nunca float) +
  `StabilityPolicy` + `policies/scale_stability_policy.py::evaluate_stability()`:
  exige que las últimas N lecturas estén **todas** marcadas estables **y**
  coincidan dentro de tolerancia. Cubre el caso "doble lectura" que el
  gate de esta fase pedía explícitamente: dos lecturas ambas marcadas
  `stable=True` pero que no concuerdan entre sí deben rechazarse igual
  (una báscula puede oscilar mientras se acomoda el producto) — y el caso
  de ventana deslizante, donde una lectura vieja/inestable fuera de la
  ventana requerida no bloquea la confirmación de las lecturas recientes.
  Deliberadamente **no persistido**: la política de estabilidad correcta
  es candidata a ser un `ConfigurationValue` (Settings, SET-2) resuelto
  por sucursal/dispositivo, no un campo fijo del schema de Device
  Management.
- **Diagnóstico** — `DeviceTestResult`, **generalizado** a propósito (no
  `ScaleTestResult`/`ReaderTestResult` separados): con dos casos de uso
  reales ya en la mano generalizar es la elección correcta, mientras que
  `PrinterTestResult` (SET-8, ya en producción vía migración 212) se deja
  intacto — deshacerlo para unificar retroactivamente no vale el churn de
  una migración; la decisión (y el porqué) queda documentada en el
  docstring de `DeviceTestResult` para que no se lea como un descuido.
- Migración `213_scale_reader_diagnostics_schema` — solo
  `device_test_results` (FK a `devices`); cero tablas nuevas para
  `WeightReading`/`StabilityPolicy`.
- **Tests**: `test_weight_reading_and_stability.py` (incluye el caso
  "doble lectura" explícito y el de ventana deslizante),
  `test_scale_and_reader_profile_policy.py`, `test_device_test_result_entity.py`
  (dominio) + `test_device_test_result_repository.py` (infraestructura —
  incluida la prueba de que un mismo dispositivo acumula tests de
  distinto `test_type`, capacidad que `PrinterTestResult` no tiene por
  diseño). **Total tras SET-9 (Settings + Device Management): 426 tests
  verdes.**

### Continuación (2026-08-22) — "Protocolos" (capacidades) cerrado; Puertos/Estabilidad/Diagnóstico confirmados sin gap

Usuario pidió "SET-9 — Básculas y lectores" con los 5 sub-puntos
originales (Puertos/Protocolos/Estabilidad/Diagnóstico/Tests). Auditado
antes de construir, punto por punto:

- **Puertos**: confirmado sin gap — `SerialPortProfile` (SET-7) ya se
  reutiliza sin cambios, y el diálogo de perfil de dispositivo ya tenía
  los campos serial_port/baud_rate desde el round de Dispositivos
  (device-type-agnósticos). Nada que construir.
- **Protocolos (gap real encontrado y cerrado)**: `scale_profile_policy.
  assert_valid_scale_profile()`/`reader_profile_policy.
  assert_valid_reader_profile()` existían desde el corte SET-9 original,
  pero — igual que `printer_profile_policy` antes del follow-up de
  SET-8 — **nunca estaban conectadas**: `RegisterDeviceProfileUseCase`
  nunca pasaba `capabilities` a `DeviceProfile.create()` (siempre tupla
  vacía), así que **ningún** perfil de báscula o lector podía pasar su
  propia política (que exige la capacidad `WEIGH`/`SCAN_1D`/`SCAN_2D`).
  Cerrado derivando la capacidad requerida a partir de `device_type`
  (determinística, nunca preguntada al usuario — mismo criterio que las
  capacidades opcionales de impresora, que siguen sin exponerse en el
  diálogo). Se hizo pública `reader_profile_policy.
  REQUIRED_CAPABILITY_BY_TYPE` (antes `_REQUIRED_CAPABILITY_BY_TYPE`) para
  que el use case y la política compartan una sola fuente de verdad en
  vez de duplicar el mapeo tipo→capacidad. El campo `protocol` del
  diálogo (compartido con impresoras desde SET-8) ahora ofrece también
  el vocabulario de báscula (`TOLEDO_STANDARD`/`SICS`/`NCI`/
  `CONTINUOUS`/`ON_DEMAND`, más `VIRTUAL` compartido) — cuál aplica lo
  decide la política correspondiente en el servidor, no se oculta nada
  en el cliente.
- **Estabilidad**: confirmado como límite de alcance deliberado, no
  gap — `WeightReading`/`StabilityPolicy`/`scale_stability_policy.
  evaluate_stability()` están explícitamente documentados en el propio
  dominio como **no persistidos**: es una política pura que se invoca en
  el momento de capturar un peso real (un flujo de Ventas/Inventario que
  todavía no existe), no algo que Configuración administre por CRUD. No
  hay nada que construir aquí hasta que exista ese flujo consumidor.
- **Diagnóstico/Test**: mismo límite ya documentado para SET-8
  (`PrinterTestResult`) — `DeviceTestResult` generalizado necesita un
  gateway de hardware real que este repo solo tiene como Protocol/stub;
  fuera de alcance por la misma razón, no repetida aquí en detalle.
- Verificado end-to-end contra la factory real: perfil de báscula con
  protocolo `TOLEDO_STANDARD` → capacidad `WEIGH` confirmada automática
  → protocolo de impresora (`ESC_POS`) rechazado para una báscula →
  lector de código de barras → capacidad `SCAN_1D` automática → lector
  QR → capacidad `SCAN_2D` automática → registro de un dispositivo real
  contra el perfil de báscula sin fricción → ruta de impresoras
  (regresión) intacta. Sin bugs nuevos encontrados esta vez (a diferencia
  de SET-8) — el smoke test pasó limpio en el primer intento. Tests: 6
  nuevos, todos verdes; regresión completa limpia (424
  settings+document_output, sin caídas). **Siguiente**: 4 secciones aún
  de solo lectura; §65-68 Resumen dashboard y §70 clasificación formal
  de legacy siguen abiertos; "Test"/diagnóstico de báscula-lector sigue
  fuera de alcance junto con el de impresoras (SET-8) y lo que falte de
  SET-10 (cajones/terminales) por la misma razón de hardware real.

## Avance SET-10 — Cajones y terminales: gateways, asignación, pruebas, seguridad

**Hecho** — extiende `backend/domain/device_management/` con lo
específico de cajones de dinero y terminales de pago (§18/§20/§23, §60).
Ver `migrations/MIGRATION_LOG.md` (entrada "SET-10 — sin migración
nueva") para el detalle completo. Resumen:

- **Sin migración 214, a propósito** — Asignación (`WorkstationDeviceAssignment`,
  SET-7) y Pruebas (`DeviceTestResult`, SET-9) ya cubrían estos dos tipos
  de dispositivo genéricamente desde que se construyeron; este SET solo
  agregó tests que lo confirman explícitamente en vez de código de
  persistencia nuevo.
- **Perfiles** — `assert_valid_cash_drawer_profile()` (exige `DRAWER_PULSE`)
  y `assert_valid_payment_terminal_profile()` (exige al menos una
  capacidad de pago real: swipe/chip/contactless/efectivo) — dominio
  puro sobre `device_profiles` (SET-7) sin cambios de schema.
- **Gateways** — decisión de alcance explícita, la misma lógica que
  viene sosteniendo todo Device Management desde SET-7: `hardware_ports.py`
  define `CashDrawerGatewayPort`/`PaymentTerminalGatewayPort` como
  **contratos**, no implementaciones — escribir E/S serial/red real para
  abrir un cajón físico o hablar con una terminal de pago real es un tipo
  de trabajo distinto (requiere hardware real, SDKs de proveedor y
  credenciales para validar contra algo de verdad), fuera de lo que este
  refactor puede construir con seguridad sin acceso a ese hardware.
  Probado con un gateway falso que demuestra la composición
  autorización→gateway (la autorización nunca se salta, el gateway nunca
  se toca si la solicitud no está autorizada).
- **Seguridad** — la pieza genuinamente nueva: `CashDrawerOpenRequest`
  (forma válida) + `assert_can_open()` (¿autorizada?), separación
  deliberada que refleja `ConfigurationValue`/`ConfigurationApprovalPolicy`
  en Settings. Codifica un control anti-robo real, no inventado: la
  auditoría SET-0 encontró el permiso legacy
  `CASH_DRAWER_OPEN_WITHOUT_SALE` en el catálogo de Caja
  (`docs/refactor/settings_legacy_inventory.md` §7) — abrir el cajón sin
  venta asociada exige un motivo explícito; con venta, no. Un test
  expuso que la primera versión de `assert_can_open()` solo comprobaba
  veracidad de `reason` (un string de puros espacios se habría colado si
  alguien construía el VO sin pasar por `.create()`) — corregido antes de
  cerrar el corte, no después.
- **Tests**: `test_cash_drawer_and_terminal_profile_policy.py`,
  `test_cash_drawer_security_policy.py`, `test_cash_drawer_terminal_assignment.py`,
  `test_hardware_ports_composition.py` (dominio) +
  `test_cash_drawer_terminal_integration.py` (infraestructura — registro,
  asignación, prueba y autorización de apertura de extremo a extremo
  contra SQLite real, incluida la reconfirmación de que el índice único
  de asignación activa de SET-7 también aplica a estos dos tipos de
  dispositivo). **Total tras SET-10 (Settings + Device Management): 479
  tests verdes.**

### Continuación (2026-08-22) — "Perfiles" cerrado; Gateways/Pruebas/Seguridad confirmados sin gap (3ª vez consecutiva del mismo patrón)

Usuario pidió "SET-10 — Cajones y terminales" con los 5 sub-puntos
(Gateways/Asignación/Pruebas/Seguridad/Tests). Auditado punto por punto,
mismo criterio que SET-7/8/9:

- **Perfiles (gap real, cerrado — 3ª vez con la misma forma)**:
  `cash_drawer_profile_policy.assert_valid_cash_drawer_profile()`
  (exige `DRAWER_PULSE`) y `payment_terminal_profile_policy.
  assert_valid_payment_terminal_profile()` (exige al menos una de 5
  capacidades de pago reales) existían desde el corte original, nunca
  conectadas — mismo hueco exacto que impresoras (SET-8)/básculas-
  lectores (SET-9): `capabilities` nunca se poblaba, así que ningún
  perfil de cajón o terminal podía pasar su propia política. Cerrado
  igual que antes: `DRAWER_PULSE` se deriva de `device_type`
  (determinístico, como `WEIGH`); las capacidades de terminal de pago
  **no** son determinísticas (una terminal puede aceptar tarjeta banda/
  chip/sin-contacto/efectivo/dispensar en cualquier combinación) — única
  excepción real a "la capacidad se deriva, nunca se pregunta": el
  diálogo ahora pide checkboxes de las 5 capacidades. Se usó `QCheckBox`
  en vez del patrón "códigos separados por coma" (SET-8) porque aquí el
  vocabulario es pequeño y fijo (5 valores), no una lista abierta de
  referencias a otras entidades — el patrón de coma existe para resolver
  contra una lista real (dispositivos), no para elegir de un enum
  minúsculo.
- **Gateways**: confirmado límite de alcance deliberado, no gap —
  `hardware_ports.py::CashDrawerGatewayPort`/`PaymentTerminalGatewayPort`
  son Protocols puros sin implementación real desde el corte original,
  misma razón que todo Device Management sostiene desde SET-7/8/9: abrir
  un cajón físico o hablar con una terminal de pago real necesita
  hardware/SDK de proveedor real contra el cual validar.
- **Asignación**: confirmado sin gap — **ya construido en el follow-up
  de SET-7**: `AssignmentRole.CASH_DRAWER`/`PAYMENT_TERMINAL` ya estaban
  en el enum de 11 roles desde el corte original, y la UI de
  Asignaciones (tarjeta en la página Estaciones) ya funciona para estos
  dos tipos sin ningún cambio — verificado en el smoke test de este
  mismo corte (asignar un cajón y una terminal a una estación, ambos
  funcionan de punto a punto contra la factory real).
- **Pruebas**: confirmado límite de alcance — `DeviceTestResult`
  (SET-9, ya generalizado) cubre cajones/terminales genéricamente, pero
  ejecutar una prueba real necesita el mismo gateway de hardware que no
  existe. Mismo límite que impresoras (SET-8)/básculas-lectores (SET-9).
- **Seguridad**: confirmado como un límite de alcance distinto de los
  anteriores, no un gap de UI de Configuración — `CashDrawerOpenRequest`/
  `cash_drawer_security_policy.assert_can_open()` es una autorización de
  **acción en tiempo real** (¿puede este usuario abrir el cajón ahora,
  con o sin venta asociada?), no algo que Configuración administre por
  CRUD. Mismo tipo de límite que "Estabilidad" en SET-9 (una política
  pura consumida por un flujo operativo de Caja/Ventas que todavía no
  existe) — nada que construir aquí hasta que ese flujo exista.
- Verificado end-to-end contra la factory real: cajón de dinero →
  `DRAWER_PULSE` automático → terminal de pago sin capacidades
  seleccionadas rechazada → terminal con capacidades seleccionadas
  (`CARD_CHIP`/`CARD_CONTACTLESS`) aceptada → dispositivo real registrado
  contra ambos perfiles sin fricción → **asignación de cajón y terminal
  a una estación funciona sin ningún cambio** (confirma que SET-7 ya
  cerró ese pilar) → rutas de impresoras/perfiles de báscula/lector
  (regresión) intactos. Sin bugs nuevos encontrados (2º corte limpio
  consecutivo tras SET-9) — cambio puramente aditivo, sin mutación de
  estado cruzado como el de SET-8. Tests: 4 nuevos, todos verdes;
  regresión completa limpia (424 settings+document_output, sin caídas).
  **Siguiente**: 4 secciones aún de solo lectura; §65-68 Resumen
  dashboard y §70 clasificación formal de legacy siguen abiertos.
  **Esto cierra la familia de 4 rounds consecutivos (SET-7/8/9/10) que
  encontraron y cerraron el mismo patrón "política construida, nunca
  conectada" en Device Management** — no queda ningún perfil de
  dispositivo (impresora/báscula/lector/cajón/terminal) sin su
  validación de capacidades conectada al flujo real de registro.

## Avance SET-11 — Document Output: Templates, Versiones, Renderers, PrintJobs, Worker

**Hecho** — abre `backend/domain/document_output/`, el segundo bounded
context nuevo de este refactor (el primero fue Device Management en
SET-7). Ver `migrations/MIGRATION_LOG.md` (entrada "214_document_output_schema")
para el detalle completo. Resumen:

- **Nuevo, no reemplaza `print_job_log` todavía** — decisión de alcance
  explícita, la misma lógica que sostuvo no tocar `sucursales` (SET-5) ni
  `hardware_config` (SET-7): `print_job_log` (migración 056) es una tabla
  legacy **con consumidor real y activo** — `core/services/printer_service.py::
  PrintQueue._log_job_to_db` (documentado en
  `docs/refactor/SALES-17_document_output.md`) — no un cascarón muerto.
  `print_jobs` (nuevo, migración 214) es una tabla aditiva y separada;
  cortar el consumidor de Ventas hacia la nueva tabla es trabajo de una SET
  posterior (probablemente SET-12/Tickets, que ya está listada como la que
  "elimina `ticket_delivery.py`/`ticket_printer_service.py` duplicados"),
  no de este corte.
- **Templates** — `DocumentTemplate`: identidad/metadata por
  `document_type` (20 valores — el inventario completo de documentos
  imprimibles del ERP, desde `SALE_TICKET` hasta `SWEEPSTAKES_TICKET`).
  Mismo rol que `ConfigurationDefinition` en Settings.
- **Versiones** — `DocumentTemplateVersion`: máquina de 7 estados (DRAFT →
  PENDING_APPROVAL → APPROVED → ACTIVE → INACTIVE/EXPIRED → ARCHIVED), sin
  REJECTED terminal — un rechazo regresa a DRAFT para revisión, no mata la
  versión. Toda edición crea versión nueva (`create_next_version()`,
  encadenada por `previous_version_id`), nunca in-place. La supersesión
  "cuál versión es la ACTIVE" vive en
  `policies/template_activation_policy.py::activate_version()`, reforzada
  con un índice único parcial (`ux_dtv_template_active`) — probado con un
  test de integración que confirma el `IntegrityError` si se intenta
  activar una segunda versión sin pasar por la policy.
- **PrintJobs** — `PrintJob`: máquina de 8 estados. Nunca se imprime
  directo desde UI (§26/§70) — toda impresión pasa por esta entidad.
  `start_printing()` exige `printer_device_id` ya asignado. Reimpresión
  (§33) es siempre un job nuevo (`create_reprint(reason)`, encadenado por
  `reprint_of_job_id`), nunca una mutación del original.
- **Worker** — `policies/print_job_queue_policy.py`: solo la *decisión*
  (`select_next_job` por prioridad+FIFO, `should_retry`/
  `retry_or_dead_letter`), no el loop de fondo real — eso es
  infraestructura de una SET posterior.
- **Renderers** — `rendering_ports.py::DocumentRendererPort`: Protocol
  puro, sin implementación real, misma razón que `hardware_ports.py`
  (SET-10) — generar ESC/POS o PDF real requiere una librería/vendor
  concreto contra el cual validar. Probado con un renderer falso
  (`test_rendering_ports_composition.py`).
- **operation_id como idempotencia, no campo de dominio** — descubierto al
  escribir el repositorio de `PrintJob`: el primer borrador reutilizaba
  `source_document_id` como llave de idempotencia, lo cual es
  semánticamente incorrecto (un mismo documento origen puede generar más
  de un `PrintJob` legítimamente, p. ej. una reimpresión). Se corrigió
  para replicar exactamente el patrón de `configuration_values.operation_id`
  de Settings — columna solo de persistencia, con su propio índice único
  parcial — antes de escribir los tests de integración.
- **Tests**: `tests/unit/document_output/` — 64 tests (template + máquina
  de estados de versión + `template_activation_policy`; máquina de
  estados completa de `PrintJob` + `create_reprint()`; selección de cola
  por prioridad/FIFO + reintento/dead-letter; composición de
  `DocumentRendererPort` con un renderer falso). `tests/integration/
  document_output/` — 13 tests contra SQLite real (round-trip de los 3
  repositorios, upsert, listados filtrados, supersesión de versión activa
  vía policy + su índice único, ciclo de vida completo de un `PrintJob`
  persistido, `operation_id` como idempotencia + su índice único,
  reimpresión persistida como job independiente). **Total tras SET-11
  (Settings + Device Management + Document Output): 556 tests verdes.**
  Tras la continuación del 2026-08-22 (edición + activar/desactivar
  familia de plantilla): **575 tests verdes** (+19).

### Continuación (2026-08-22) — "Plantillas" cerrado (edición + activar/desactivar familia); Renderers/PrintJobs/Worker confirmados sin gap por primera vez con 3 razones distintas

Usuario pidió "SET-11 — Document Output" con los 5 sub-puntos
(Templates/Versiones/Renderers/PrintJobs/Worker). Auditado punto por
punto:

- **Templates/Versiones**: ya tenían CRUD real — construido en el round
  de Documentos (SET-25 follow-up #3, mismo día, antes de esta serie
  SET-N repegada) — creación de plantilla+primera versión, nuevas
  versiones, y las 7 transiciones de aprobación. Al auditar de cerca se
  encontró un gap real dentro de "Templates": `DocumentTemplate.
  activate()`/`deactivate()` (la **familia completa**, no solo el
  contenido de una versión) existían desde el corte original pero
  **nunca tuvieron caso de uso** — no había forma de retirar una
  plantilla entera (p. ej. "ya no imprimimos recibos de regalo"),
  distinto de desactivar el contenido de una versión específica.
  Tampoco existía `update_details()` en el dominio — a diferencia de
  Device/Workstation/Company (que ya tenían el método sin conectar),
  aquí el método **ni siquiera existía**, había que agregarlo primero.
  Cerrado: `DocumentTemplate.update_details(name, module, description)`
  (nuevo) + `UpdateDocumentTemplateUseCase`/
  `ChangeDocumentTemplateStatusUseCase` (2 acciones, mismo molde que
  `ChangePrintRouteStatusUseCase`) + botones "Editar plantilla"/
  "Activar plantilla"/"Desactivar plantilla" en la página Documentos,
  operando sobre la plantilla seleccionada (distintos de los botones de
  versión ya existentes). Permisos reutilizados sin cambios
  (`DOCUMENTOS.plantilla.editar`/`.activar`, ya registrados y usados
  para versiones — semánticamente correcto reusarlos también a nivel
  familia). `_page_documentos` cambiado a `list_all()` (antes
  `list_active()`), mismo patrón de vista de gestión que todas las
  secciones anteriores.
- **Renderers**: confirmado límite de alcance — `DocumentRendererPort`
  es un Protocol puro sin implementación real desde el corte original,
  misma razón que `hardware_ports.py` (SET-10): generar ESC/POS o PDF
  real necesita una librería/vendor concreto.
- **PrintJobs**: confirmado límite de alcance, pero por una razón
  **distinta** a Renderers — `PrintJob` SÍ es una entidad completa con
  repositorio real (a diferencia de políticas puras como Estabilidad/
  Seguridad de SET-9/10), pero el propio corte original documenta que
  **ningún consumidor real crea filas todavía**: cortar Ventas hacia
  esta tabla queda explícitamente diferido a "una SET posterior" (nunca
  ejecutado). Una UI de gestión de cola sobre una tabla que nunca recibe
  filas reales sería una pantalla muerta — mismo problema de fondo que
  "Diagnóstico"/"Pruebas" en SET-8/9/10 (entidad real, cero productor
  real), aunque la causa específica sea distinta (dependencia de un
  corte de Ventas pendiente, no de hardware).
- **Worker**: confirmado límite de alcance explícito **desde el propio
  corte original** (no un olvido) — `print_job_queue_policy.py` es
  deliberadamente solo la *decisión* (qué job sigue, cuándo reintentar);
  el loop de fondo real está documentado ahí mismo como "infraestructura
  de una SET posterior", nunca asignado a SET-11.
- Verificado end-to-end contra la factory real: crear plantilla → editar
  nombre/módulo/descripción → desactivar la familia completa → confirmado
  que sigue apareciendo en la vista de gestión (ya no en la de solo
  activas) → reactivar → usuario sin `DOCUMENTOS.plantilla.editar`/
  `.activar` bloqueado antes del use case en ambos casos → audit log
  registra ACTIVATE/DEACTIVATE de la familia → flujo de versión
  (regresión) intacto. Sin bugs nuevos encontrados (3er corte limpio
  consecutivo). Tests: 19 nuevos, todos verdes; regresión completa
  limpia (198 settings, sin caídas). **Siguiente**: 4 secciones aún de
  solo lectura; §65-68 Resumen dashboard y §70 clasificación formal de
  legacy siguen abiertos. Esta es la primera SET reprisada donde 3 de
  los 5 sub-puntos originales (Renderers/PrintJobs/Worker) se confirman
  sin gap por 3 razones genuinamente distintas (falta de librería real,
  falta de productor real, y diferimiento explícito del corte original)
  — no un patrón repetido, sino tres límites de alcance independientes
  que coinciden en el mismo SET.

## Avance SET-12 — Tickets: Secciones, DTO, Routing, Reimpresión

**Hecho** — completa `backend/domain/document_output/` para que
cualquier módulo (no solo Ventas) pueda componer y enrutar un ticket real
usando la infraestructura de SET-8/SET-11. Ver `migrations/MIGRATION_LOG.md`
(entrada "SET-12 — sin migración nueva") para el detalle completo. Resumen:

- **Sin migración 215, a propósito** — el arreglo de secciones de una
  plantilla y el DTO de un ticket son, en este corte, conceptos de
  dominio puro sin tabla propia; el ruteo y la reimpresión componen
  entidades/tablas que SET-8/SET-11 ya crearon.
- **Secciones** — `DocumentSectionCode` (13 códigos, el mismo vocabulario
  ya probado en producción por `core/tickets/ticket_layout_config.py::
  DEFAULT_BLOCK_ORDER`, no inventado) + `DocumentSection`/`SectionLayout`
  — dominio puro, valida códigos únicos, expone orden y habilitados.
- **DTO** — `TicketLine`/`TicketTotals`/`TicketPaymentSummary`/
  `TicketParty`/`TicketData`, Decimal de punta a punta, generalizando el
  `TicketPrintModel` legacy (float). Dos invariantes aritméticas reales
  atrapadas en construcción: `TicketTotals.total == subtotal - discount`,
  y la suma de `TicketData.lines[].line_total` debe coincidir con
  `totals.subtotal`. `to_render_data()` serializa Decimal como string
  hacia el `data: dict` que `DocumentRendererPort.render()` ya esperaba
  desde SET-11 — sin romper esa firma. El DTO específico de Ventas
  (`backend/application/sales/dto.py::SaleReceiptDataDTO`, SALES-17)
  queda intacto; este es para módulos que aún no tienen el suyo.
- **Routing** — `routing_ports.py::PrintRouteResolverPort` +
  `policies/ticket_routing_policy.py::create_routed_print_job()`
  (compone creación + resolución + `assign_route()` sin dejar nunca un
  job creado-pero-no-enrutado). A diferencia de los Protocols de
  renderers (SET-11) y hardware (SET-10), que se quedaron sin
  implementación real porque necesitan una librería/vendor/hardware
  concreto para validar, resolver una ruta es lógica pura + lecturas de
  SQLite — así que esta vez sí hay un adaptador real:
  `backend/infrastructure/integrations/document_output_print_routing_client.py::
  DocumentOutputPrintRoutingClient`, que delega enteramente en
  `device_management.policies.print_routing_policy` (SET-8) y sus
  repositorios reales, mismo patrón que `sales_cash_drawer_client.py`.
  Probado contra SQLite real: dispositivo primario, failover a respaldo,
  ruta más específica gana, sin ruta disponible, sin dispositivo
  disponible.
- **Reimpresión** — `policies/reprint_policy.py::assert_reprintable()`/
  `request_reprint()`, construido sobre `PrintJob.create_reprint()`
  (SET-11) sin modificarlo — esa operación mecánica sigue permitiendo
  reimprimir desde cualquier estado, a propósito. La policy nueva es la
  entrada estricta: solo PRINTED/FAILED/CANCELLED/DEAD_LETTER califican,
  no los estados en curso (PENDING/RENDERING/READY/PRINTING). Autorización
  (el equivalente de `POS.ticket.reimprimir` por módulo) queda fuera a
  propósito — decisión de capa de aplicación, como ya hace
  `ReprintReceiptUseCase` para Ventas.
- **`ticket_delivery.py`/`ticket_printer_service.py`: no eliminados.** La
  tabla de fases original describía SET-12 como el que los "elimina";
  este corte construye la capacidad que lo haría posible pero no ejecuta
  el corte de producción sobre rutas de impresión térmica reales sin
  validación manual contra hardware físico — misma cautela que no tocar
  `print_job_log` en SET-11.
- **Tests**: `tests/unit/document_output/` — 51 tests nuevos
  (`test_document_sections.py`, `test_ticket_data_dto.py`,
  `test_ticket_routing_policy.py` con un resolver falso — sin importar
  device_management —, `test_reprint_policy.py`).
  `tests/integration/document_output/test_print_routing_client.py` — 6
  tests contra SQLite real del adaptador real de ruteo, incluida la
  composición de punta a punta con `create_routed_print_job()`. **Total
  tras SET-12 (Settings + Device Management + Document Output): 613
  tests verdes.**

### Continuación (2026-08-22) — cutover real: Ventas gana un productor real de PrintJob

Auditoría del propio SET-12 (repegado, sin sub-puntos nuevos del usuario
esta vez — se pidió re-auditar "Secciones/DTO/Routing/Reimpresión") encontró
que, pese a estar `COMPLETO` desde el corte original, **ningún caller de
aplicación en todo el repo usaba nunca** `create_routed_print_job()`/
`request_reprint()`/`DocumentOutputPrintRoutingClient` — solo los tests
propios de SET-12 los ejercitaban. A diferencia de Renderers (sin
implementación real posible, necesita librería/hardware) o PrintJobs/Worker
(diferidos explícitamente desde el corte original), Routing/Reimpresión
**sí tenían un adaptador real** desde el principio — el único motivo de que
siguieran sin consumidor era que nadie los había conectado. El usuario
decidió explícitamente cerrar esa brecha conectando la impresión real de
Ventas, aceptando que es un cambio de producción más riesgoso que cualquier
otra ronda de esta sesión (no una simple UI de Configuración).

**Hallazgo de la auditoría previa a tocar código**: `sales_pos/` (única
pantalla POS viva desde SALES-22) **nunca imprime automáticamente al
cerrar una venta** — la única acción que envía un ticket a imprimir hoy es
Reimprimir (F12) vía `ReprintReceiptUseCase`. Comportamiento preexistente,
no modificado por este cambio. También confirmado: no existe implementación
real de `DocumentRendererPort`, y `PrinterService` (legacy) está fijo a UN
solo dispositivo configurado en `hardware_config` — dirigir bytes reales a
un dispositivo específico resuelto por ruteo necesitaría puentear
`DeviceProfile.ConnectionProfile` dentro de `PrinterService`, un trabajo
separado y mayor que necesita validación con hardware real. **Alcance de
este corte, con precisión**: solo ruteo (qué dispositivo *serviría* este
ticket, con failover real — SET-8) y gobernanza de auditoría/reimpresión
sobre `PrintJob`. El renderizado de bytes y el envío físico siguen 100% en
`PrinterService`/`TicketESCPOSRenderer` sin tocar — `printer_device_id`/
`print_route_id` quedan grabados solo para auditoría.

**Propiedad de seguridad central**: invisible mientras nadie configure
nada. Ningún `DocumentTemplate` `SALE_TICKET` activo ni `PrintRoute`
existían en la base real antes de este cambio, así que el día uno debe
comportarse byte-por-byte igual que antes — degrada a no-op (registrado,
nunca relanzado) ante cualquier prerequisito faltante o fallo de
resolución, jamás bloquea un ticket real. El camino de activación no
necesita UI nueva: la página Documentos (SALE_TICKET ya es uno de sus
~27 `DocumentType`) y la tarjeta "Rutas de impresión" de Dispositivos
(campo `document_type` de texto libre, el tooltip ya sugiere
`"SALE_TICKET"` como ejemplo) ya lo cubren.

**Construido**:
- `PrintJobRepositoryPort`/`SqlitePrintJobRepository`: nuevo
  `list_by_source(source_module, source_document_id)` (orden
  `requested_at DESC, id DESC` — el segundo criterio importa: `requested_at`
  solo tiene precisión de segundo, y un UUIDv7 ordena lexicográficamente
  por tiempo de creación, así que sirve de desempate real, no cosmético).
- `backend/infrastructure/integrations/sales_print_job_client.py::
  SalesPrintJobClient` (nuevo, mismo molde delgado que
  `sales_receipt_client.py`/`document_output_print_routing_client.py`):
  busca la plantilla+versión activa de `SALE_TICKET` (ya existía
  `list_by_document_type()`, no hizo falta un método nuevo); si hay un
  `PrintJob` previo para la venta, pasa por `reprint_policy.
  request_reprint()` (si el previo no es reimprimible aún —sigue en
  vuelo—, es un **skip de gobernanza**, nunca un fallback silencioso a un
  job nuevo sin relación — bug real encontrado y corregido durante el
  desarrollo, antes de escribir los tests); si no hay uno previo, rutea
  con `create_routed_print_job()`. Captura `PrintRouteNotFoundError`/
  `NoAvailablePrinterError`/`DocumentReprintNotAllowedError` → `None`.
- `ReprintReceiptUseCase.execute` (nuevo parámetro opcional `reason`,
  compatible hacia atrás): envuelve la integración completa en
  try/except — un fallo inesperado de Document Output nunca debe romper
  una reimpresión real — y pasa callbacks `on_success`/`on_error` a
  `SalesReceiptClient.print_receipt_data()` que marcan el `PrintJob`
  `PRINTED`/`FAILED` reflejando el resultado REAL del `PrinterService`
  legacy (mismo patrón ya usado por `PrintQueue._log_job_to_db`: escribir
  a la DB desde el callback asíncrono usando la misma `connection`).
- Sin migración nueva — `print_jobs` (migración 214) ya tenía todas las
  columnas necesarias.

**Fuera de alcance, documentado explícitamente**: dirigir bytes reales al
dispositivo resuelto por ruteo (necesita puentear `ConnectionProfile` en
`PrinterService` + validación con hardware real); impresión automática al
cerrar venta (comportamiento preexistente, no es parte de este cambio);
`SaveReceiptDocumentUseCase` (PDF, no es un `PrintJob` físico).

**Tests**: 14 nuevos — `test_document_output_repositories.py` (+1,
`list_by_source`), `test_sales_print_job_client.py` (8, incluye el caso
del bug de gobernanza above), `test_sales_reprint_print_job_cutover.py`
(5, incluye "Document Output lanza una excepción inesperada → la
reimpresión real igual tiene éxito" y "sin nada configurado → cero
cambio de comportamiento"). Regresión completa limpia: 299 tests
(`tests/unit/document_output` + `tests/integration/document_output` +
`tests/unit/test_sales_receipts.py`), 353 tests
(`tests/unit/test_sales*.py`) — cero regresiones. **Total tras esta
continuación: 627 tests verdes** (613 + 14).

## Avance SET-13 — Marketing en tickets: Campaigns, Rules, FOMO policy, Loyalty summary

**Hecho** — agrega mensajes de marketing configurables a
`backend/domain/document_output/`, generalizando la lógica real y
probada de `core/tickets/ticket_message_engine.py::TicketMessageEngine`
(mensajes de fidelidad/FOMO/CTA siempre derivados de datos reales de
negocio, nunca urgencia inventada) en datos persistidos y editables. Ver
`migrations/MIGRATION_LOG.md` (entrada "215_marketing_campaigns_schema")
para el detalle completo. Resumen:

- **Campaigns** — `MarketingCampaign` (`code`/`category`/`message_template`/
  `priority`/`requires_customer`/`rules`/`active`), persistida en la tabla
  nueva `marketing_campaigns` (migración 215) — a diferencia de
  Secciones/DTO (SET-12, sin tabla), un catálogo de campañas gestionable
  por un admin sí encaja con el patrón de catálogo persistido de
  `DocumentTemplate` (SET-11).
- **Rules** — `CampaignRule` (`metric`/`comparator`/`threshold`, Decimal),
  generaliza los umbrales que el motor legacy tenía hardcodeados en
  Python (`goal_remaining <= 5`, `points_to_reward <= 50`,
  `promo_days_left <= 4`) en datos configurables sin desplegar código.
  `MarketingCampaign.matches(context)` exige que todas las reglas pasen
  (AND). Serializadas inline como `rules_json`, sin tabla propia.
- **FOMO policy** — `policies/marketing_claim_validation_policy.py::
  assert_responsible_claim()`: rechaza toda campaña FOMO sin ninguna
  regla — un mensaje de urgencia/escasez sin condición real detrás
  imprimiría siempre, el patrón manipulador que el motor legacy nunca
  tuvo. `select_messages()` generaliza el cap de frecuencia legacy
  (`ticket_fomo_max_messages=2`, antes solo para FOMO) a las tres
  categorías, configurable.
- **Loyalty summary** — `LoyaltySummary` (generaliza `TicketLoyaltyInfo`
  legacy), estado de cuenta factual, no sujeto a la FOMO policy.
  `TicketData` (SET-12) se extiende con `loyalty`/`messages`, ambos con
  default vacío — no rompe ningún caller de SET-12 existente, confirmado
  re-corriendo sus 115 tests antes de escribir los nuevos.
- **Tests**: `tests/unit/document_output/` — 40 tests nuevos
  (`test_marketing_campaign.py`, `test_marketing_claim_validation_policy.py`,
  `test_loyalty_summary_and_ticket_data.py`). `tests/integration/
  document_output/test_marketing_campaign_repository.py` — 9 tests contra
  SQLite real. **Total tras SET-13 (Settings + Device Management +
  Document Output): 662 tests verdes.**

### Continuación (2026-08-23) — cutover real: mensajes de fidelidad/marketing en tickets vivos

Auditoría del propio SET-13 (repegado, mismo patrón que SET-12) encontró
**cero callers de aplicación en todo el repo** para `MarketingCampaign`/
`marketing_claim_validation_policy`/`LoyaltySummary` — solo sus propios
tests los ejercitaban. El motor legacy que generaliza,
`core/tickets/ticket_message_engine.py::TicketMessageEngine`, resultó
estar igualmente desconectado (solo referenciado por sus propios tests) —
un callejón sin salida preexistente, no causado por este refactor. Pero
`core/services/sales_service.py::_execute_sale_core` (el viejo camino REST
de cierre de venta) sí construye un `loyalty_result` real vía
`LoyaltyService.process_loyalty_for_sale()`, y el renderer ESC/POS legacy
ya tiene bloques reales `loyalty`/`fomo_messages`. El camino nuevo de
escritorio (`SalesReceiptClient._to_ticket_payload()`, cableado por el
cutover de SET-12) nunca poblaba esas claves — los tickets del POS de
escritorio no mostraban contenido de fidelidad/marketing, a diferencia del
viejo camino REST. El usuario decidió explícitamente cerrar esa brecha de
paridad conectando mensajes reales a los tickets vivos.

**Prerequisito duro encontrado durante la investigación**: no existía
ningún camino de administración para crear una `MarketingCampaign` — sin
eso, la selección de mensajes sería permanentemente inerte. Este corte
incluye entonces un CRUD administrativo mínimo (mismo patrón SET-6..11) a
la par del cableado de consumo — ambas mitades son necesarias para que la
funcionalidad haga algo real, no alcance añadido de más.

**Segundo límite encontrado y respetado**: el checkout de `sales_pos` solo
maneja *canje* de fidelidad (`RedeemLoyaltyPointsUseCase`), nunca *gana*
puntos en una venta completada (a diferencia del viejo camino `SalesService.
_execute_sale_core`). Construir un pipeline de ganancia de puntos es un
cambio financiero/de fidelidad separado y mucho mayor, explícitamente
**fuera de alcance** — `LoyaltySummary.points_earned` queda honestamente
en `None` para tickets de sales_pos; solo `points_balance`/`tier` (una
consulta real, de solo lectura, sin efectos secundarios) se pueblan.

**Construido**:
- `MarketingCampaign.update_details()` (nuevo — no existía forma de
  editar mensaje/prioridad/requires_customer/reglas tras la creación).
- `MarketingCampaignRepositoryPort`/`SqliteMarketingCampaignRepository`:
  nuevo `list_all()` (vista de gestión necesita campañas inactivas
  también).
- `backend/infrastructure/integrations/sales_loyalty_client.py::
  SalesLoyaltyClient.peek_loyalty_summary()` (nuevo) — reutiliza
  `LoyaltyService.preview_redemption()` (ya documentado como sin efectos
  secundarios: "no registra ni decrementa puntos") en vez de inventar una
  consulta nueva.
- `backend/infrastructure/integrations/sales_marketing_client.py::
  SalesMarketingClient` (nuevo, mismo molde delgado que
  `sales_receipt_client.py`) — construye el contexto SOLO con datos reales
  ya disponibles (`subtotal`/`total`/`has_customer`/`points_balance`, sin
  inventar métricas de negocio), llama `select_messages()` con un tope de
  1/2/1 por categoría (generaliza el `max_fomo=2` legacy a las 3
  categorías), degrada a `()` ante cualquier fallo — nunca rompe un ticket
  real.
- `ReprintReceiptUseCase.execute` (ya tocado por SET-12): agrega la
  consulta de fidelidad + selección de mensajes, ambas envueltas en
  try/except independientes (un fallo en una nunca suprime la otra), y las
  pasa a `SalesReceiptClient.print_receipt_data(loyalty=..., messages=...)`.
  `SalesReceiptClient._to_ticket_payload()` puebla `payload["loyalty"]`/
  `["fomo_messages"]` con la MISMA forma que el renderer legacy ya leía
  (`_loyalty_bytes`/`_fomo_bytes`, confirmado leyendo el renderer, no
  asumido).
- CRUD administrativo mínimo: `CreateMarketingCampaignUseCase` (valida
  FOMO-responsable ANTES de guardar — una campaña FOMO sin reglas nunca
  llega a la base), `UpdateMarketingCampaignUseCase` (re-valida por la
  misma razón — las reglas pueden editarse y quitarse de una campaña FOMO
  existente), `ChangeMarketingCampaignStatusUseCase`. Códigos de permiso
  `campana.ver/crear/editar/activar` registrados bajo el módulo
  `DOCUMENTOS` ya existente (mismo patrón que `plantilla.*`, no un módulo
  nuevo). Activar/desactivar auditado (transición crítica de familia,
  mismo peso que el toggle de plantilla); crear/editar no auditado (edición
  de contenido rutinaria). Nueva tarjeta "Campañas de marketing" en la
  página Documentos, mismo patrón independiente-no-selection-driven que
  "Rutas de impresión" en Dispositivos.
- Sin migración nueva — `marketing_campaigns` (migración 215) ya tenía
  todas las columnas necesarias.
- **Fuera de alcance, documentado explícitamente**: ganar puntos de
  fidelidad en el checkout de `sales_pos` (cambio financiero, no de
  tickets); cablear mensajes al viejo camino legacy `SalesService`/REST
  (ya vivo y funcionando por su propio mecanismo); cualquier métrica de
  campaña más allá de `subtotal`/`total`/`points_balance`/`has_customer`
  (sin datos de negocio inventados).
- **Tests**: 41 nuevos — `MarketingCampaign.update_details()` (5),
  `list_all()` del repositorio (1), 3 casos de uso de administración (8),
  `SalesLoyaltyClient.peek_loyalty_summary()` (2, incluye verificación
  explícita de que el ledger de fidelidad queda intacto), `SalesMarketingClient.
  select_ticket_messages()` (8, incluye cap por categoría, plantilla mal
  formada omitida sin romper el resto, requires_customer), cutover de
  `ReprintReceiptUseCase` (4, incluye "nada configurado → sin cambio de
  comportamiento" y "el cliente de marketing lanza una excepción
  inesperada → la reimpresión real igual tiene éxito"), tarjeta/diálogos
  de Documentos (6), autorización del presenter (7). Regresión completa
  limpia: 303 tests del dominio `document_output` (era 271 antes de este
  corte — la cifra citada al cerrar SET-12 quedó desactualizada, no se
  re-corrió tras agregar los archivos de cutover de esa misma ronda; 902
  tests en la regresión cruzada completa (document_output + sales +
  configuracion + UI workspace + autorización del presenter), cero fallos.
  **Siguiente**: 4 secciones aún de solo lectura; §65-68 Resumen dashboard
  y §70 clasificación formal de legacy siguen abiertos; dirigir bytes
  reales al dispositivo resuelto por ruteo (SET-12) sigue pendiente de
  hardware real.

## Avance SET-14 — Etiquetas: Label templates, Variables, Serialización, Routing

**Hecho** — extiende `backend/domain/document_output/` para que las
etiquetas (lote/peso/transferencia/conteo/ajuste/producto) se compongan e
impriman con la misma infraestructura que los tickets. Ver
`migrations/MIGRATION_LOG.md` (entrada "SET-14 — sin migración nueva")
para el detalle completo. Resumen:

- **Sin migración 216, a propósito** — ni las plantillas de etiqueta ni
  las variables necesitaron esquema nuevo.
- **Tres pipelines de etiqueta reales encontrados en la auditoría previa**
  (de ahí la descripción original de este SET, "elimina los 3
  pipelines"): `backend/application/inventory/labels/` (INV-26, el
  bueno — real, auditado, permission-gated, pero con renderers
  hardcodeados en Python, sin plantilla editable), `labels/
  generador_etiquetas.py` (v11, PNG/PDF/HTML), `modulos/etiquetas.py`
  (UI v13). **Los tres siguen operando, no se tocaron** — misma cautela
  que `print_job_log`/`ticket_delivery.py` en SET-11/12.
- **Label templates** — sin entidad nueva: `DocumentTemplate`/
  `DocumentTemplateVersion` (SET-11) ya sirven para etiquetas. 6 valores
  nuevos en `DocumentType` (`LOT_LABEL`/`WEIGHT_LABEL`/`TRANSFER_LABEL`/
  `COUNT_LABEL`/`ADJUSTMENT_LABEL`/`PRODUCT_LABEL`), generalizando
  `backend/domain/inventory/enums.py::LabelType` (INV-26, mismas 6
  categorías). `RenderFormat.ZPL` ya existía desde SET-11. Probado con
  `DocumentTemplate`/`DocumentTemplateVersion` reales contra SQLite.
- **Variables** — `LabelVariable`/`LabelVariableSet.assert_satisfied()`,
  generaliza los parámetros hardcodeados de los renderers INV-26 en un
  esquema tipado (STRING/DECIMAL/INTEGER/DATE) validable antes de
  renderizar. Sin tabla nueva — misma decisión que `SectionLayout` en
  SET-12.
- **Serialización** — `LabelData`, la contraparte de `TicketData`
  (SET-12) para etiquetas, generaliza
  `backend/domain/inventory/value_objects/label_document.py::LabelDocument`
  (INV-26) hacia Document Output. Alimenta el mismo
  `DocumentRendererPort.render()` sin cambiar su firma.
- **Routing** — sin código nuevo: `create_routed_print_job()` (SET-12) ya
  era agnóstico al `document_type` — funciona para una etiqueta igual que
  para un ticket. Probado explícitamente para confirmarlo.
- **Tests**: `tests/unit/document_output/` — 36 tests nuevos
  (`test_label_variables.py`, `test_label_data.py`,
  `test_label_templates_and_routing.py`). `tests/integration/
  document_output/test_label_document_persistence.py` — 2 tests contra
  SQLite real. **Total tras SET-14 (Settings + Device Management +
  Document Output): 698 tests verdes.**

### Continuación (2026-08-23) — el primer gateway físico REAL de todo el track: INV-26 imprime etiquetas de verdad por primera vez

Auditoría del propio SET-14 (repegado) encontró el mismo patrón de
callers-cero que SET-12/13 para `LabelVariable`/`LabelData`/
`marketing_claim_validation_policy`-equivalente — pero, a diferencia de
esos dos, **no había ninguna capacidad real sin conectar que cablear**.
Rastreando el pipeline "bueno" de INV-26
(`InventoryLabelPrintService`, permission-gated, auditado) hasta su cable
en vivo (`frontend/desktop/modules/inventory/composition.py`) se confirmó
que se construye ahí **sin gateway**, cayendo en
`InMemoryPrintGateway()` — hoy, imprimir una etiqueta en el módulo de
inventario en vivo registra éxito y no imprime físicamente nada. Ningún
`InventoryPrintGateway` real existe en todo el repo, igual que
`DocumentRendererPort`. Presentado al usuario vía AskUserQuestion (cerrar
como límite vs. construir un gateway real); el usuario, a diferencia de
las rondas anteriores, **eligió explícitamente construirlo**, aceptando
que esta es la primera ronda de toda la sesión con E/S de red/serial real
y protocolo de cable real (ZPL), sin impresora física disponible en este
entorno para validar contra ella.

**Mitigación del riesgo de "sin hardware"**: ZPL y ESC/POS son protocolos
deterministas y bien documentados (ZPL, basado en texto, sin dependencia
de imaging); la corrección se verifica con aserciones de string exacto en
tests, exactamente la misma disciplina bajo la que ya opera
`core/ticket_escpos_renderer.py` (en producción, sin que esta sesión haya
tenido nunca acceso a hardware tampoco). Esta ronda no cruza una
categoría de riesgo nueva.

**Reutilización real, no reinvención** (decisiones clave):
- **Transporte**: `core/services/printer_service.py::PrintTransport` —
  ya real, ya en producción para tickets (`_send_tcp`/`_send_serial`/
  `_send_win32`/`_send_file`) — reutilizado tal cual, cero código nuevo
  de sockets/serial.
- **Resolución de impresora**: en vez de inventar configuración nueva,
  las etiquetas se enrutan con la MISMA infraestructura real de
  `PrintRoute`/device_management que SET-12 ya cableó para tickets de
  Ventas (`DocumentOutputPrintRoutingClient`, ruteo real con failover de
  SET-8) — exactamente la razón por la que SET-14 registró los 6 valores
  `DocumentType` de etiqueta (`LOT_LABEL` etc.) desde el principio. Un
  admin configura una impresora de etiquetas real vía la página
  Dispositivos YA VIVA (registrar un `Device` `LABEL_PRINTER` + una
  `PrintRoute` para p. ej. `LOT_LABEL`) — cero UI nueva de Configuración.
- **Barcode/QR para ESC/POS**: `core/ticket_escpos_renderer.py` ya tiene
  generación real de raster Code-128/QR (vía `qrcode`/`PIL`, dependencia
  ya viva) — reutilizada por composición, no duplicada.

**Cambio de comportamiento deliberado y declarado explícitamente, no
oculto**: hoy imprimir una etiqueta SIEMPRE reporta éxito (el stub en
memoria no puede fallar). Tras este cambio, imprimir sin una
ruta+dispositivo configurados **falla con claridad**
(`PrintDeliveryError`, ya capturado por `print_service.py` y convertido
en un `PRINT_DELIVERY_FAILED` auditado — nunca un crash). Esto es
correcto para un gateway real — fingir éxito silenciosamente cuando nada
está configurado es peor que un fallo honesto — pero es un cambio visible
frente al stub-siempre-exitoso de hoy, hasta que un admin configure una
ruta.

**Construido**: nuevo paquete
`backend/infrastructure/hardware/label_rendering/`:
`zpl_renderer.py::render_zpl` (ZPL II real: `^XA`/`^FO`/`^A0N`/`^FD…^FS`
por título+línea, `^BY`+`^BCN,60,Y,N,N` si hay barcode,
`^BQN,2,4`+`^FDLA,…` si hay QR, `^PQ{copies}`, `^XZ`);
`escpos_label_renderer.py::render_escpos_label` (reutiliza las constantes
de comando de `core.ticket_escpos_renderer` + una instancia de
`TicketESCPOSRenderer` para el raster de barcode/QR, `copies` repetido
del lado del llamador ya que las etiqueteras térmicas típicamente no
tienen comando nativo de cantidad); `text_label_renderer.py::render_text_label`
(texto plano, preview/fallback sin hardware);
`network_label_gateway.py::NetworkLabelPrintGateway` (implementa
`InventoryPrintGateway`: mapea `LabelType`→`DocumentType` de etiqueta,
resuelve dispositivo real vía `DocumentOutputPrintRoutingClient`
—`printer_ref` como override explícito de código de dispositivo si se
provee—, renderiza según `label_format`, mapea `ConnectionProfile`→
`(TransportType, destino, baud)` y entrega con
`PrintTransport.send()` real; cualquier fallo se envuelve como
`PrintDeliveryError`, el único límite de excepción que este gateway
puede cruzar). `frontend/desktop/modules/inventory/composition.py`: las
2 lambdas `label_print_service_factory` ganan
`gateway=NetworkLabelPrintGateway(c)` — único cambio de producción,
todo lo demás en `InventoryLabelPrintService` (permisos, auditoría,
eventos) queda intacto.
Sin migración nueva, sin UI de Configuración nueva — Dispositivos/SET-7/
SET-8 ya cubren todo lo necesario para registrar una impresora de
etiquetas real.
**Fuera de alcance, declarado explícitamente**: validar contra una
impresora física real (imposible en este entorno; corrección a nivel de
protocolo, igual que `ticket_escpos_renderer.py`); cortar `labels/
generador_etiquetas.py` (v11) o `modulos/etiquetas.py` (v13 UI) —
ambos intactos; cablear `DocumentRendererPort` en sí (la capacidad propia
de etiquetas de document_output sigue sin callers de aplicación incluso
después de esto — esta ronda apuntó a INV-26 específicamente, el
pipeline que sí está vivo).
**Tests**: 33 nuevos — `render_zpl` (11, aserciones de string ZPL
exacto), `render_escpos_label` (6, estructural), `render_text_label` (4,
exacto), `NetworkLabelPrintGateway` (12, contra SQLite real con
`PrintTransport.send` interceptado — nunca abre un socket real —
incluye ruteo NETWORK/SERIAL con los valores reales de
`ConnectionProfile`, override explícito de dispositivo, sin ruta
configurada, dispositivo inactivo, fallo de transporte, tipo de conexión
no soportado, formato de etiqueta no soportado, y 2 pruebas de punta a
punta a través de `InventoryLabelPrintService.print_label` real
confirmando el cableado del composition root). Regresión completa
limpia: 277 tests en el alcance directamente relevante (labels + gateway
+ document_output). **Nota honesta**: la corrida más amplia de
`tests/integration/inventory/` mostró 10 fallos/errores preexistentes
(`test_inventory_analytics.py`, `test_legacy_reader_repoints.py`,
`test_inventory_ui_presenter.py::test_analytics_kpis_and_export`) por
tablas ausentes (`products`, `loss_cases`) en esos fixtures específicos —
confirmado que ninguno referencia `composition.py`/el gateway de
etiquetas en absoluto, preexistentes y no relacionados con este cambio,
no corregidos aquí (fuera de alcance). **Siguiente**: 4 secciones aún de
solo lectura; §65-68 Resumen dashboard y §70 clasificación formal de
legacy siguen abiertos; dirigir bytes reales de tickets al dispositivo
resuelto por ruteo (SET-12) sigue pendiente — este SET-14 es la PRIMERA
vez que ese patrón se completó de punta a punta para CUALQUIER tipo de
documento en todo el track. **Advertencia permanente para quien retome
esto**: ningún byte generado aquí fue validado contra una impresora
física real — antes de confiar en producción, un admin con hardware real
debe confirmar que `render_zpl`/`render_escpos_label` producen salida
aceptada por su impresora concreta.

## Avance SET-15 — Sorteos: Integración con Sweepstakes, Plantilla, Boleto, Reimpresión

**Hecho** — activa `DocumentType.SWEEPSTAKES_TICKET` (reservado desde
SET-11, sin uso hasta ahora), integrando Document Output con el dominio
real de rifas en `core/services/loyalty_service.py::LoyaltyService`
(validadores financieros reales de §FASE 3) y
`core/tickets/raffle_ticket_renderer.py`. Ver
`migrations/MIGRATION_LOG.md` (entrada "SET-15 — sin migración nueva")
para el detalle completo. Resumen:

- **Sin migración 216, a propósito** — ni el boleto ni el puerto de
  integración necesitaron esquema nuevo.
- **Boleto** — `SweepstakesTicketData`, generaliza el payload real que
  `LoyaltyService._raffle_print_payload()` ya construye (raffle_name/
  ticket_number/prize/draw_date/cliente/venta), reutilizando `TicketParty`
  (SET-12) para el cliente. 4 códigos de sección nuevos
  (`RAFFLE_TITLE`/`TICKET_NUMBER`/`PRIZE`/`DRAW_DATE`), completando el
  vocabulario de `RAFFLE_BLOCK_ORDER` legacy que `DEFAULT_BLOCK_ORDER`
  (SET-12) aún no cubría.
- **Plantilla** — sin entidad nueva: `DocumentTemplate`/
  `DocumentTemplateVersion` (SET-11) ya sirven para
  `SWEEPSTAKES_TICKET` sin modificación. Probado con ciclo de vida
  completo y persistencia real.
- **Integración con Sweepstakes** — `sweepstakes_ports.py::
  SweepstakesTicketPort`, **sin implementación real, a propósito** — a
  diferencia del adaptador real de ruteo en SET-12,
  `LoyaltyService` todavía usa ids enteros legacy (no migrado a UUIDv7),
  así que puentearlo de forma segura es una decisión que le corresponde a
  quien migre el dominio de Lealtad/Sorteos, no algo que Document Output
  deba resolver unilateralmente hoy.
- **Reimpresión** — sin código nuevo: `reprint_policy` (SET-12) ya era
  agnóstico al `document_type`. Probado explícitamente para confirmarlo
  — coherente con que `LoyaltyService` ya distingue reimpresión explícita
  de idempotencia en el handler de venta completada.
- **`LoyaltyService`/`RaffleTicketESCPOSRenderer` no se tocaron.**
- **Tests**: `tests/unit/document_output/` — 18 tests nuevos
  (`test_sweepstakes_ticket_data.py`,
  `test_sweepstakes_integration_and_reprint.py`). `tests/integration/
  document_output/test_sweepstakes_document_persistence.py` — 2 tests
  contra SQLite real. **Total tras SET-15 (Settings + Device Management +
  Document Output): 716 tests verdes.**

### Continuación (2026-08-23) — corrección de una auditoría propia: el bloqueo original de SET-15 no existía, sales_pos gana boletos de rifa reales

Auditoría del propio SET-15 (repegado) encontró, otra vez, cero callers
de aplicación para `SweepstakesTicketData`/`sweepstakes_ports.
SweepstakesTicketPort` — pero esta vez la investigación llevó a algo más
significativo que un simple "sin conectar": **la razón documentada
originalmente para no construir un adaptador real resultó ser
incorrecta**. El docstring de `sweepstakes_ports.py` afirmaba que los
métodos de rifa de `LoyaltyService` "siguen usando ids enteros legacy
(`venta_id: int`)" — leer el CUERPO real de `issue_raffle_tickets_for_sale()`/
`process_raffles_for_sale()` mostró que convierten cada id a string de
inmediato y NUNCA hacen join contra una tabla legacy por `venta_id`:
elegibilidad, generación y consulta de boletos están todas indexadas por
`(raffle_id, venta_id)` como strings opacos en `raffle_tickets`.
`evaluate_raffle_sale_eligibility()` incluso tiene un comentario propio
confirmándolo: `# Identidad como str (UUIDv7): comparar contra los sets
de elegibles (TEXT).` Un `sale.id` UUIDv7 real funciona ahí con **cero
puente de identidad** — a diferencia de los puntos de fidelidad de
SET-13, que sí necesitaban `EnsureLegacyCustomerBridgeUseCase`.

Mientras tanto, `core/services/sales_service.py::_execute_sale_core` (el
viejo camino REST de cierre de venta) ya emite E imprime boletos de rifa
reales (`LoyaltyService.issue_raffle_tickets_for_sale()` →
`PrinterService.print_raffle_ticket()`, ambos reales y ya cableados a la
cola/transporte real). `sales_pos` (el único POS de escritorio vivo desde
SALES-22) tenía **cero** integración de rifas — la misma brecha de
paridad camino-viejo-sí/camino-nuevo-no que SET-13 cerró para mensajes de
fidelidad.

Diseño confirmado con el usuario: **emitir en el checkout** (best-effort,
coincide con cuándo se evalúa naturalmente la elegibilidad en el camino
legacy), **imprimir vía la acción de reimpresión existente** (F12) junto
al recibo — sin cablear `printer_service` nuevo en el checkout, coherente
con el hallazgo de SET-12 de que el checkout nunca imprime nada hoy.
**Tradeoff declarado**: igual que el recibo mismo, los boletos de rifa se
imprimen de nuevo cada vez que se presiona F12 (sin candado de "ya
impreso") — coincide exactamente con el comportamiento ya existente del
recibo, no una inconsistencia nueva.

**Construido**: `repositories/loyalty_repository.py::get_tickets_for_venta()`
(nuevo — `get_tickets_for_sale` exige `raffle_id` conocido; la
reimpresión necesita "todo boleto de esta venta, en cualquier rifa").
`core/services/loyalty_service.py::LoyaltyService.get_printable_tickets_for_sale()`
(nuevo — reutiliza el método privado `_raffle_print_payload()` ya
existente, ahora llamado desde DENTRO de la clase, no alcanzado desde
afuera). Nuevo `backend/infrastructure/integrations/
sales_sweepstakes_client.py::SalesSweepstakesClient` (mismo molde que
`sales_loyalty_client.py`, pero sin necesitar ningún puente de
identidad). `CheckoutSaleUseCase.execute()` gana emisión best-effort
(mismo patrón ya establecido para `cash_effects_error` en ese mismo
archivo — nunca deshace una venta completada). `ReprintReceiptUseCase.execute()`
(ya tocado por SET-12/13) gana impresión best-effort de cualquier boleto
ya emitido para la venta, vía el mismo `PrinterService.print_raffle_ticket()`
real que el camino legacy ya usa — un boleto con payload malo nunca
bloquea el recibo ni a los demás boletos.
Sin migración nueva, sin UI de Configuración nueva.
**Corrección documentada in situ**: el docstring de `sweepstakes_ports.py`
fue actualizado para señalar explícitamente que su razón original
("ids enteros legacy") no se sostenía al releer el código, preservando el
texto original tachado para que quien lo retome entienda qué cambió y
por qué — la razón real por la que ese puerto específico sigue sin
adaptador es que tiene una forma distinta (boleto por número, para el
pipeline de plantillas de document_output) a la que este cutover
necesitaba (emitir+imprimir vía el renderer legacy ya real).
**Tests**: 18 nuevos — `tests/test_raffle_sales_pos_cutover.py` (10:
prueba directa de que los métodos de rifa funcionan con identidad UUIDv7
real —incluyendo un test que demuestra que NO se necesita ninguna fila en
tabla legacy para `venta_id`—, más `get_tickets_for_venta`/
`get_printable_tickets_for_sale`), `tests/unit/test_sales_sweepstakes.py`
(8: `SalesSweepstakesClient`, cutover de `CheckoutSaleUseCase` incluyendo
"la emisión falla → el checkout igual tiene éxito", cutover de
`ReprintReceiptUseCase` incluyendo "sin boletos emitidos → sin cambio de
comportamiento" y "la impresora falla → el recibo igual se imprime").
Regresión completa limpia: 710 tests pasando en el alcance completo
(document_output + sales + rifas/fidelidad legacy). **Nota honesta**: 2
fallos preexistentes encontrados en `tests/test_raffle_rules_engine.py`/
`tests/test_raffle_financial_safety.py` (una violación de constraint NOT
NULL no relacionada y una discrepancia de aritmética en el ledger
financiero), confirmados en aislamiento como no relacionados con este
cambio (ninguno invoca código nuevo de esta ronda) — no corregidos, fuera
de alcance. **Siguiente**: 4 secciones aún de solo lectura; §65-68 Resumen
dashboard y §70 clasificación formal de legacy siguen abiertos; dirigir
bytes reales al dispositivo resuelto por ruteo (SET-12) sigue pendiente
de hardware real; construir un adaptador real para
`SweepstakesTicketPort` específicamente (forma distinta, sin caller
todavía) sigue abierto, igual que `DocumentRendererPort`.

## Avance SET-16 — Numeración: Sequences, Reservas, Reset, Idempotencia

**Hecho** — cierra el riesgo "Folio duplicado" que la entrada de SET-10
en `MIGRATION_LOG.md` ya había marcado explícitamente. Ver esa entrada
("216_document_numbering_schema") para el detalle completo. Resumen:

- **Ya existían dos generadores de folio en vivo** —
  `backend/domain/procurement/value_objects.py::DocumentNumber` (calculado
  con un escaneo `MAX(document_number)+1` real contra la tabla de
  documentos, con ventana de carrera) y
  `backend/domain/finance/value_objects/document_number.py::DocumentNumber`
  (wrapper opaco sin generación propia). **Ninguno se tocó.**
- **Sequences** — `DocumentNumberSequence`, un contador persistido por
  prefijo (`document_number_sequences`, migración 216) en vez de escanear
  una tabla de documentos.
- **Reservas** — `reserve_next()` + `document_number_reservations`
  (`UNIQUE(sequence_id, operation_id)` + `UNIQUE(document_number)`
  global) — cada reserva exitosa queda auditada, no solo contada.
- **Reset** — `SequenceResetPolicy` (NEVER/YEARLY/MONTHLY/DAILY),
  generaliza el reset anual implícito que Procurement ya tenía.
  `reserve_next()` reinicia automáticamente al cruzar de periodo;
  `force_reset()` es la corrección administrativa manual, distinta.
- **Idempotencia** — `sequence_reservation_policy.reserve_with_idempotency()`:
  una reserva repetida con el mismo `operation_id` devuelve el mismo
  número sin avanzar el contador — mismo patrón que
  `configuration_values.operation_id` (SET-3) y `print_jobs.operation_id`
  (SET-11).
- **Procurement/Finance no se tocaron.** Esta SET construye el generador
  seguro; cortar ambos consumidores legacy al mismo tiempo queda para una
  SET futura con autorización explícita.
- **Tests**: `tests/unit/document_output/` — 18 tests nuevos
  (`test_document_number_sequence.py`,
  `test_sequence_reservation_policy.py`). `tests/integration/
  document_output/test_document_numbering_repositories.py` — 8 tests
  contra SQLite real. **Total tras SET-16 (Settings + Device Management +
  Document Output): 742 tests verdes.**

### Continuación (2026-08-23) — Procurement cortado al generador seguro; se encontró y cerró un race real en el propio diseño de SET-16

Auditoría del propio SET-16 (repegado) encontró, de nuevo, cero callers
de aplicación para `DocumentNumberSequence`/`reserve_with_idempotency` —
pero, a diferencia de SET-12/13/15, esta vez SÍ existía un consumidor
legacy real y vivo (`DocumentSequenceRepository.next_number()`,
`backend/infrastructure/db/repositories/procurement/support_repositories.py`,
llamado por 6 casos de uso reales: órdenes de compra, requisiciones,
cotizaciones, facturas, devoluciones, compras directas) con un race
condition real: el propio docstring del método ya admitía que dos
lectores concurrentes del `MAX(document_number)` pueden calcular el mismo
"siguiente" número, dependiendo por completo de `UNIQUE(document_number)`
para atrapar la colisión DESPUÉS del hecho (un `sqlite3.IntegrityError`
crudo en quien pierde la carrera). El propio `DocumentNumberSequence` de
SET-16 fue construido específicamente para reemplazar esto — su docstring
cita textualmente el riesgo ya señalado en `MIGRATION_LOG.md` desde
SET-10 ("Folio duplicado al introducir DocumentNumberSequence mientras
next_number() legacy sigue activo") — pero nunca se conectó. El wrapper
`DocumentNumber` de Finance, el otro artefacto legacy que el audit
original de SET-16 nombraba, resultó ser un simple wrapper de string
validado, no un generador — nada que cortar ahí.

**Un problema de corrección real encontrado durante el diseño, no
asumido como resuelto**: `SqliteDocumentNumberSequenceRepository.save()`
(la propia infraestructura de SET-16) persiste lo que la ENTIDAD calculó
en Python — un UPSERT simple, no un incremento atómico. Cortar Procurement
de forma ingenua ("leer la secuencia → `entity.reserve_next()` → `save()`")
habría reproducido EXACTAMENTE el mismo race, solo que contra una tabla
más pequeña en vez de la tabla de documentos en vivo — no una corrección
real. Esta app es multi-estación (`Device`/`Workstation`, multi-sucursal),
así que escritores concurrentes desde procesos de SO distintos contra el
mismo archivo SQLite es un escenario real, no teórico.

**La corrección**: un solo `UPDATE ... RETURNING` atómico (SQLite 3.35+)
que avanza el contador Y ejecuta el rollover de periodo en la MISMA
escritura:
```sql
UPDATE document_number_sequences
   SET current_value = CASE WHEN period_key = ? THEN current_value + 1 ELSE 1 END,
       period_key = ?, updated_at = ?
 WHERE id = ?
 RETURNING current_value
```
Rastreado a través de escritores concurrentes: SQLite serializa las
escrituras a la misma fila; quien commitee primero evalúa el CASE contra
el estado REAL de la fila, así que un segundo intento de rollover
concurrente ve correctamente el `period_key` ya rodado y suma desde 1 en
vez de colisionar también en 1. Sin read-modify-write en Python, sin
retry loop — el race se cierra a nivel SQL, no se asume resuelto por el
nivel de aislamiento de transacción que esta app no usa explícitamente en
ningún otro lugar. Probado explícitamente con un test que simula un
rollover concurrente (rueda a un periodo nuevo, luego reserva de nuevo con
el MISMO periodo objetivo, confirma que la segunda reserva cae en 2, no en
un 1 colisionante).

**Construido**: `SqliteDocumentNumberSequenceRepository.reserve_and_get()`
(nuevo — genérico, no específico de Procurement, vive junto al
repositorio existente de SET-16). `DocumentSequenceRepository.next_number()`
reescrito por dentro (firma y tipo de retorno SIN CAMBIOS — cero
call-sites de los 6 casos de uso necesitaron tocarse): resuelve o
bootstrapea la secuencia real por prefijo, reserva atómicamente, devuelve
el `DocumentNumber` de Procurement de siempre (`PREFIX-YYYY-NNNNNN`,
confirmado byte-idéntico). **Bootstrap sin colisión**: primer uso de un
prefijo tras el corte — sin fila `document_number_sequences` todavía — se
siembra desde el MISMO scan `MAX(document_number)` que el método ya hacía
(reutilizado, no reinventado), así el contador continúa exactamente donde
el scan legacy se habría quedado. Un doble-bootstrap concurrente es
seguro: `document_number_sequences.prefix` ya es `UNIQUE`, así que el
INSERT perdedor falla limpio y ese llamador simplemente vuelve a
consultar la fila del ganador en vez de propagar el error.
**Fixture compartida de tests actualizada**: `tests/integration/procurement/
conftest.py::proc_conn` (y 4 fixtures locales más en archivos de UI/
integraciones que no pasaban por `conftest.py`) ahora también crean el
esquema de numeración (migración 216) — sin esto, los ~20 tests de
procurement que ya ejercitan `next_number()` habrían fallado con "no such
table" tras el corte; confirmado corrigiendo y re-verificando los 96 tests
de `tests/integration/procurement/` en verde.
**Límite real de diseño encontrado y documentado, no oculto**: a
diferencia del scan legacy (que releía la tabla en vivo cada vez, así que
toleraba un argumento `year` fuera de orden), la nueva fila-única-por-prefijo
asume que `year` solo avanza hacia adelante entre llamadas — exactamente
lo que `_year()` (`date.today().year`) siempre da en uso real. Documentado
explícitamente en el docstring del método, no es un escenario que ningún
llamador real produzca.
**Fuera de alcance, declarado**: cablear `document_number_reservations`/
idempotencia — `next_number(prefix, year)` no tiene parámetro
`operation_id` y ninguno de los 6 call sites lo provee hoy; agregarlo
sería un cambio de firma pública más grande, no necesario para cerrar el
race (el `UPDATE...RETURNING` atómico ya lo cierra por sí solo).
**Tests**: 12 nuevos — `reserve_and_get()` (4, incluye la prueba de
concurrencia del rollover), `DocumentSequenceRepository.next_number()`
(8: bootstrap continúa numeración existente sin colisión, prefijo nuevo
arranca en 1, segunda llamada reutiliza la secuencia ya bootstrapeada
—sin re-scan—, formato byte-idéntico al legacy, años distintos avanzan
correctamente hacia adelante, prefijo desconocido no toca almacenamiento,
doble-bootstrap concurrente se resuelve al ganador real). Regresión
completa limpia: 413 tests en el alcance directamente relevante
(procurement completo + document_output). **Nota honesta**: 13 fallos
preexistentes encontrados en una corrida más amplia (`grep`-confirmados
sin ninguna referencia a `next_number`/`DocumentSequenceRepository`/
`document_number_sequences` — tests de layout Qt, una tabla
`inventory_balances` ausente, un atributo `capabilities` faltante),
ninguno relacionado con este cambio, no corregidos, fuera de alcance.
**Siguiente**: 4 secciones aún de solo lectura; §65-68/§70; dirigir bytes
reales al dispositivo resuelto por ruteo (SET-12) sigue pendiente de
hardware real; idempotencia de numeración vía `document_number_reservations`
sigue sin conectar (cambio de firma pública, deliberadamente diferido).

## Avance SET-17 — Customer Display: Displays, Layouts, Modes, Gateway

**Hecho** — abre `backend/domain/customer_display/`, el cuarto y último
bounded context nuevo que el título de este plan anticipa. Ver
`migrations/MIGRATION_LOG.md` (entrada "217_customer_display_schema")
para el detalle completo. Resumen:

- **Único artefacto real previo**: `backend/application/sales/queries/
  customer_display_query_service.py::CustomerDisplayQueryService`
  (proyección de solo lectura sobre `Sale`, Ventas solo publica estado,
  nunca controla la pantalla). Clasificado en la auditoría SET-0 como
  "REUSE como base de diseño" — no se tocó; esta SET construye el resto
  (`CustomerDisplay`/`DisplayLayout`) desde cero.
  `ContentCampaign`/`AdvertisingSlot` quedan para SET-18+.
- **Displays** — `CustomerDisplay` (registro por estación de trabajo,
  `workstation_id` FK a `workstations` de Settings). `current_mode` sin
  máquina de estados — a diferencia de `PrintJob`, el modo de pantalla no
  tiene transiciones restringidas por regla de negocio propia.
- **Modes** — `CustomerDisplayMode` (IDLE/CART/PAYMENT_PENDING/
  THANK_YOU), generaliza el diccionario legacy `_SCREEN_BY_STATUS`.
- **Layouts** — `DisplaySection`/`DisplayLayout`
  (`CustomerDisplaySectionCode`: CUSTOMER_NAME/ITEMS/SUBTOTAL/DISCOUNT/
  TOTAL/MESSAGE/LOGO), independiente del `DocumentSectionCode` de
  Document Output pese a la forma similar. A lo sumo un layout ACTIVE
  por modo (índice único parcial). `display_layout_resolution_policy::
  resolve_layout()` — más simple que el ruteo de impresión (SET-8), sin
  ámbito por sucursal.
- **Gateway** — `CustomerDisplayGatewayPort`, sin implementación real a
  propósito (SET-0 ya confirmó cero hardware/consumidor real en el
  repo). `display_state_push_policy::push_state()` filtra el contenido
  al layout resuelto antes de enviarlo. Probado con un gateway falso.
- **`CustomerDisplayQueryService` no se tocó.**
- **Tests**: `tests/unit/customer_display/` — 27 tests nuevos.
  `tests/integration/customer_display/test_customer_display_repositories.py`
  — 8 tests contra SQLite real. **Total tras SET-17 (Settings + Device
  Management + Document Output + Customer Display): 777 tests verdes.**

### Continuación (2026-08-25) — Ventas cortado a un Gateway real de segunda pantalla; corrigió un supuesto erróneo del propio plan sobre el bootstrap de Workstation

Auditoría (repegado del prompt original SET-17) encontró, de nuevo, cero
callers de aplicación para `CustomerDisplayGatewayPort`/
`display_state_push_policy` — pero a diferencia de SET-14 (impresoras
físicas), el propio docstring de `CustomerDisplayGatewayPort` nombra
explícitamente *"una vista web de segunda pantalla real"* como validación
suficiente: no hay frontera de hardware/protocolo de bytes que bloquee
este corte, a diferencia de ZPL/ESC-POS. `CustomerDisplayQueryService`
(Ventas) ya era una proyección real y probada de "qué debería mostrar
esta pantalla ahora mismo" — construida en el SET-0/SET-17 original,
nunca conectada a ningún consumidor. Presentado vía AskUserQuestion; el
usuario eligió construir la ventana real.

**Construido**:
- `frontend/desktop/modules/sales_pos/customer_display_window.py::
  CustomerDisplayWindow` — una segunda ventana Qt real (testeable
  offscreen), maximizada en el segundo monitor cuando existe
  (`QGuiApplication.screens()`), ventana normal si no. `render_content(mode,
  content)` solo actualiza los widgets para las claves presentes en
  `content` — misma disciplina de filtrado que `display_state_push_policy.
  push_state()` ya aplica; la ventana nunca fabrica contenido para una
  sección que el layout desactivó/omitió.
- `QtCustomerDisplayGateway` — implementación real de
  `CustomerDisplayGatewayPort`, delega a la ventana.
- `backend/infrastructure/integrations/sales_customer_display_client.py::
  SalesCustomerDisplayClient` — cliente de integración (mismo patrón que
  `sales_sweepstakes_client.py`), bootstrapea perezosamente un
  `CustomerDisplay` y un `DisplayLayout` por modo en el primer uso (mismo
  patrón "fila real persistida en el primer uso" que `next_number()`
  estableció en SET-16) — layout por defecto: las 6 secciones no-LOGO
  habilitadas, LOGO deshabilitado (sin infraestructura real de logo,
  hallazgo confirmado desde la ronda Empresa/SET-25).
- Cableado real: `sales_pos/composition.py` registra
  `CustomerDisplayQueryService` como query service + un command handler
  `push_customer_display`; `CashierBar` gana un botón checkable "🖥
  Pantalla del cliente" (Signal, sin lógica de negocio);
  `SalesPosWorkspace` posee la ventana, la abre/cierra al toggle, y
  `_refresh()` (ya se ejecuta tras cada mutación de carrito/venta) empuja
  el estado — envuelto en try/except, mismo "best-effort, nunca bloquea
  la operación real" que cada `_try_*` de `receipt_use_cases.py` ya
  estableció para SET-12/13/15.

**Corrección al propio plan aprobado, encontrada al escribir los tests de
este round, no asumida como resuelta**: el plan original proponía, si no
había `Workstation` activa, "acuñar un UUIDv7 nuevo" para no bloquear la
función. `customer_displays.workstation_id` tiene un FK real
(`REFERENCES workstations(id)`, migración 217) — un UUID huérfano falla
de inmediato con `sqlite3.IntegrityError` en cuanto `foreign_keys` está
activo (siempre lo está en este repo, confirmado escribiendo el primer
test de bootstrap). Como `workstations.branch_id` a su vez referencia
`sucursales(id)` (migración 210), y toda venta real ya exige una
`branch_id` real (`SalesPosPresenter.current_branch_id()`, de la sesión
activa), el cliente ahora bootstrapea una `Workstation` real y mínima
contra esa sucursal ya real cuando no existe ninguna activa — no un
segundo huérfano — mismo patrón "bootstrapea una fila real" que el propio
bootstrap de `DisplayLayout`/`CustomerDisplay` ya usa. Solo cuando no hay
`branch_id` disponible (defensivo, no debería ocurrir en una sesión de
venta real) lanza el nuevo `CustomerDisplayBootstrapError` en vez de
intentar un INSERT que ya se sabe que viola el FK.

**Tests**: 23 nuevos — `SalesCustomerDisplayClient` contra SQLite real
(11: bootstrap de display/layout, reutilización sin duplicados, bootstrap
de Workstation real contra la sucursal dada, error claro sin `branch_id`,
filtrado de contenido, LOGO nunca aparece, persistencia de modo, venta
real end-to-end); `CustomerDisplayWindow`/`QtCustomerDisplayGateway` (6,
Qt real offscreen); corte completo a través de la composición real de
`sales_pos` (3: mutación de carrito empuja CART real con líneas reales,
checkout empuja THANK_YOU, un gateway que falla no corrompe el estado ya
bootstrapeado para el siguiente push); toggle de la barra de cajero +
no-bloqueo de `_refresh()` (3, se suman a los 9 ya existentes en
`test_sales_pos_workspace.py`, ahora 12). **Nota honesta**: durante la
verificación se encontró y corrigió una violación real al propio
guardrail de estilo de `sales_pos`
(`test_no_component_sets_an_inline_stylesheet` — 3 llamadas a
`setStyleSheet()` en `customer_display_window.py` para tamaños de
tipografía, reemplazadas por `QFont`/`setPixelSize()`, no por CSS
inline). Regresión enfocada limpia, confirmada con una corrida directa de
`pytest` (nunca estimada): **979 tests verdes** en el alcance
directamente relevante (Settings + Device Management + Document Output +
Customer Display + `sales_pos`, unit + integration, incluyendo los 23
nuevos). Una corrida
amplia de `tests/architecture/` encontró 6 fallos preexistentes sin
relación (verificados individualmente, no solo por grep): una ruta
relativa rota en `test_permission_catalog_matches_menu_modules.py` (bug
del propio test, no del código); una regresión de conteo `legacy_id`
(baseline 2, actual 10) en archivos que no forman parte de este cambio
(confirmado por grep: ninguno de los archivos tocados en este round
contiene la cadena); cientos de PK TEXT preexistentes sin NOT NULL en
prácticamente todo el esquema (`test_text_pk_not_null.py`, incluye
`historico_puntos.id` admitiendo NULL); decenas de `CREATE TABLE` fuera
de `migrations/` en `backend/infrastructure/db/schema/*` — la forma
establecida en que TODO este repo construye su schema, no algo de este
round; un `sqlite3.connect()` crudo preexistente en
`tools/crm/backfill_legacy_customers.py`. Ninguno relacionado con este
cambio, ninguno corregido, fuera de alcance.

**Fuera de alcance, declarado**: contenido publicitario/pantalla-idle
(SET-18, sigue sin pantalla real que genere impresiones); nuevo CRUD de
Configuración para displays/layouts — el bootstrap por defecto basta este
round, la página de solo lectura ya existente (`_page_pantalla_cliente`)
muestra lo que se bootstrapea sin cambios; cualquier cambio a
`CustomerDisplayQueryService` en sí (reutilizado exacto, sin tocar).

## Avance SET-18 — Contenido y publicidad: Content, Campaigns, Placements, Approval, Metrics

**Hecho** — completa `backend/domain/customer_display/` con
`ContentCampaign`/`AdvertisingSlot`, lo que SET-0/SET-17 ya habían dejado
explícitamente pendiente. Ver `migrations/MIGRATION_LOG.md` (entrada
"218_content_and_advertising_schema") para el detalle completo. Resumen:

- **Content** — `Content` (imagen/video/texto/HTML, `duration_seconds`),
  sin historial de versiones.
- **Campaigns**/**Approval** — `ContentCampaign`, máquina de 7 estados
  que replica exactamente `DocumentTemplateVersionStatus` (SET-11) — la
  misma disciplina de revisión antes de estar en vivo, aplicada a
  contenido publicitario.
- **Placements** — `AdvertisingSlot` (reutiliza `CustomerDisplayMode` de
  SET-17) + `CampaignPlacement`, que replica exactamente
  `WorkstationDeviceAssignment` (SET-7): assign/unassign, a lo sumo una
  asignación activa por slot. **Approval gatea Placements**:
  `assign_placement()` exige campaña ACTIVE — contenido sin aprobar
  nunca llega a la pantalla.
- **Metrics** — `ContentImpression` (registro append-only) +
  `summarize_impressions()` (conteo/duración/promedio). Honesto sobre su
  alcance: ninguna pantalla real genera impresiones todavía, misma
  situación que el Gateway de SET-17.
- **`CustomerDisplayQueryService`/`CustomerDisplay`/`DisplayLayout` no se
  tocaron.**
- **Tests**: `tests/unit/customer_display/` — 56 tests nuevos.
  `tests/integration/customer_display/` — 14 tests nuevos. **Total tras
  SET-18 (Settings + Device Management + Document Output + Customer
  Display): 847 tests verdes.**

### Continuación (2026-08-28) — CRUD real de Contenido/Campañas/Slots/Asignaciones + rotación real de anuncios en la pantalla idle de sales_pos

Auditoría (repegado de "SET-18 — Contenido y publicidad") encontró, de
nuevo, cero callers para `Content`/`ContentCampaign`/`AdvertisingSlot`/
`CampaignPlacement`/`ContentImpression` — dominio + 5 repositorios Sqlite
reales, cero UI, cero uso real. A diferencia de SET-12/16, esto no
reemplaza nada legacy: es capacidad genuinamente nueva. Pero SET-17 (la
ronda anterior) le dio a `sales_pos` una ventana real de segunda
pantalla cuyo estado IDLE hoy no renderiza nada — exactamente donde
pertenece el contenido publicitario aprobado. Presentado vía
AskUserQuestion (dejarlo como capacidad de dominio / cortar solo el lado
de la pantalla / corte completo con CRUD); el usuario eligió el corte
completo — el alcance más grande de cualquier ronda de este track.

**Una corrección de diseño real encontrada durante la planeación**: la
primera versión del plan condicionaba la rotación de anuncios a
`self._sale_id is None`. Eso está mal para cómo `sales_pos` realmente
funciona: `SalesPosWorkspace._start_new_sale()` arranca una venta DRAFT
nueva en `showEvent` y de nuevo después de cada checkout/suspensión/
cancelación, así que `self._sale_id` está casi siempre asignado;
`_SCREEN_BY_STATUS` (SET-17) mapea DRAFT/ACTIVE → `"CART"`, nunca
`"IDLE"` — el modo `IDLE` literal casi nunca se alcanza en operación
normal. El verdadero "idle" para un cajero es un **carrito vacío** (una
venta DRAFT/ACTIVE con cero líneas), no un `sale_id` ausente — la
rotación usa eso en su lugar.

**Construido**:
- Dominio: `ContentCampaign.approve()` ganó el mismo chequeo de
  segregación de funciones que la ronda repegado de SET-1 agregó a
  `DocumentTemplateVersion.approve()` (el propio docstring de esta
  entidad ya decía replicar esa forma, pero el chequeo nunca se copió) +
  `update_schedule()`. `AdvertisingSlot` ganó `update_display_order()`.
  `Content` ganó `update_details()`.
- `backend/application/customer_display/` (nuevo — primera capa de
  aplicación PROPIA de customer_display; el `SalesCustomerDisplayClient`
  de SET-17 vive en las integraciones de Ventas porque Ventas es dueña
  de los datos de venta que proyecta, pero el contenido publicitario es
  dominio propio de customer_display):
  `queries/advertising_query_service.py::AdvertisingQueryService.
  resolve_active_ads(mode)` — resuelve slot activo → placement activo →
  campaña ACTIVE dentro de su ventana `starts_at`/`ends_at` → contenido
  activo. **Nota honesta**: no existe política de dominio para "¿esta
  campaña está dentro de su ventana programada?" — solo la comparación
  simple de timestamps ISO en esta capa de aplicación, no una regla de
  dominio inventada. `use_cases/record_content_impression_use_case.py::
  RecordContentImpressionUseCase` — la capacidad de registro real que el
  propio docstring de `ContentImpression` ya anticipaba.
- `backend/application/use_cases/configuracion/
  customer_display_advertising_use_cases.py` — CRUD completo (Create/
  Update/ChangeStatus para Content y AdvertisingSlot; Create/Update/
  ChangeContentCampaignStatus con las 7 transiciones en una sola clase,
  igual que `ChangeTemplateVersionStatusUseCase`; Assign/Unassign para
  CampaignPlacement, reutilizando sin reinventar
  `campaign_placement_policy.assign_placement()`).
  `AssignCampaignPlacementUseCase` chequea explícitamente si el slot ya
  tiene una asignación activa ANTES de insertar (nuevo
  `CampaignPlacementSlotOccupiedError`) — nunca deja que el índice único
  parcial del esquema llegue a la UI como un `IntegrityError` crudo,
  misma disciplina que `AssignDeviceUseCase` (SET-7) ya estableció.
- Página nueva `frontend/desktop/modules/configuracion/pages/
  pantalla_cliente_page.py::PantallaClientePage` (reemplaza la página
  genérica de solo lectura) — 4 tarjetas nuevas (Contenido/Campañas con
  8 botones de ciclo de vida idénticos a los de Documentos/Métricas vía
  `QMessageBox`, sin dashboard nuevo este round) sobre la lista de
  Displays ya existente (SET-17, sin tocar). 5 constantes nuevas de
  permiso en `ConfiguracionPermissions`, todas reutilizando códigos
  `PANTALLA_CLIENTE.*` ya pre-registrados en `permission_catalog.py`
  desde SET-1 (sin usar hasta ahora) — cero cambios al catálogo.
- Corte real en `sales_pos`: `AdvertisingQueryService` registrado como
  query service, `record_ad_impression` como command handler.
  `CustomerDisplayWindow` gana `render_idle_ad()` — `TEXT` renderiza el
  cuerpo real; `IMAGE`/`VIDEO`/`HTML` renderizan un placeholder honesto
  (`"{título} ({tipo})"`) — no existe infraestructura real de renderizado
  de imagen/video/HTML en este repositorio (confirmado repetidamente en
  este track), así que fingir pintarlo sería fabricado, no real.
  `SalesPosWorkspace` gana un `QTimer` de 1s que, solo mientras el
  carrito está vacío, resuelve/rota los anuncios activos y registra una
  impresión real al completarse cada `duration_seconds` — envuelto en
  try/except, mismo "best-effort, nunca bloquea la operación real" que
  cada `_try_*`/`_push_customer_display` ya estableció.

**Dos bugs reales encontrados durante este round, no asumidos
correctos**:
1. `CustomerDisplayWindow` es construida por `SalesPosWorkspace` con
   `self` como `parent` (para que Qt gestione su ciclo de vida) — pero un
   `QWidget(parent)` plano es un hijo EMBEBIDO ordinario por defecto
   (`isWindow()` es `False`), así que nunca aparecía realmente como una
   ventana de SO independiente, y `isVisible()` de cualquier hijo suyo
   reportaba `False` en cuanto el padre no fuera visible. Encontrado por
   el primer smoke test de la rotación (visible=False siempre), no por
   revisión de código. Corregido pasando el flag `Qt.Window` — mantiene
   la relación padre-para-ciclo-de-vida pero la vuelve una ventana
   top-level real, igual que `QDialog` ya hace implícitamente para toda
   otra ventana secundaria de este repositorio. Afecta también, en
   retrospectiva, el render de estado de venta que SET-17 ya construía —
   nunca se había verificado con un padre real asignado.
2. `SqliteContentCampaignRepository.save()`'s UPSERT nunca actualizaba
   `starts_at`/`ends_at` en conflicto — sin motivo hasta ahora, ya que
   ningún método de mutación tocaba esos campos antes de
   `update_schedule()`. Encontrado por el primer test de
   `UpdateContentCampaignUseCase` (la actualización se perdía
   silenciosamente al releer). Corregido agregando ambas columnas al
   `ON CONFLICT ... DO UPDATE SET`.

**Tests**: 71 nuevos — dominio (17: segregación de aprobación +
`update_schedule` + `update_display_order` + `Content.update_details`);
repositorios (5: los 4 `list_all()` nuevos + la regresión del bug de
persistencia de `starts_at`/`ends_at`); `AdvertisingQueryService`/
`RecordContentImpressionUseCase` (10: cadena real slot→placement→
campaña→contenido, exclusión de slot inactivo/campaña no-ACTIVE/fuera
de ventana, orden por `display_order`, alcance por modo); CRUD de
Configuración (20, incluye `CampaignPlacementSlotOccupiedError` y la
segregación de aprobación end-to-end); `CustomerDisplayWindow.
render_idle_ad()` + el bug de `Qt.Window` (6); rotación de
`SalesPosWorkspace` (6, ticks invocados directamente, nunca vía un
`QTimer` real); página nueva de Configuración vía la factory real (7).
Regresión enfocada limpia, confirmada con `pytest` directo: 418 tests
verdes en el alcance de customer_display+sales_pos+Configuración
combinados. Una corrida más amplia confirmó, también con `pytest`
directo (nunca estimado): **1236 tests verdes** en Settings + Device
Management + Document Output + Customer Display + sales_pos +
Configuración combinados.

**Fuera de alcance, declarado**: renderizado real de IMAGE/VIDEO/HTML
(sin infraestructura); un dashboard de métricas dedicado (el
`QMessageBox` real basta este round); cualquier cambio a
`CustomerDisplayQueryService`/el push de estado de venta de SET-17 más
allá de ocultar la etiqueta de anuncio.

## Avance SET-19 — Integraciones: Definitions, Instances, Credentials, Health, Webhooks

**Hecho** — abre `backend/domain/integrations/`, un catálogo de gobierno
para las integraciones externas, generalizando las dos que ya son reales
y están en vivo en este repositorio (WhatsApp, MercadoPago) sin tocarlas.
Ver `migrations/MIGRATION_LOG.md` (entrada "219_integrations_schema")
para el detalle completo. Resumen:

- **Ya existían dos artefactos reales sin conectar entre sí**:
  `whatsapp_service/middleware/hmac_validator.py` (verificación de firma
  real para Meta y MercadoPago) y
  `backend/security/secrets/secret_store_gateway.py::SecretStoreGateway`
  (ya construido desde SHELL-1, sin consumidores conectados — nota
  explícita de la auditoría SET-0 §6.5). Ninguno se tocó ni se importó
  — WhatsApp es un microservicio independiente (CLAUDE.md §14).
- **Definitions** — `IntegrationDefinition` (`code`/`category`/
  `required_credential_names`).
- **Instances**/**Credentials** — `IntegrationInstance` (`config` para
  ajustes no sensibles, `credential_references` hacia
  `SecretStoreGateway`, nunca el secreto). `config` se escanea contra
  claves con apariencia de secreto (reimplementación independiente del
  guardia que `ConnectionProfile` ya aplica, SET-7).
  `credential_provisioning_policy.assert_credentials_satisfied()` exige
  referencia para cada credencial requerida.
- **Health** — `IntegrationHealthCheck` (append-only, mismo patrón que
  `DeviceTestResult`, SET-9) + `integration_health_policy.current_status()`.
- **Webhooks** — `WebhookEndpoint` + `WebhookSignatureVerifierPort`,
  **con implementación real** (a diferencia de los Gateway/Renderer
  ports anteriores) — HMAC es criptografía sin estado, segura de
  construir real. Reimplementa (no importa) la misma lógica de
  `hmac_validator.py`, verificada contra los mismos vectores de prueba
  para confirmar resultados idénticos.
- **Nada de WhatsApp/MercadoPago/`SecretStoreGateway` se tocó.**
  Conectar los consumidores reales sigue pendiente.
- **Tests**: `tests/unit/integrations/` — 53 tests nuevos.
  `tests/integration/integrations/` — 17 tests nuevos. **Total tras
  SET-19 (Settings + Device Management + Document Output + Customer
  Display + Integrations): 917 tests verdes.**

### Continuación (2026-08-28) — CRUD real de Definitions/Instances/Credentials/Health/Webhooks + corte real de la resolución de credencial de MercadoPago

Auditoría (repegado de "SET-19 — Integraciones") encontró, de nuevo,
cero callers de aplicación — mismo punto de partida que cada dominio de
este track antes de su corte. "Integraciones" seguía siendo una de las 3
secciones de Configuración sin CRUD real. Todos los códigos de permiso
necesarios (`integracion.crear/editar/probar/activar/desactivar/
secretos`, `webhook.gestionar`) ya estaban pre-registrados bajo el grupo
`CONFIGURACION` desde SET-1 y sin usar salvo `ver` — mismo patrón que
SET-18 encontró para `PANTALLA_CLIENTE`.

Por separado: `services/mercado_pago_service.py::_get_token()` ya leía
el token de acceso desde `SecretStoreGateway` (migrado en el SET-1
original, no SQL crudo) — pero por una **constante hardcodeada**
(`PaymentProviderSettingsService.SECRET_NAME`), no a través de ningún
catálogo. El propio docstring del dominio de SET-19 nombra "conectar
consumidores reales a SecretStoreGateway vía IntegrationInstance" como
trabajo futuro diferido. Presentado vía AskUserQuestion (CRUD solo /
CRUD + corte real de MercadoPago / solo dominio); el usuario eligió el
corte real — la superficie de mayor riesgo que este track ha tocado
(resolución de credenciales de pago en vivo), así que recibió el diseño
más conservador posible.

**Construido**:
- Dominio: `IntegrationDefinition.update_details()` e
  `IntegrationInstance.update_details()` — no existían métodos de
  edición más allá de activate/deactivate. A diferencia de SET-18, los
  UPSERT de ambos repositorios YA actualizaban todos los campos
  relevantes en conflicto (name/required_credential_names_json,
  name/config_json/credential_references_json) — construidos más
  defensivamente desde el inicio, sin el bug de persistencia que SET-18
  encontró para `starts_at`/`ends_at`.
- `backend/application/use_cases/configuracion/
  integration_management_use_cases.py` — CRUD completo (Create/Update/
  ChangeStatus para Definition/Instance/WebhookEndpoint;
  `SetIntegrationInstanceCredentialUseCase` — el ÚNICO lugar que toca
  `SecretStoreGateway` desde el lado admin, y solo llama `set_secret()`,
  nunca `get_secret()` — el propio docstring del gateway prohíbe que la
  UI lea un secreto crudo; `RecordIntegrationHealthCheckUseCase` —
  manual, sin sondeo de red real, misma cautela de "pruebas" que
  SET-8/9/10 ya establecieron para hardware).
- `get_credential_status()` en `workspace_query_service.py` —
  únicamente usa `SecretStoreGateway.describe()` (nunca `get_secret()`),
  devuelve un `masked_value` seguro para la UI.
- Página nueva `frontend/desktop/modules/configuracion/pages/
  integraciones_page.py::IntegracionesPage` (reemplaza la genérica de
  solo lectura) — tabla principal de Definiciones; seleccionar una carga
  una tarjeta "Instancias" (con un área de Credenciales inline);
  seleccionar una instancia carga tarjetas "Webhooks" y "Salud" —
  mismo patrón de selección-en-cascada que `documentos_page.py`
  estableció para Templates→Versiones, con 2 tarjetas secundarias en vez
  de 1. 7 constantes nuevas de permiso, todas reutilizando códigos
  `CONFIGURACION.integracion.*`/`webhook.gestionar` ya pre-registrados —
  cero cambios al catálogo.
- **El corte real de MercadoPago**: nuevo
  `backend/infrastructure/integrations/mercadopago_credential_resolver.py::
  resolve_mercadopago_secret_name(connection)` — bootstrapea (primer uso)
  un `IntegrationDefinition` real (code="MERCADOPAGO") + un
  `IntegrationInstance` real con `credential_references={"mp_access_token":
  PaymentProviderSettingsService.SECRET_NAME}` — el mismo nombre de
  secreto ya en uso, así que un token ya configurado se encuentra de
  inmediato, sin re-captura, sin cambio de comportamiento hasta que un
  admin reapunte la referencia deliberadamente. Cualquier fallo en
  cualquier punto de esta resolución cae de vuelta a esa misma constante
  hardcodeada, nunca propaga la excepción.
  `mercado_pago_service.py::_get_token()` ahora resuelve el NOMBRE del
  secreto a través de esto antes de llamar
  `secret_store.get_secret(secret_name)` — la llamada a `get_secret()`
  en sí y su propio `or ""` de reserva quedan sin cambios, así que un
  pago real se degrada exactamente igual que antes si no hay token
  configurado. WhatsApp explícitamente fuera de alcance — CLAUDE.md §14
  protege ese límite de microservicio; el corte aprobado solo nombraba
  MercadoPago.
- **Verificado explícitamente, no asumido**: con un token ya configurado
  bajo el nombre legacy, `MercadoPagoService._get_token()` lo encuentra
  de inmediato tras el bootstrap (sin re-captura); sin ningún token
  configurado, sigue degradando a `""` exactamente como antes; con la
  conexión a la base de datos cerrada/rota, el resolver cae de vuelta a
  la constante hardcodeada sin propagar la excepción — cada uno de estos
  3 casos tiene su propio test contra SQLite real, no solo el caso feliz.

**Tests**: 33 nuevos — dominio (6: `update_details()` de ambas
entidades); CRUD de Configuración (16, incluye
`SetIntegrationInstanceCredentialUseCase`'s "valor en blanco = no toca
el secreto guardado, solo reapunta la referencia" y el estado de salud
derivado de chequeos reales); `mercadopago_credential_resolver`/
`MercadoPagoService._get_token()` cutover (7: bootstrap, reutilización
sin duplicados, reapuntado por admin respetado, fallback ante conexión
rota, más los 3 casos explícitos de `_get_token()` real arriba); página
nueva de Integraciones vía la factory real, incluye la cascada de
selección Definiciones→Instancias→(Webhooks+Salud) y confirma que el
estado de credencial nunca expone el secreto crudo (4). Regresión
enfocada limpia, confirmada con `pytest` directo: 161 tests verdes en el
alcance de integrations+Configuración combinados. Una corrida más amplia
confirmó, también con `pytest` directo (nunca estimado): **1339 tests
verdes** en Settings + Device Management + Document Output + Customer
Display + sales_pos + Configuración + Integrations combinados.

**Fuera de alcance, declarado**: sondeo de salud en vivo (llamar de
verdad a las APIs de WhatsApp/MercadoPago) — misma cautela de hardware/
dependencia-externa que SET-8/9/10; cualquier cambio a la resolución de
credenciales propia de `whatsapp_service/` — protegido por CLAUDE.md
§14; recepción/despacho real de webhooks — `WebhookEndpoint` sigue
siendo un catálogo, tal como el propio docstring de dominio de SET-19 ya
declaraba.

## Avance SET-20 — WhatsApp y notificaciones: Accounts, Templates, Channels, Routing

**Hecho** — abre `backend/domain/notifications/`, generalizando el
catálogo real de plantillas WhatsApp y los remitentes reales por canal ya
existentes, sin tocarlos. Ver `migrations/MIGRATION_LOG.md` (entrada
"220_notifications_schema") para el detalle completo. Resumen:

- **Ya existían tres artefactos reales**: `whatsapp_service/messaging/
  templates.py::TEMPLATES` (9 plantillas aprobadas por Meta —
  WhatsApp solo permite plantillas pre-aprobadas fuera de la ventana de
  24h), `send_event_template()` (ruteo evento→plantilla, rellena
  parámetros faltantes con `""` en silencio — el hueco real),
  `cash_notification_senders.py`/`loss_notification_senders.py`
  (remitentes reales WhatsApp/Email con su propia validación de
  destinatario). Ninguno se tocó.
- **Accounts** — `NotificationAccount` (`credential_reference` hacia
  `SecretStoreGateway`, `integration_instance_id` como referencia opaca
  hacia el catálogo de SET-19).
- **Templates** — `NotificationTemplate` generaliza `TEMPLATES`.
  `template_parameter_policy.assert_params_satisfied()` corrige el hueco
  real: rechaza el envío en vez de rellenar en silencio.
- **Channels** — `NotificationChannelPort`, sin implementación real a
  propósito — los remitentes reales ya existen por módulo, esta SET no
  los duplica. `NotificationMessage` reproduce exactamente la validación
  real de destinatario (E.164/email) de `cash_notification_senders.py`.
- **Routing** — `NotificationRoute` + `resolve_route()` — a lo sumo una
  ruta activa por `event_code` (índice único parcial).
- **Nada de WhatsApp/`TEMPLATES`/los remitentes reales se tocó.**
- **Tests**: `tests/unit/notifications/` — 35 tests nuevos.
  `tests/integration/notifications/` — 10 tests nuevos. **Total tras
  SET-20 (Settings + Device Management + Document Output + Customer
  Display + Integrations + Notifications): 962 tests verdes.**

### Continuación (2026-08-28) — CRUD real de Accounts/Templates/Routing + corrección real del hueco de parámetros faltantes en `whatsapp_service`

Auditoría (repegado de "SET-20 — WhatsApp y notificaciones") encontró,
de nuevo, cero callers de aplicación — "Notificaciones" seguía siendo
una de las 2 secciones de Configuración sin CRUD real. Solo 2 códigos de
permiso están pre-registrados para esta sección
(`notificacion.ver/gestionar`, más simples que el conjunto granular de
Integraciones) — cero cambios al catálogo.

**Hallazgo real durante la auditoría**: `whatsapp_service/` NO vive
dentro de `pos_spj_v13.4/pos_spj_v13.4/` como sugerían búsquedas previas
en ese subárbol — vive en la raíz del repositorio
(`whatsapp_service/`, hermano de `pos_spj_v13.4/`), exactamente como el
propio árbol de directorios de CLAUDE.md ya lo muestra. Confirmado
leyendo el archivo real: `whatsapp_service/messaging/templates.py:74`
todavía tiene el hueco documentado — `params.get(param_name, "")` —
un parámetro faltante se sustituye en silencio por una cadena vacía en
vez de negarse a enviar. Los 3 call sites reales
(`notifications/customer.py`, `notifications/rrhh.py`) siempre proveen
todos los parámetros declarados hoy — el hueco es defensivo/preventivo,
no actualmente disparado, pero real y en un microservicio desplegado.

Presentado vía AskUserQuestion (CRUD solo / CRUD + corregir el hueco de
WhatsApp / solo dominio); el usuario eligió corregir el hueco — la
propia intención documentada del dominio de SET-20.

**Construido**:
- Dominio: `NotificationAccount.update_details()`/
  `NotificationTemplate.update_parameter_names()` — no existían métodos
  de edición más allá de activate/deactivate. Nuevas
  `NotificationRouteEventCodeOccupiedError`/
  `NotificationTemplateCodeChannelOccupiedError`.
- `backend/application/use_cases/configuracion/
  notification_management_use_cases.py` — CRUD completo para las 3
  entidades. `CreateNotificationTemplateUseCase` chequea la ocupación de
  `code`+`channel` ANTES de insertar (nunca deja que `UNIQUE(code,
  channel)` llegue a la UI como `IntegrityError` crudo);
  `CreateNotificationRouteUseCase`/`ChangeNotificationRouteStatusUseCase`
  (ACTIVATE) chequean la ocupación de `event_code` de la misma forma —
  mismo índice único parcial `ux_notification_routes_event_active` que
  `ux_campaign_placements_slot_active` (SET-18) ya estableció, misma
  disciplina "desactivar-y-crear explícito, nunca un swap silencioso"
  que `AssignDeviceUseCase` (SET-7) originó.
- Página nueva `frontend/desktop/modules/configuracion/pages/
  notificaciones_page.py::NotificacionesPage` (reemplaza la genérica de
  solo lectura) — tabla principal de Rutas (ya la consulta real de
  `_page_notificaciones`) + 2 tarjetas siempre visibles "Cuentas" y
  "Plantillas" (no en cascada de selección como Integraciones — una
  Ruta compone una Cuenta y una Plantilla ya existentes, no es hija de
  ninguna) — mismo patrón de tarjeta-junto-a-la-tabla-principal que
  "Campañas de marketing" (SET-13) ya estableció. 1 constante nueva de
  permiso (`NOTIFICACIONES_GESTIONAR`), reutiliza el código
  `CONFIGURACION.notificacion.gestionar` ya pre-registrado.
- **La corrección real en `whatsapp_service`**: `messaging/templates.py::
  send_event_template()` ahora valida que todos los parámetros
  declarados por el template estén presentes ANTES de intentar el envío
  — si falta alguno, registra un error y devuelve `False` (mismo
  contrato que ya usaba para "plantilla desconocida", nunca lanza) en
  vez de sustituir el faltante por `""`. Reimplementado localmente
  dentro del propio microservicio — no importa
  `backend.domain.notifications` — mismo patrón "reimplementar, nunca
  cruzar el límite" que `webhook_signature_verifier.py` (SET-19) ya
  estableció para CLAUDE.md §14. Verificado explícitamente contra los 3
  call sites reales del servicio (todos siguen enviando exactamente
  igual que antes) y contra el caso que el bug original producía (un
  parámetro con cadena vacía explícita también se rechaza, no solo uno
  ausente).
- **Regresión de la corrección de WhatsApp confirmada por separado**:
  suite completa de `whatsapp_service/tests/` — 32 tests verdes en el
  subconjunto que puede colectarse en este entorno (7 archivos con
  errores de import preexistentes por rutas de `sys.path` no
  relacionadas con este cambio, confirmados fallando igual antes de
  tocar `templates.py`); 1 falla preexistente no relacionada
  (`test_conversation_quote_context.py`, una condición de carrera al
  limpiar un archivo temporal de SQLite en Windows).

**Tests**: 35 nuevos — dominio (6: `update_details()`/
`update_parameter_names()`); CRUD de Configuración (17, incluye ambos
guardias de ocupación y el caso de reactivar una ruta vieja mientras una
nueva está activa); página nueva de Notificaciones vía la factory real
(5); `whatsapp_service/tests/test_templates_parameter_validation.py`
(7, incluye una prueba explícita de que los 3 call sites reales de este
servicio nunca se ven afectados). Regresión enfocada limpia, confirmada
con `pytest` directo: 121 tests verdes en el alcance de
notifications+Configuración combinados (ERP), más los 32 de
`whatsapp_service` por separado. Una corrida más amplia confirmó,
también con `pytest` directo (nunca estimado): **1402 tests verdes** en
Settings + Device Management + Document Output + Customer Display +
sales_pos + Configuración + Integrations + Notifications combinados
(lado ERP).

**Fuera de alcance, declarado**: cualquier cambio a `NotificationChannelPort`
(sigue sin implementación real a propósito — los remitentes reales ya
existen por módulo); `cash_notification_senders.py`/
`loss_notification_senders.py` sin tocar; cualquier otro archivo de
`whatsapp_service/` más allá de la validación de parámetros añadida.

## Avance SET-21 — Feature flags: Flags, Rules, Rollout, Approval

**Hecho** — abre `backend/domain/feature_flags/`, exactamente el destino
que la auditoría SET-0 ya había nombrado en `settings_legacy_inventory.md`
§6.3: "REWRITE el esquema/repository unificándolo con
`FeatureFlag`/`FeatureFlagRule` tipados". Ver `migrations/MIGRATION_LOG.md`
(entrada "221_feature_flags_schema") para el detalle completo. Resumen:

- **Ya existía un servicio real con deuda técnica real**:
  `core/services/feature_flag_service.py::FeatureFlagService`
  (`is_enabled`/`set_flag`, caché por sucursal), consumido por
  `modulos/config_modules.py`/`modulos/delivery.py`. Su repositorio
  detecta en tiempo de ejecución si la tabla `feature_flags` tiene el
  esquema nuevo o el legacy (`PRAGMA table_info`). Ninguno se tocó — el
  esquema nuevo usa prefijo `ff_` para no colisionar.
- **Flags** — `FeatureFlag` (`code`/`name`/`default_enabled`) generaliza
  las claves string sueltas de `is_enabled()`.
- **Rules** — `FeatureFlagRule` (GLOBAL/BRANCH/USER) generaliza la
  precedencia `branch_id IN (?, 0) ORDER BY branch_id DESC` del
  repositorio legacy en un ranking de especificidad explícito.
- **Rollout** — `rollout_percentage` (0-100), capacidad nueva que el
  esquema legacy no tenía. `resolve_flag_value()` decide con un hash
  determinista `(flag.code, evaluation_key)` — sin aleatoriedad,
  verificado con una distribución de 1000 llaves.
- **Approval** — `FeatureFlagChangeRequest` (4 estados) +
  `assert_can_approve()` — misma segregación de funciones que
  `configuration_approval_policy` ya exige (§59): quien solicita no
  puede aprobar.
- **Nada de `FeatureFlagService`/la tabla legacy `feature_flags` se
  tocó.**
- **Tests**: `tests/unit/feature_flags/` — 47 tests nuevos.
  `tests/integration/feature_flags/` — 10 tests nuevos. **Total tras
  SET-21 (Settings + Device Management + Document Output + Customer
  Display + Integrations + Notifications + Feature Flags): 1019 tests
  verdes.**

### Continuación (2026-08-28)

Repegado del mismo master prompt de SET-21. Auditoría: el dominio, los 3
repositorios y `FeatureFlagsPage` (Aprobar/Rechazar/Aplicar) ya estaban
COMPLETOS, pero **nada en el código llamaba a `FeatureFlag.create()` ni
a `FeatureFlagChangeRequest.create()` fuera de los tests** — ni siquiera
un seed. La pantalla de aprobación nunca podía tener nada real que
procesar; el ciclo Flags→Rules→Rollout→Approval estaba roto en el
primer paso. Confirmado por grep directo. `flag.crear`/`flag.editar` ya
estaban pre-registrados en `permission_catalog.py` y sin usar.
Presentado vía AskUserQuestion (CRUD completo / solo originar
solicitudes / solo documentar); el usuario eligió CRUD completo.

- **Construido**: `CreateFeatureFlagUseCase`/`UpdateFeatureFlagUseCase`/
  `ChangeFeatureFlagStatusUseCase` (catálogo de Flags) +
  `RequestFeatureFlagChangeUseCase` (origina el `FeatureFlagChangeRequest`
  que alimenta el Approve/Reject/Apply ya existente) — nuevo
  `backend/application/use_cases/configuracion/
  feature_flag_management_use_cases.py`. `FeatureFlag.update_details()`
  nuevo en el dominio. `SqliteFeatureFlagRepository.list_all()` nuevo
  (antes solo `list_active()` — el admin no podía ver ni reactivar un
  flag desactivado).
- **UI**: `FeatureFlagsPage` reescrita — la tabla heredada (antes solo
  lectura de flags activos) es ahora la tabla real de Flags (crear/
  editar/activar/desactivar/"Solicitar cambio"), con una tarjeta
  "Reglas activas" de solo lectura controlada por la selección de la
  tabla (las reglas solo se crean vía `apply()`, por diseño —
  segregación de funciones §59). "Solicitudes pendientes" queda
  intacta.
- **Permisos**: `FEATURE_FLAGS_CREAR`/`FEATURE_FLAGS_EDITAR` nuevos en
  `ConfiguracionPermissions`, reutilizando `flag.crear`/`flag.editar`
  ya catalogados. `flag.rollback` queda sin usar — no existe capacidad
  de "revertir" en el dominio.
- **Tests**: 18 nuevos (3 dominio + 10 integración + 5 widget),
  confirmados con `pytest` directo.
- **Regresión combinada** (mismo alcance ampliado que SET-22
  continuación abajo): **1617 tests verdes** — ver la nota de alcance
  de regresión en "Avance SET-22" continuación.

## Avance SET-22 — Apariencia: Themes, Tokens, Light/dark, Density

**Hecho** — abre `backend/domain/appearance/`, el residual "SET-22+ |
Apariencia, offline, eliminación de legacy" que quedaba pendiente desde
SET-21. Ver `migrations/MIGRATION_LOG.md` (entrada "222_appearance_schema")
para el detalle completo. Resumen:

- **Tres sistemas de tema legacy, paralelos e inconsistentes**:
  `ui/themes/theme_engine.py` (raw SQL contra `configuraciones` clave
  `'tema'`, solo Claro/Oscuro), `core/services/theme_service.py`
  (claves `ui_theme`/`ui_density`/`ui_font_size`/`ui_icon_size`, `density`
  es string libre sin validar), `frontend/desktop/themes/` (design system
  más nuevo, sin persistencia ni concepto de densidad).
  `modulos/config_interfaz.py` (pantalla "Apariencia") ya está rota hoy —
  referencia atributos (`theme_service.palettes`/`.densities`) que no
  existen. Ninguno de los tres se tocó.
- **Themes** — `Theme` (`code`/`name`/`mode`/`is_default`) generaliza el
  par hardcodeado Claro/Oscuro en un catálogo tipado.
  `theme_default_policy.assert_can_set_default()` + índice único parcial
  `ux_themes_single_default` garantizan a lo sumo un tema default activo
  (dominio + esquema, defense in depth).
- **Tokens** — `DesignToken` (`theme_id` nullable/`token_key`/`category`/
  `token_value`) generaliza `frontend/desktop/themes/tokens.py`
  (constantes Python hardcodeadas) en filas persistidas y editables.
  `token_resolution_policy.resolve_tokens_for_theme()` fusiona tokens
  GLOBAL con overrides por tema — específico gana sobre global.
- **Light/dark** — `ThemeMode` (LIGHT/DARK) generaliza el split legacy.
  `AppearancePreference` (GLOBAL/BRANCH/USER) generaliza el par plano
  único `{ui_theme, ui_density}` en overrides por sucursal/usuario — sin
  precedente legacy de scoping. `appearance_resolution_policy.
  resolve_appearance()` reimplementa "el más específico gana" (USER >
  BRANCH > GLOBAL), mismo principio que `ConfigurationResolutionService`/
  `print_routing_policy`/`notification_routing_policy`/
  `feature_flag_evaluation_policy`.
- **Density** — `DensityProfile` (COMPACT/NORMAL/COMFORTABLE,
  `scale_factor` Decimal, métricas en px) — sin precedente legacy alguno;
  el `density` legacy es un string libre sin opciones ni métricas.
- **Nada de `theme_engine.py`/`ThemeService`/`frontend/desktop/themes/`/
  claves `configuraciones` se tocó**, ni se reparó la pantalla rota
  `modulos/config_interfaz.py`. Esta SET construye el modelo tipado que
  habilitaría un futuro corte, no ejecuta el corte de los consumidores
  reales. `tests/test_fase0_theme_engine_persistence.py` y
  `tests/test_fase0_theme_normalization.py` siguen intactos y en verde.
- **Tests**: `tests/unit/appearance/` — 35 tests nuevos.
  `tests/integration/appearance/` — 24 tests nuevos. **Total tras SET-22
  (Settings + Device Management + Document Output + Customer Display +
  Integrations + Notifications + Feature Flags + Appearance): 1078 tests
  verdes.**

### Continuación (2026-08-28)

Repegado del mismo master prompt de SET-22, mismo día que el repegado de
SET-21. Auditoría: el mismo hueco de SET-21 pero más grande — de las 4
entidades del dominio (`Theme`/`DesignToken`/`DensityProfile`/
`AppearancePreference`), la ÚNICA acción de escritura real era
`SetDefaultThemeUseCase` (marcar un tema existente como default), y esa
acción es inutilizable en la práctica porque requiere que YA exista un
`Theme` — **nada llamaba a `Theme.create()`/`DesignToken.create()`/
`DensityProfile.create()`/`AppearancePreference.create()` fuera de los
tests**, confirmado por grep. `tema.crear`/`apariencia.gestionar` ya
estaban pre-registrados en `permission_catalog.py` y sin usar.
Presentado vía AskUserQuestion (CRUD completo de los 4 pilares / solo
Themes+Tokens / solo documentar); el usuario eligió CRUD completo — el
corte más grande de este track por número de entidades nuevas con CRUD
en una sola ronda.

- **Construido**: nuevo `backend/application/use_cases/configuracion/
  appearance_management_use_cases.py` con los 10 use cases de origen:
  `CreateThemeUseCase`/`UpdateThemeUseCase`/`ChangeThemeStatusUseCase`
  (Themes), `CreateDesignTokenUseCase`/`UpdateDesignTokenUseCase`
  (Tokens, global o por tema), `CreateDensityProfileUseCase`/
  `UpdateDensityProfileUseCase`/`ChangeDensityProfileStatusUseCase`
  (Density), `CreateAppearancePreferenceUseCase`/
  `ChangeAppearancePreferenceStatusUseCase` (Light/dark por alcance).
  Cada uno con su verificación de ocupación antes del INSERT, respetando
  las 4 restricciones UNIQUE reales del esquema
  (`themes.code`, `density_profiles.level`, `ux_design_tokens_scope`
  sobre `(theme_id, token_key)`, `ux_appearance_preferences_scope_active`
  sobre `(scope_type, scope_id)` — esta última revisada tanto en CREATE
  como en la acción ACTIVATE, mismo patrón de
  `CreateNotificationRouteUseCase`/SET-20). `Theme.update_details()` y
  `DensityProfile.update_details()` nuevos en el dominio (este último
  reutiliza la validación de `create()` extraída a un `_validate()`
  compartido). `SetDefaultThemeUseCase` no se tocó.
- **UI**: `AparienciaPage` reescrita — la tabla heredada (antes solo
  lectura de temas activos) es ahora la tabla real de Temas (crear/
  editar/activar/desactivar + "Marcar como predeterminado", que por fin
  tiene datos reales con los que trabajar); una tarjeta "Tokens de
  diseño" controlada por la selección de Temas (GLOBAL + tokens del
  tema seleccionado); dos tarjetas hermanas independientes "Perfiles de
  densidad" y "Preferencias por alcance", mismo patrón de tarjetas
  siempre visibles que `NotificacionesPage` (SET-20) ya estableció para
  Cuentas/Plantillas.
- **Permisos**: `TEMA_CREAR`/`APARIENCIA_GESTIONAR` nuevos en
  `ConfiguracionPermissions`. `apariencia.gestionar` cubre todo lo demás
  del corte (editar tema, ambas acciones de Tokens, las 3 de Density,
  las 2 de Preferences) — no existe un código dedicado
  `tema.editar`/`token.*`/`densidad.*` en el catálogo, mismo criterio de
  "reusar el código pre-registrado más cercano" que
  `INTEGRACIONES_EDITAR` (SET-19) ya sigue. `tema.aprobar` queda sin
  usar — este dominio no tiene flujo de aprobación (a diferencia de
  Feature Flags).
- **Fuera de alcance, explícito**: los tres sistemas de tema legacy
  (`ui/themes/theme_engine.py`/`ThemeService`/
  `frontend/desktop/themes/`) y `modulos/config_interfaz.py` siguen sin
  tocarse; conectar `appearance_resolution_policy`/
  `token_resolution_policy` para repintar la UI en vivo es un corte de
  consumidor real, aparte y mayor, no parte de este cierre de origen.
- **Tests**: 34 nuevos (6 dominio + 22 integración + 6 widget),
  confirmados con `pytest` directo.
- **Regresión combinada**: el intento inicial de correr `pytest tests/`
  completo (sin acotar) reveló que esa ruta NUNCA ha sido viable en este
  repo — colapsa con un `Windows fatal exception: access violation`
  dentro de `modulos/configuracion.py` (bug nativo ya documentado en
  `tests/integration/test_settings_module_loads.py`, no tocado por esta
  ronda) y arrastra ~26 fallas preexistentes de un módulo "Configuración"
  legado completamente distinto (`repositories/config_repository.py`)
  que tampoco toca esta ronda. Acotando a los mismos paquetes que las
  rondas SET-16..20 vienen usando (Settings + Device Management +
  Document Output + Customer Display + Integrations + Notifications +
  Feature Flags + Appearance + Offline + Configuración UI/UX +
  sales_pos, sin los 26 tests del "Configuración" legado ni el archivo
  que crashea): **1617 tests verdes, cero fallas** — este es también el
  número final de la continuación de SET-21 de arriba (mismo comando,
  mismo run).

## Avance SET-23 — Offline: Cache, Version, Sync, Expiration

**Hecho** — abre `backend/domain/offline/`, cerrando el residual
"SET-23+ | Offline, eliminación de legacy" que quedaba pendiente desde
SET-22. Ver `migrations/MIGRATION_LOG.md` (entrada "223_offline_schema")
para el detalle completo. Resumen:

- **`sync/` es infraestructura muerta confirmada** — `SyncEngine`/
  `SyncWorker`/`ConflictResolver`, motor completo pero hardcodeado a
  tablas legacy fijas y nunca importado por `main.py`. Ya documentado
  independientemente en `docs/refactor/CRM-20_offline_sync_conflictos.md`,
  que confirmó que este repo corre sobre un único SQLite compartido sin
  transporte real — por lo que esta SET, igual que CRM-20, no inventa un
  pipeline `sync_status` sin productor real.
- **Cache** — `OfflineCacheEntry` (`entity_type`/`entity_id`/
  `workstation_id`/`payload_json`) generaliza los dos cachés ad hoc ya
  existentes: `ConfigurationCache` (invalidado por evento) y el legacy
  `AddressCache` (TTL+LRU hardcodeado).
- **Version** — `source_version` es un string libre que refleja
  cualquier marcador de versión que la entidad origen ya use — misma
  disciplina de reuso que CRM-20 estableció.
- **Sync** — `cache_version_sync_policy.evaluate_sync_state()` compara
  `source_version` contra la versión origen (FRESH/STALE, deliberadamente
  dos valores, no un pipeline fabricado).
- **Expiration** — `CacheExpirationPolicy` (`entity_type` único,
  `ttl_seconds`) generaliza el TTL hardcodeado de `AddressCache` en un
  registro tipado por tipo de entidad; `cache_expiration_evaluation_policy.
  is_expired()` hace la comparación de reloj.
- **Composición** — `offline_read_policy.resolve_cache_read()` combina
  las cuatro piezas: online+fresco→usar caché, online+obsoleto→refrescar,
  **offline+obsoleto→usar caché como mejor esfuerzo** (el comportamiento
  genuinamente offline-first). `is_online` es un parámetro plano que el
  llamador calcula (típicamente vía `Workstation.is_online()`, SET-6) —
  sin import cruzado entre bounded contexts.
- **Nada de `sync/`, tablas `sync_*`, `ConfigurationCache`, ni
  `AddressCache` se tocó.**
- **Tests**: `tests/unit/offline/` — 20 tests nuevos.
  `tests/integration/offline/` — 23 tests nuevos. **Total tras SET-23
  (Settings + Device Management + Document Output + Customer Display +
  Integrations + Notifications + Feature Flags + Appearance + Offline):
  1121 tests verdes.**

### Continuación (2026-08-28)

Repegado del mismo master prompt de SET-23, mismo día que los repegados
de SET-21/22. Auditoría: forma distinta de hueco a las dos rondas
anteriores — aquí el dominio tenía CERO callers de aplicación (el punto
de partida clásico de este track antes de su corte), y Offline era la
ÚNICA sección de Configuración que seguía siendo el shell genérico de
solo lectura, sin página propia.

**Hallazgo clave, distinto de SET-21/22**: los 2 pilares del dominio NO
son simétricos. `CacheExpirationPolicy` ("Expiration") es configuración
administrable de verdad — un TTL por `entity_type`, mismo perfil que
`FeatureFlag`/`Theme`. `OfflineCacheEntry` ("Cache"/"Version"/"Sync") es
un artefacto de RUNTIME que debería escribir un consumidor real de
lectura offline-first — y ese consumidor no existe (`sync/` confirmado
muerto, nunca importado por `main.py`; el propio `enums.py` del dominio
ya declina fabricar un pipeline `sync_status` sin productor real).
Autorizar una entrada de caché a mano desde un formulario no reflejaría
ningún flujo real. Presentado vía AskUserQuestion (CRUD de Expiration +
Cache como diagnóstico de solo lectura / CRUD completo de ambos pilares
incl. creación manual de caché / solo documentar); el usuario eligió la
opción recomendada — CRUD solo donde existe un flujo real de admin.

- **Construido**: nuevo `backend/application/use_cases/configuracion/
  offline_management_use_cases.py` — `CreateCacheExpirationPolicyUseCase`
  (verificación de ocupación sobre `entity_type` UNIQUE antes del
  INSERT)/`UpdateCacheExpirationPolicyUseCase`/
  `ChangeCacheExpirationPolicyStatusUseCase`. Sin cambios de dominio —
  `CacheExpirationPolicy` ya tenía `create()`/`change_ttl()`/
  `activate()`/`deactivate()`, a diferencia de SET-21/22 que necesitaron
  un `update_details()` nuevo. `list_all()` nuevo en ambos repositorios
  (`SqliteCacheExpirationPolicyRepository` y
  `SqliteOfflineCacheEntryRepository` — este último para el diagnóstico
  de solo lectura across-workstation).
- **UI**: nueva `OfflinePage` (reemplaza el shell genérico) — la tabla
  heredada es la tabla real de Políticas de Expiración (crear/editar/
  activar/desactivar), mismo patrón de reutilizar la tabla heredada como
  tabla principal que `FeatureFlagsPage`/`AparienciaPage` establecieron
  este día. Una tarjeta independiente "Caché por estación", listando
  `OfflineCacheEntry` vía `list_offline_cache_entries()` (join con
  `Workstation` para nombre legible) — **deliberadamente sin ningún
  botón de acción**, ni crear ni editar ni activar/desactivar; su
  mensaje de estado vacío explica por qué. `workspace_pages.py`: se
  elimina el último uso del factory `_page(...)` genérico (y el propio
  helper, ya sin consumidores) — las 9 secciones de Configuración tienen
  ahora página dedicada.
- **Permisos**: `OFFLINE_GESTIONAR` nuevo en `ConfiguracionPermissions`,
  reutilizando `offline.gestionar` ya catalogado — cubre los 3 use
  cases nuevos (no hay split fino `offline.crear`/`offline.editar` en
  el catálogo, mismo criterio de "un permiso de gestión cubre las
  escrituras de la sección" que `apariencia.gestionar` (SET-22) ya
  estableció).
- **Tests**: 11 nuevos (6 integración + 5 widget, incl. una prueba que
  siembra un `OfflineCacheEntry` directamente vía el dominio —
  simulando lo que haría un futuro consumidor real — y confirma que
  aparece en la tarjeta de diagnóstico sin ningún botón de acción
  disponible).
- **Regresión combinada** (mismo alcance acotado que SET-21/22 —
  Settings+Device Management+Document Output+Customer Display+
  Integrations+Notifications+Feature Flags+Appearance+Offline+
  Configuración UI/UX+sales_pos, NUNCA `pytest tests/` sin acotar — ver
  `env_nested_git_repo_pos_spj.md`): **1628 tests verdes, cero fallas**
  (1617 previos + 11 nuevos).

## Avance UI/UX — Configuración (fase separada de la numeración SET-N)

**Hecho** — el usuario pidió "SET-24 — UI/UX" (Sidebar, Páginas, Diálogos,
Design System, Responsive, Accesibilidad, Tests). Antes de construir nada
se investigó y se confirmó el alcance con el usuario porque ese número ya
significa otra cosa en este plan (fila `SET-24 | Eliminación de legacy`
de la tabla arriba) y porque el sidebar/shell real está en plena
reescritura por una pista `SHELL-N` separada, no comiteada
(`frontend/desktop/shell/`, `interfaz/menu_lateral.py` a punto de ser
reemplazado, 9 módulos de negocio ya migrados vía `shell_registration.py`
pero ninguno wireado en `main.py` todavía). Ver
`migrations/MIGRATION_LOG.md` (entrada "UI/UX (Configuración)") para el
detalle completo. Resumen:

- Primer frontend para los 9 bounded contexts de SET-0..23 — ninguno
  tenía UI antes (verificado). `backend/application/queries/configuracion/
  workspace_query_service.py::ConfiguracionWorkspaceQueryService` es el
  primer read path real contra los 9.
- **Sidebar/Páginas**: un único punto de entrada "Configuración" con 9
  rutas internas (General/Dispositivos/Documentos/Pantalla del cliente/
  Integraciones/Feature Flags/Apariencia/Notificaciones/Offline) —
  exactamente el objetivo que SET-0's propia auditoría ya había definido
  en §"Alcance" arriba.
- **Diálogos**: 2 de 9 secciones con escritura real —
  `RejectChangeRequestDialog`/aprobar/aplicar para Feature Flags
  (SET-21), `SetDefaultThemeDialog` para Apariencia (SET-22). Las otras 7
  quedan de solo lectura, alcance documentado, no un descuido.
- **Design System**: cero componentes nuevos, solo consume lo ya
  construido (incluye SET-22).
- **Responsive/Accesibilidad**: 1366×768 probado, `accessibleName`/
  tooltips/estados de vista en toda la superficie nueva.
- **Bug real encontrado y corregido durante esta fase**:
  `SetDefaultThemeUseCase` verificaba `assert_can_set_default` ANTES de
  desmarcar el tema default actual, así que el propio default activo se
  autobloqueaba y el "cambio de tema predeterminado" nunca funcionaba —
  corregido invirtiendo el orden (desmarcar primero, verificar después),
  con tests explícitos de switch-back e idempotencia.
- `shell_registration.py` existe pero **no** está wireado en
  `main.py`/`MainWindow`/`menu_lateral.py` este round — mismo criterio
  que `finance`/`cash_register`/`inventory`/`transfers`, verificado con
  test de arquitectura. `ui/themes/theme_engine.py`/`core/services/
  theme_service.py`/las 3 pantallas de configuración legacy
  (`modulos/config_interfaz.py` ya rota/`config_modules.py`/
  `config_hardware.py`) siguen intactas.
- **Tests**: 20 de integración (SQLite real, los 9 contextos + los 4
  use cases de escritura) + 9 de widgets PyQt5 (offscreen) + 7 de
  arquitectura (guardrails DS-10) = **36 tests nuevos, todos verdes**. No
  se suma al conteo acumulado "Total tras SET-N" (presentación, no otro
  bounded context de dominio) — ese conteo se mantiene en 1121.

### Continuación (2026-08-28)

Repegado del mismo master prompt de UI/UX, mismo día que los repegados
de SET-21/22/23 (Sidebar, Páginas, Diálogos, Design System, Responsive,
Accesibilidad, Tests). A diferencia de esas 3 rondas, esta fase no es
un bounded context nuevo sino la capa de presentación en sí — y ya se
había tocado extensamente hoy al construir `FeatureFlagsPage`/
`AparienciaPage`/`OfflinePage`. Auditoría por sub-punto contra el
estado actual:

- **Design System**: `tests/architecture/test_configuracion_ui_guardrails.py`
  (los 7 guardrails DS-10 originales) sigue en verde contra las 3
  páginas/3 archivos de diálogos nuevos de hoy — cero colores literales,
  cero `setStyleSheet`, cero `QDialog` crudo, todos los permisos de
  navegación siguen viniendo del catálogo real.
- **Responsive**: el test de resize
  (`test_workspace_builds_all_permitted_routes_lazily_and_supports_target_sizes`)
  ya itera genéricamente TODAS las rutas de `CONFIGURACION_NAV` — cubre
  las 3 páginas nuevas sin cambios necesarios.
- **Accesibilidad**: los botones asignan `accessibleName` automáticamente
  desde su texto (`create_primary_button`/etc. ya lo hacían desde antes
  de hoy); las tablas nuevas llevan `setAccessibleName` manual,
  consistente con el resto del módulo. Sin huecos encontrados.
- **Sidebar**: hueco real encontrado — `ConfiguracionNavEntry` para
  "Feature Flags" declara `badge_key="pending_flag_requests"` desde la
  fase original (pensado para mostrar "Feature Flags (N)" en el
  sidebar), pero ni `create_configuracion_view()` ni
  `shell_registration.py::ConfiguracionModuleActivator._build_view()`
  pasaban nunca un `badges=` real a `ConfiguracionView` — el contador
  quedaba permanentemente vacío. Antes de hoy esto era inofensivo
  porque nada podía originar un `FeatureFlagChangeRequest` pendiente
  (el hueco que SET-21 repegado cerró); ahora el badge por fin tiene
  datos reales que mostrar. Presentado vía AskUserQuestion (conectar el
  badge real / solo documentar); el usuario eligió conectarlo.
- **Construido**: ambos puntos de construcción en vivo ahora calculan
  `len(presenter.list_pending_feature_flag_change_requests())` y lo
  pasan como `badges={"pending_flag_requests": N}` (omitido del dict
  cuando N=0, para que el sidebar renderice el título plano sin
  "(0)" ruidoso) — mismo query ya usado por `FeatureFlagsPage`, ninguna
  consulta nueva.
- **Páginas/Diálogos**: sin cambios — ya cubiertos exhaustivamente por
  SET-21/22/23 repegado el mismo día.
- **Tests**: 2 nuevos en `test_feature_flags_page.py`
  (`TestSidebarPendingFlagRequestsBadge` — sin badge cuando no hay
  solicitudes pendientes, badge real "Feature Flags (1)" tras originar
  una).
- **Regresión combinada** (mismo alcance acotado de siempre + el
  archivo de guardrails de arquitectura, incorporado por primera vez a
  este conteo combinado): **1637 tests verdes, cero fallas** (1628 + 2
  nuevos + 7 guardrails DS-10 preexistentes ahora dentro del alcance).

## Avance Usuarios y Roles (fase separada de la numeración SET-N)

**Hecho (2026-08-28)** — el usuario pidió "elimina arquitectura antigua
y modulos antiguos". Repitiendo el precedente ya establecido en este
mismo track (2026-08-22): borrar `modulos/configuracion.py`/
`config_hardware.py`/`config_modules.py` hoy dejaría sin ninguna ruta
real SMTP, CRUD de usuarios/roles/auditoría, credenciales de Mercado
Pago, Happy Hour, cierre mensual real, configuración+prueba de hardware,
y alternado de módulos por sucursal — nada de esto lo cubre el módulo
nuevo. El usuario eligió migrar funcionalidad real primero, una sección
a la vez (mismo patrón que Dispositivos/Documentos/Empresa), empezando
por **Usuarios, Roles, Sucursales, Auditoría** — la más grande de las 8
áreas, pero sin dependencia de hardware ni de una operación financiera
irreversible.

Tres hallazgos reales durante la auditoría, antes de construir nada:

1. **La UI legacy ya delegaba en una capa de aplicación real**, no SQL
   crudo: `core/services/configuration_settings_service.py::
   UserManagementService`/`RoleManagementService`/
   `PermissionQueryService` (UUIDv7, transaccional, con eventos) +
   `backend/application/services/user_security_service.py::
   UserSecurityService` (desbloqueo auditado). Esta ronda es un
   traslado de UI sobre una capa ya sólida, no un dominio nuevo desde
   cero.
2. **Existe una capa "FASE 6" más canónica, completamente dormida,
   encima de esa capa de servicio**: `backend/application/use_cases/
   save_user_use_case.py::SaveUserUseCase`,
   `set_user_active_use_case.py::SetUserActiveUseCase` (+ Commands en
   `backend/application/commands/settings_commands.py`) — confirmado
   por grep: fuera de sus propios archivos y tests, CERO callers reales
   en toda la app. Su propio encabezado ya declara la intención: *"Each
   mutation has exactly one route: Command -> UseCase -> application
   service"*. Esta ronda es el primer caller real de esa capa para
   Usuarios/roles — arquitectónicamente correcto, no un desvío.
   (Existen use cases hermanos igual de dormidos para Happy Hour/Cierre
   Mensual/Hardware/Módulos/SMTP/MercadoPago/Empresa — contexto para
   cuando se aborde cualquiera de esas 7 áreas restantes, no construidos
   en esta ronda.)
3. **Los 8 tests fallando encontrados durante la re-auditoría de SET-25
   eran un fixture desactualizado, no un bug de producción real**:
   `tests/integration/test_configuracion_use_case_flows.py` y
   `test_roles_permissions_canonical_flow.py` hand-rolleaban su propio
   esquema con `roles`/`usuarios`/`sucursales` como
   `id INTEGER PRIMARY KEY AUTOINCREMENT` + columna `uuid` separada — un
   layout dual pre-REGLA-CERO. El esquema real
   (`migrations/m000_base_schema.py`) ya tiene `roles.id`/`usuarios.id`
   como `TEXT PRIMARY KEY` puro desde hace tiempo —
   `ConfigRepository.save_role()`/`save_user_v13()` ya escriben
   directamente contra `id` como UUID, correctamente, contra el esquema
   real. Insertar un string UUID en la columna `INTEGER PRIMARY KEY`
   desactualizada del fixture es justo lo que producía
   `sqlite3.IntegrityError: datatype mismatch`. Corregido: ambos
   fixtures ahora reflejan el esquema real (incl. `usuarios.email`/
   `empleado_id` de la migración 047, y `rol_permisos.id` que
   `save_role_permissions()` ya requería) — los 8 tests, más los 5 que
   ya pasaban en esos archivos, quedan verdes.

**Construido**:

- `SaveRoleCommand` + `SaveRoleUseCase` (nuevo — no existía ruta
  canónica para identidad de rol, solo `SaveRolePermissionsUseCase`
  para la matriz de permisos, un proyecto aparte y mayor, diferido).
- `ConfiguracionPresenter`: `create_user`/`update_user` (el presenter
  hashea la contraseña con `bcrypt` — nunca en el diálogo; contraseña
  en blanco al editar = no cambiarla, en blanco al crear se rechaza
  antes de llamar al use case), `set_user_active`, `unlock_user`
  (delega en `UserSecurityService.unlock_user()`, cuyo propio chequeo
  interno de permisos —contra sus códigos ya existentes
  `CONFIG_SEGURIDAD.editar`/`USUARIOS.desbloquear`— es el único gate,
  sin duplicar con un código nuevo), `save_role`, y los `list_*`/
  `audit_log_rows` de solo lectura — todos como passthroughs delgados
  hacia la capa de aplicación ya existente.
- Nueva `UsuariosRolesPage` (10ª sección de Configuración, más allá de
  los 9 bounded contexts SET-0..23 originales): la tabla heredada es la
  tabla real de Usuarios (Nuevo/Editar/Activar-Desactivar/Desbloquear),
  mismo patrón de reutilizar la tabla heredada que las 4 rondas de hoy
  ya establecieron. Dos tarjetas hermanas independientes: "Roles"
  (crear/editar nombre+descripción, NO la matriz de permisos) y
  "Auditoría" (solo lectura, últimas 200, sin botones — mismo patrón
  deliberadamente de solo lectura que la tarjeta de Caché de
  `OfflinePage`).
- Permisos nuevos bajo `CONFIGURACION`: `usuario.ver/crear/editar/
  activar`, `rol.ver/crear/editar` — primer catálogo nuevo de esta
  sesión (todas las rondas anteriores hoy reutilizaron códigos
  pre-registrados).

**Tests**: 22 nuevos/recuperados — 1 nuevo (`test_save_role_flow`) + 7
ya existentes recuperados en `test_configuracion_use_case_flows.py`, 1
recuperado en `test_roles_permissions_canonical_flow.py`, 8 de widgets
(`test_usuarios_roles_page.py`, incl. verificación real de hash bcrypt,
contraseña en blanco no cambia el hash, desbloqueo real reseteando
intentos fallidos). **Regresión combinada: 1669 tests verdes, cero
fallas** (1637 + 22 nuevos/recuperados) — incorpora por primera vez
`test_configuracion_use_case_flows.py`/
`test_roles_permissions_canonical_flow.py` al alcance combinado.

**Explícitamente fuera de esta ronda**: el pin de "sucursal de
instalación" (`get_installation_branch()` — migrado en la ronda
siguiente, ver abajo), la matriz granular de permisos por rol, y la
eliminación de cualquier pestaña legacy — nada de eso es seguro
todavía. Las otras 7 áreas legacy (SMTP, credenciales de Mercado Pago,
Happy Hour, Cierre Mensual, Hardware, Módulos) quedan como rondas
futuras, cada una con su propio use case ya dormido esperando
(hallazgo #2 arriba).

## Avance Sucursal de instalación (continuación — 2026-08-28)

El usuario pidió "continua eliminando legacy" tras cerrar la ronda de
Usuarios/Roles. Con la matriz de permisos aún sin migrar, la pestaña
legacy "Usuarios y Roles" seguía sin ser borrable — se le preguntó al
usuario cuál de los dos bloqueos restantes atacar primero y eligió el
pin de "sucursal de instalación" (qué sucursal es la de ESTA terminal:
`configuraciones.sucursal_instalacion_id`, leída por
`core/app_container.py`/`core/services/branch_resolution.py` en cada
arranque).

La escritura de este pin vivía en **dos** sitios legacy distintos
(`modulos/configuracion.py`: el combo `cmb_sucursal_inst` de la pestaña
"Empresa/Fiscal", y una acción por fila en la sub-pestaña "Sucursales"
de "Usuarios y Roles"), ambos llamando al mismo servicio ya correcto y
transaccional (`core/services/configuration_settings_service.py::
CompanyProfileService.set_installation_branch()` → `repositories/
config_repository.py::ConfigRepository.set_installation_branch()` —
valida UUIDv7 + sucursal activa, nunca persiste "None"). Nada duplicado
ni obsoleto aquí — es el mismo `ConfigRepository` que ya usa la página
de Usuarios/Roles; solo faltaban el wrapper Command/UseCase y una
ruta de UI nueva.

**Construido**: `SetInstallationBranchCommand` + `SetInstallationBranchUseCase`
(mismo patrón Command → UseCase → servicio de aplicación de la ronda
anterior), reutilizando `ConfiguracionPermissions.EMPRESA_EDITAR` (sin
código de catálogo nuevo — la pestaña legacy que hacía esto vivía en
"Empresa/Fiscal", el mismo permiso ya la protegía). `EmpresaPage`
(5ª sección) gana un resumen "📍 Esta instalación: {sucursal}" y un
botón "Anclar sucursal de esta instalación" que consolida los DOS
puntos de entrada legacy en uno solo — matiene la validación existente
y la propagación en vivo (`main_win.aplicar_sucursal_activa()`: barra
de sesión, módulos abiertos, `AppContainer`, evento
`ACTIVE_BRANCH_CHANGED`), llamada igual que la UI legacy, desde la capa
de UI, no del presenter.

**Tests**: 6 nuevos — `test_set_installation_branch_flow` (incl. rechazo
de sucursal inactiva) en `test_configuracion_use_case_flows.py`, 5 de
widget en `test_empresa_page_installation_branch.py` (incl. hallazgo
real: `m000_base_schema.py` YA siembra el pin a "Principal" en toda
instalación limpia — nunca queda realmente sin asignar; cubierto con un
segundo test que borra la fila para probar la ruta "sin asignar").
**Regresión**: los 4 archivos de test dedicados a este flujo — 14
en `test_configuracion_use_case_flows.py`, 58 en
`test_configuracion_ui_workspace.py`, 8 en `test_usuarios_roles_page.py`,
5 en `test_empresa_page_installation_branch.py` — verdes en aislado.
Regresión combinada por paquete (`tests/unit/{settings,device_management,
document_output,customer_display,integrations,notifications,
feature_flags,appearance,offline,configuracion}/` + `sales_pos/` + los 3
archivos sueltos de Configuración arriba + los 2 de integración + la
guardia de arquitectura): **1137 tests verdes, cero fallas**. Además se
corrió `tests/unit/` completo sin acotar como chequeo extra: 25 fallas,
las 25 preexistentes y no relacionadas con esta ronda (verificado
archivo por archivo) — mismo esquema `INTEGER PRIMARY KEY AUTOINCREMENT`
+ `uuid` dual pre-REGLA-CERO ya documentado en `test_configuracion_dtos
.py`/`test_configuracion_transactions.py`/`test_configuracion_refactor_
services.py` (2 archivos más con el mismo bug que los que se corrigieron
en la ronda de Usuarios/Roles, aún sin tocar — fuera de esta ronda), más
fallas en módulos sin ninguna relación (meat_processing,
archive_legacy_inventory_migration, product_catalog_refactor,
phase3_ui_components, menu_hidden_reasons) que esta ronda no tocó.

**Explícitamente fuera de esta ronda**: la matriz de permisos por rol
sigue siendo el único bloqueo restante para poder borrar la pestaña
legacy "Usuarios y Roles" — sin migrarla, ninguno de los dos puntos de
entrada legacy del pin es seguro de eliminar todavía. Las otras 6 áreas
legacy (SMTP, Mercado Pago, Happy Hour, Cierre Mensual, Hardware,
Módulos) siguen como rondas futuras.

## Riesgos

| Riesgo | Severidad | Mitigación |
| --- | --- | --- |
| Migrar credenciales en plano sin plan de rotación | Crítica | `SecretStoreGateway.rotate_secret` + ventana de migración con doble lectura solo durante el corte, nunca permanente |
| Romper impresión de ticket de venta (única ruta ya en buen estado) | Alta | Tratar `core/ticket_escpos_renderer.py` como contrato protegido con characterization tests antes de generalizar |
| `hardware_config` PK en `tipo` bloqueando multi-sucursal al migrar en caliente | Alta | Migración atómica única (REGLA CERO) hacia `device`/`device_profile` con ámbito real, no parches incrementales |
| Folio duplicado al eventualmente cortar Procurement/Finance hacia `DocumentNumberSequence` (construido en SET-16, `next_number()` legacy de Procurement sigue activo sin tocar) | Alta | Cortar ambos consumidores al mismo tiempo, no dejar dos generadores de folio vivos |
| Confundir permisos de Caja (`CASH_*`) con el catálogo punteado nuevo | Media | Decisión explícita de convención en SET-1, documentada antes de tocar Device Management |
| ~~Webhook MercadoPago sin firma en producción durante la transición~~ | ~~Alta~~ | **Mitigado** — `verify_mp_signature` aplicado en SET-1, ver "Avance SET-1" |

## Validación SET-0

Este corte es de solo lectura: no reinicia la base de datos, no abre la
UI y no elimina legacy. No hay tests que ejecutar todavía — el gate de
SET-0 es la existencia y coherencia de este documento junto con
`settings_legacy_inventory.md`.
