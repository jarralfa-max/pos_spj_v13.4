# SDLC-ARQ-PERM-001 — Especificación

- **Intent:** `items/SDLC-ARQ-PERM-001/intent.md` (aprobado el 2026-10-29, Alfred)
- **Nivel:** T0
- **Estado:** aprobado por autopiloto (2026-11-02) — pendiente de revisión humana en el PR

Rutas relativas a `pos_spj_v13.4/`. Toda ruta:línea se leyó en la rama `sdlc/sdlc-arq-perm-001` creada desde `1c4786a7`.

## Situación medida (antes del cambio)

- La composición única de Configuración construye la política real una sola vez: `frontend/desktop/modules/configuracion/configuracion_routes.py:197` (`ConfiguracionAuthorizationPolicy(SessionPermissionChecker(session))`), pero sólo se la pasa a 5 casos de uso (`:288-298`, `SaveUser`, `SetUserActive`, `SaveRole`, `SaveRolePermissions`, `SaveUserPermissions`) y a dos servicios (`OrgStructureService`, `RoleAssignmentService`). Los otros **80** casos de uso de `backend/application/use_cases/configuracion/` se construyen sólo con `connection` (`:212-286`, p. ej. `:256` `SetIntegrationInstanceCredentialUseCase(connection, secret_store)`), igual que `SetInstallationBranchUseCase` (`:292`) y el diseñador de tickets (`:301`, `:352`).
- Esos casos de uso no reciben ni verifican política: p. ej. `backend/application/use_cases/configuracion/integration_management_use_cases.py:167-184` escribe el secreto (`:180`) y hace `commit()` (`:183`) sin ninguna comprobación; `feature_flag_change_request_use_cases.py:25-38` aprueba con el `approver_user_id` que trae el llamador; `set_installation_branch_use_case.py:19-28` re-ancla la terminal sin comprobación.
- La única autorización es `ConfiguracionPresenter._authorize` (`frontend/desktop/modules/configuracion/configuracion_presenter.py:322-330`), llamada antes de cada `execute` (inventario completo abajo, medido con un recorrido AST del presentador). Las tablas de permiso por acción viven en el presentador (`:94-149`, más la regla ACTIVAR/DESACTIVAR de integraciones en `:2071-2074` y `:2126-2129`).
- Ya cumplen (no se tocan salvo el cableado por palabra clave): `SaveUserUseCase` (`backend/application/use_cases/save_user_use_case.py:16-25`, `unwired()` + `require()`), `SetUserActiveUseCase` (`set_user_active_use_case.py:20-24`), `SaveRoleUseCase` (`save_role_use_case.py:23-27`), `SaveRolePermissionsUseCase` (`save_role_permissions_use_case.py:61-75`, exige política), `SaveUserPermissionsUseCase` (`save_user_permissions_use_case.py:60-69`). Toman el actor del comando, pero el verificador de sesión sólo concede si ese actor ES el usuario de la sesión (`backend/application/configuracion/authorization.py:57-78`, PER-03), así que ya quedan atados a la sesión. `UserSecurityService.unlock_user` verifica en backend (`backend/application/services/user_security_service.py:81-85`); actualizaciones de software autorizan en su fábrica (`backend/infrastructure/desktop/software_updates_factory.py:59`).
- **Casos de uso nombrados en el intent que NO son alcanzables:** `save_system_setting_use_case.py`, `save_smtp_settings_use_case.py`, `save_payment_provider_settings_use_case.py` y `save_company_profile_use_case.py` (los de `backend/application/use_cases/`, no el de `configuracion/`) no tienen ningún llamador de producción (búsqueda de nombre de clase y de módulo en `backend/`, `frontend/`, `tests/`: sólo aparecen en sí mismos, en un comentario de `backend/infrastructure/integrations/mercadopago_credential_resolver.py:39` y en la lista de existencia de `tests/architecture/test_configuracion_module_architecture.py:37-39`) y los servicios a los que delegan (`save_mercado_pago_settings`, `save_many`, `SystemSettingsService`) ya no existen en el código (`grep` sin resultados): son código muerto. El `SaveCompanyProfile` vivo es `backend/application/use_cases/configuracion/company_branch_use_cases.py:47`, que sí entra en el alcance.

## Alcance (criterio explícito)

**Entra:** toda operación de ESCRITURA (persiste estado o produce un efecto físico: secreto, archivo, impresión) de Configuración que se construye en `build_configuracion_view` (`configuracion_routes.py:21-336`) y aún no se autoriza en backend:

1. Las 80 clases con `execute` de `backend/application/use_cases/configuracion/*.py`, excepto `PreviewLogoUseCase` (`branding_use_cases.py`, sólo genera una vista previa en un directorio temporal; no persiste).
2. `SetInstallationBranchUseCase` (`backend/application/use_cases/set_installation_branch_use_case.py`) — sólo su autorización (TERM-002 queda fuera, como dice el intent).
3. Las operaciones de escritura de `TicketDesignerService` (`ticket_designer_service.py`): `print_test`, `import_logo`, `set_company_logo`, `set_branch_logo`.

**No entra (seguimiento):**
- Los 4 casos de uso muertos de arriba. Recomendación: borrarlos (CLAUDE.md regla 2, «ELIMINAR código muerto») en un ítem propio, porque hoy una prueba de arquitectura exige que existan (`test_configuracion_module_architecture.py:37-39`). Mientras no tengan llamador ni servicio, no son alcanzables.
- Lecturas (`ConfiguracionWorkspaceQueryService`, `preview`, `validate`, `logo_for`): el intent habla de escritura; el presentador ya revalida lecturas (`configuracion_presenter.py:354-359`).
- Contraseñas (SDLC-SEC-001) y el re-anclaje central (SDLC-ARQ-TERM-002), excluidos por el intent.
- Cambiar los 5 casos de uso de usuarios/roles para tomar el actor de la sesión en vez del comando: ya están atados a la sesión por PER-03; rehacer su contrato de comando no aporta seguridad y cambiaría la futura API.

## Comportamiento esperado

- Cada operación en alcance recibe un autorizador y, **antes de leer o escribir nada**, exige el mismo permiso que hoy exige el presentador para esa operación (tabla abajo). No se crea, renombra ni concede ningún permiso: quien hoy puede hacer algo desde la pantalla lo sigue pudiendo; quien no, tampoco — ahora también por fuera de la pantalla.
- El actor que se autoriza es el **usuario de la sesión**, que el autorizador obtiene de un proveedor (`actor: Callable[[], str]`), no de los argumentos. Si la operación recibe además un actor declarado (`approver_user_id`, `requested_by_user_id`, `created_by_user_id`, `assigned_by_user_id`, `actor_user_id`, `command.user_name`) y no está vacío, debe coincidir con el de la sesión; si no, se niega (`ConfigurationPermissionDeniedError`). Hoy el presentador siempre pasa `self._actor()` (`configuracion_presenter.py:657,757,1272,1333,1429,1460,1486,1619,1830,1893,1932,2008`), así que no cambia nada para la pantalla; cierra la suplantación por llamada directa (p. ej. aprobar una solicitud propia declarando otro aprobador).
- **Falla cerrada:** construido sin autorizador, el caso de uso recibe `unwired(ConfiguracionActionAuthorizer)` (`backend/application/security/unwired_policy.py`), sin verificador; el primer `execute` lanza `ConfigurationAuthorizationConfigurationError` sin tocar la BD. Sin sesión, o sesión inactiva, o sin `user_id` → `ConfigurationPermissionDeniedError` (comportamiento existente de `ConfiguracionAuthorizationPolicy.require` y `SessionPermissionChecker`).
- Acción de estado sin permiso definido (cadena desconocida) → se niega, no se ejecuta.
- `system_owner` y administradores: sin cambio — `session.tiene_permiso()` ya resuelve el bypass y comodines (`authorization.py:50-56`).
- Multi-sucursal: Configuración es de empresa (`authorization.py:63-64`); no se añade ámbito por sucursal (eso es SDLC-ARQ-PERM-005).
- Offline/reintento/concurrencia: la verificación es local, sin E/S; no cambia la idempotencia ni la transacción de cada caso de uso (la verificación va antes de cualquier lectura).

### Tabla operación → permiso (fuente: el presentador actual, `configuracion_presenter.py`)

| Caso de uso | Permiso | Presentador |
|---|---|---|
| ApproveFeatureFlagChangeRequest, RejectFeatureFlagChangeRequest | `FEATURE_FLAGS_APROBAR` | :653, :671 |
| ApplyFeatureFlagChangeRequest | `FEATURE_FLAGS_ACTIVAR` | :686 |
| CreateFeatureFlag | `FEATURE_FLAGS_CREAR` | :701 |
| UpdateFeatureFlag, ChangeFeatureFlagStatus, RequestFeatureFlagChange | `FEATURE_FLAGS_EDITAR` | :716, :735, :753 |
| SetDefaultTheme | `TEMA_ACTIVAR` | :768 |
| CreateTheme | `TEMA_CREAR` | :783 |
| UpdateTheme, ChangeThemeStatus, Create/UpdateDesignToken, Create/Update/ChangeDensityProfile(Status), CreateAppearancePreference, ChangeAppearancePreferenceStatus | `APARIENCIA_GESTIONAR` | :798-930 |
| Create/Update/ChangeCacheExpirationPolicy(Status) | `OFFLINE_GESTIONAR` | :946, :961, :980 |
| SetInstallationBranch | `EMPRESA_EDITAR` | :1185 |
| RegisterDeviceProfile, RegisterDevice | `DISPOSITIVOS_CREAR` | :1206, :1221 |
| SetDeviceWindowsPrinter, UpdateDevice | `DISPOSITIVOS_EDITAR` | :1244, :1285 |
| TestDevice | `DISPOSITIVOS_PROBAR` | :1267 |
| ChangeDeviceStatus | por acción (`_DEVICE_STATUS_PERMISSIONS`) | :94-100, :1304 |
| CreateDocumentTemplate | `DOCUMENTOS_PLANTILLA_CREAR` | :1328 |
| CreateNextTemplateVersion, UpdateDocumentTemplate, `TicketDesignerService.print_test` | `DOCUMENTOS_PLANTILLA_EDITAR` | :1455, :1726, :1384 |
| ChangeTemplateVersionStatus | por acción (`_TEMPLATE_STATUS_PERMISSIONS`) | :101-109, :1481 |
| ChangeDocumentTemplateStatus | `DOCUMENTOS_PLANTILLA_ACTIVAR` | :130, :1745 |
| ImportLogo, SetCompanyLogo, SetBranchLogo (vía `assign_logo`) | `EMPRESA_EDITAR` | :1421 |
| SaveCompanyProfile | `EMPRESA_EDITAR` | :1510 |
| RegisterBranchProfile / UpdateBranchProfile | `SUCURSAL_CREAR` / `SUCURSAL_EDITAR` | :1525, :1540 |
| RegisterWorkstation / UpdateWorkstation | `ESTACION_CREAR` / `ESTACION_EDITAR` | :1555, :1570 |
| ChangeWorkstationStatus | por acción (`_WORKSTATION_STATUS_PERMISSIONS`) | :116-124, :1591 |
| AssignDevice, UnassignDevice | `DISPOSITIVOS_ASIGNAR` | :1615, :1637 |
| Create/Update/ChangePrintRoute(Status) | `DISPOSITIVOS_RUTAS_GESTIONAR` | :1659, :1681, :1707 |
| CreateMarketingCampaign / UpdateMarketingCampaign | `DOCUMENTOS_CAMPANA_CREAR` / `DOCUMENTOS_CAMPANA_EDITAR` | :1766, :1781 |
| ChangeMarketingCampaignStatus | `DOCUMENTOS_CAMPANA_ACTIVAR` | :134, :1800 |
| ImportDisplayMedia, CreateContent, UpdateContent, ChangeContentStatus | `PANTALLA_CLIENTE_CONTENIDO_CREAR` | :1837-1873 (`_with_attached_media` sólo se llama en :1841 y :1857, create/update de contenido) |
| CreateContentCampaign, UpdateContentCampaign | `PANTALLA_CLIENTE_CAMPANA_PROGRAMAR` | :1888, :1905 |
| ChangeContentCampaignStatus | por acción (`_CONTENT_CAMPAIGN_STATUS_PERMISSIONS`) | :140-148, :1927 |
| Create/Update/ChangeAdvertisingSlot(Status), Assign/UnassignCampaignPlacement | `PANTALLA_CLIENTE_PUBLICIDAD_GESTIONAR` | :1954-2020 |
| CreateIntegrationDefinition, CreateIntegrationInstance | `INTEGRACIONES_CREAR` | :2037, :2092 |
| UpdateIntegrationDefinition, UpdateIntegrationInstance | `INTEGRACIONES_EDITAR` | :2052, :2107 |
| ChangeIntegrationDefinitionStatus, ChangeIntegrationInstanceStatus | `ACTIVATE`→`INTEGRACIONES_ACTIVAR`, otra→`INTEGRACIONES_DESACTIVAR` | :2071-2075, :2126-2130 |
| SetIntegrationInstanceCredential | `INTEGRACIONES_SECRETOS` | :2147 |
| CreateWebhookEndpoint, ChangeWebhookEndpointStatus | `WEBHOOKS_GESTIONAR` | :2166, :2185 |
| RecordIntegrationHealthCheck, TestIntegrationConnection | `INTEGRACIONES_PROBAR` | :2200, :2217 |
| Todos los de notificaciones (8) | `NOTIFICACIONES_GESTIONAR` | :2236-2354 |

## Diseño

- **Contexto/capa:** `backend/application/configuracion` (autorización) y `backend/application/use_cases/configuracion` (casos de uso); composición en `frontend/desktop/modules/configuracion/configuracion_routes.py`. Sin cambios de dominio ni de infraestructura.
- **Se reutiliza** `ConfiguracionAuthorizationPolicy` + `SessionPermissionChecker` (`authorization.py:49-171`) y el mecanismo `unwired()` (`unwired_policy.py`), igual que `OrgStructureService` (`backend/application/organization/org_structure_service.py:117-130`, `authorization` + `actor: Callable[[], str]`). No se crea un esquema de permisos nuevo.
- **Nuevo contrato** en `backend/application/configuracion/authorization.py`:
  ```python
  class ConfiguracionActionAuthorizer:
      def __init__(self, policy: ConfiguracionAuthorizationPolicy | None = None,
                   actor: Callable[[], str] | None = None) -> None
      @classmethod
      def for_session(cls, session) -> "ConfiguracionActionAuthorizer"
      @classmethod
      def permissive_for_tests(cls) -> "ConfiguracionActionAuthorizer"   # sólo pruebas
      def require(self, permission_code: str, *, claimed_actor: str | None = None) -> str
      def require_mapped(self, mapping, action, *, claimed_actor=None) -> str
  ```
  `require` devuelve el actor de la sesión; lanza `ConfigurationPermissionDeniedError` (sin actor, sin permiso, actor declarado distinto, permiso desconocido) o `ConfigurationAuthorizationConfigurationError` (sin verificador). `require_mapped` niega si la acción no está en la tabla. `permissive_for_tests()` concede cualquier código CONOCIDO (un código mal escrito sigue fallando) y devuelve el actor declarado o uno fijo de prueba; lo usa `tests/conftest.py:307-313` a través de `unwired()`.
- **Casos de uso:** cada constructor gana `authorization: ConfiguracionActionAuthorizer | None = None` (palabra clave, al final; los llamadores actuales no cambian) y guarda `authorization or unwired(ConfiguracionActionAuthorizer)`. La primera instrucción de `execute` es `self._authz.require(<permiso>, claimed_actor=<actor declarado si existe>)`. `TicketDesignerService` recibe el mismo parámetro, lo propaga a los casos de uso de logos y exige `DOCUMENTOS_PLANTILLA_EDITAR` en `print_test`.
- **Una sola tabla por acción:** las tablas de permiso por acción se mueven del presentador a cada módulo de caso de uso, junto a su enum (`DEVICE_STATUS_PERMISSIONS`, `TEMPLATE_VERSION_STATUS_PERMISSIONS`, `DOCUMENT_TEMPLATE_STATUS_PERMISSION`, `WORKSTATION_STATUS_PERMISSIONS`, `MARKETING_CAMPAIGN_STATUS_PERMISSION`, `CONTENT_CAMPAIGN_STATUS_PERMISSIONS`, `integration_status_permission()`); el presentador las importa en lugar de redefinirlas, para que pantalla y backend no puedan divergir. El presentador conserva su `_authorize` (refleja permisos y da el mensaje legible antes de llamar).
- **Composición:** `build_configuracion_view` crea `action_authorizer = ConfiguracionActionAuthorizer(authorization, actor=lambda: session.user_id)` con la MISMA política de `:197` y lo pasa con `authorization=` a cada caso de uso, a `SetInstallationBranchUseCase` y a `_ticket_designer`. Los 5 que ya reciben la política pasan a recibirla por palabra clave (`authorization=authorization`) para que la guardia sea uniforme.
- **Guardia de arquitectura** (`tests/architecture/test_configuracion_use_cases_are_authorized.py`): (a) toda clase con `execute` de `backend/application/use_cases/configuracion/` (salvo la lista explícita de no-escritura: `PreviewLogoUseCase`) acepta `authorization` en `__init__`, usa `unwired(` como default y llama `.require(`/`.require_mapped(` dentro de `execute`; (b) en `configuracion_routes.py`, toda llamada a `*UseCase(...)` y a `TicketDesignerService(...)` lleva la palabra clave `authorization`.

```mermaid
flowchart LR
  UI[Presentador] -->|_authorize: mensaje| UI
  UI --> UC[Caso de uso]
  API[Script / API / otro módulo] --> UC
  UC -->|require(permiso, claimed_actor)| AZ[ConfiguracionActionAuthorizer]
  AZ -->|actor de la sesión| P[ConfiguracionAuthorizationPolicy]
  P --> S[SessionPermissionChecker → session.tiene_permiso]
```

## Datos y migraciones

Ninguna. No se crea ni se concede ningún permiso: se exige en backend exactamente el código que el presentador ya exige (tabla de arriba), todos ya en `ALL_CONFIGURACION_PERMISSIONS` (`backend/application/configuracion/permissions.py:108-110`). Los roles, permisos y asignaciones existentes no se tocan (requisitos-arquitectura §3). El número reservado 358 no se usa. Reversa: revertir los commits; no hay datos que migrar. El cambio se documenta en `migrations/MIGRATION_LOG.md` (CLAUDE.md regla 3) como entrada sin esquema.

## Seguridad y auditoría

- Permisos: los de la tabla, módulo `CONFIGURACION`/`DISPOSITIVOS`/`DOCUMENTOS`/`PANTALLA_CLIENTE`, ámbito empresa.
- Validación en backend: `require()` en cada operación, con el actor de la sesión.
- Auditoría: sin cambio. El rastro de auditoría lo sigue escribiendo el presentador (`_record_audit`) y los casos de uso que ya lo hacían; un rechazo en backend no se audita como evento de seguridad en este ítem (el registro de denegaciones pertenece a SDLC-ARQ-AUD-*).
- No se registran secretos: la prueba de credenciales verifica que, denegada, no se llama a `secret_store.set_secret`.

## Criterios de aceptación

1. **Regresión (T0):** construido sin autorizador y con la sustitución de pruebas desactivada (`@pytest.mark.unwired_fails_closed`), `SetIntegrationInstanceCredentialUseCase` y `CreateFeatureFlagUseCase` fallan cerrados sobre una BD real (`make_db`): lanzan `ConfigurationAuthorizationConfigurationError`, no se escribe el secreto, la referencia de credencial no cambia y no se crea el flag. (Falla en la línea base: hoy escriben.)
2. Con un autorizador de sesión cuyo usuario NO tiene `INTEGRACIONES_SECRETOS`, la escritura de credencial se niega y no deja rastro en BD ni en el almacén de secretos; con el permiso, se escribe.
3. Para cada uno de los 80+2 casos de uso en alcance, con un verificador que registra y niega: `execute` lanza `ConfigurationPermissionDeniedError`, el permiso pedido es exactamente el de la tabla, y la conexión (y el almacén de secretos) no recibió ninguna llamada.
4. Para cada acción de cada tabla por acción, el permiso exigido en backend es el mismo que exigía el presentador antes del cambio (tabla fijada en la prueba), y una acción desconocida se niega.
5. Un actor declarado distinto del de la sesión se niega aunque la sesión tenga el permiso (p. ej. `ApproveFeatureFlagChangeRequestUseCase` con `approver_user_id` ajeno); igual o vacío, pasa.
6. `TicketDesignerService.print_test`, `import_logo`, `set_company_logo` y `set_branch_logo` se niegan sin permiso y sin tocar impresora ni BD.
7. `SetInstallationBranchUseCase` sin `EMPRESA_EDITAR` se niega sin llamar al servicio.
8. Guardia de arquitectura (a) y (b) en verde; deja de estarlo si se quita `authorization=` de una construcción en `configuracion_routes.py` o el `require` de un `execute`.
9. Sin regresiones: las pruebas de los segmentos de Configuración, páginas de Configuración, seguridad y arquitectura dan el mismo resultado que la línea base (fallos preexistentes idénticos, ninguno nuevo).

## Riesgos y alternativas descartadas

- **Envolver cada caso de uso en un decorador en la composición** (sin tocar las clases): descartado; quien construya el caso de uso directamente (API, script) seguiría sin verificación, que es justo el hueco del intent.
- **Pasar `ConfiguracionAuthorizationPolicy` + leer el actor de cada argumento** (patrón de `SaveUserUseCase`): descartado; 70 de los 80 casos de uso no reciben actor, y el intent pide el actor de la sesión.
- **Quitar `_authorize` del presentador:** descartado; perdería el mensaje legible y no es parte del intent (la UI sólo refleja; el backend autoriza).
- Riesgo: un rechazo en backend que el presentador no anticipó cae en su `except Exception` → «Error inesperado». Mitigado porque pantalla y backend comparten política y tablas; no ocurre salvo cambio de sesión a mitad de la operación.
- Riesgo: pruebas funcionales que construyen casos de uso sueltos. Mitigado por `tests/conftest.py:307-313`, que resuelve `unwired()` a `permissive_for_tests()`.

## Decisiones que requieren aprobación

Ninguna de negocio queda abierta. Las decisiones tomadas y su fuente:
- Ítem independiente del pipeline CONFIGURACION → BACKLOG «Decisiones aprobadas», 2026-11-02, SDLC-ARQ-PERM-001.
- Permiso por operación = el que ya exige el presentador (sin permisos nuevos ni concesiones) → código actual + requisitos-arquitectura §3 («No borres ni restablezcas la configuración actual de roles y permisos»).
- Falla cerrada con `unwired()` y estándar `MODULO.accion` + `require()` → intent «Objetivo» y estándar del repo (`unwired_policy.py`).
- Los 4 casos de uso muertos quedan como seguimiento, no se borran aquí → CLAUDE.md regla 2 permite borrarlos, pero lo impide una prueba de arquitectura existente que este ítem no debe reescribir.
