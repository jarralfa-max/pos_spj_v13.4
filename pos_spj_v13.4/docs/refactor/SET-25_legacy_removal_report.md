# SET-25 — Eliminación de legacy

## Actualización 7 (2026-08-28) — "continua eliminando legacy"; pin de sucursal de instalación migrado

Tras cerrar Usuarios/Roles (Actualización 6), el usuario pidió
continuar. Con la matriz de permisos aún sin migrar, la pestaña legacy
seguía sin ser candidata a borrado — se preguntó cuál de los dos
bloqueos restantes atacar y el usuario eligió el pin de "sucursal de
instalación" (`configuraciones.sucursal_instalacion_id`, leída por
`core/app_container.py` en cada arranque).

**Hecho**: `SetInstallationBranchCommand`+`SetInstallationBranchUseCase`
(mismo patrón Command→UseCase de la ronda anterior) envolviendo el
servicio ya correcto `CompanyProfileService.set_installation_branch()`
(`core/services/configuration_settings_service.py`, ya transaccional y
validado — sin duplicar nada). `EmpresaPage` (5ª sección) gana un
resumen + botón "Anclar sucursal de esta instalación", consolidando los
DOS puntos de entrada legacy (`modulos/configuracion.py`: combo en
"Empresa/Fiscal" + acción por fila en "Sucursales") en una sola ruta
canónica, preservando la propagación en vivo
(`main_win.aplicar_sucursal_activa()`). Reutiliza el permiso
`EMPRESA_EDITAR` ya existente — sin código de catálogo nuevo. Detalle
completo: `docs/refactor/settings_refactor_execution_plan.md`
§"Avance Sucursal de instalación". 6 tests nuevos; regresión combinada
por paquete: **1137 tests verdes, cero fallas** (además, `tests/unit/`
completo sin acotar corrido como chequeo extra: 25 fallas, las 25
preexistentes y ajenas a esta ronda, verificado archivo por archivo).

**Por qué NO se eliminó ninguna pestaña legacy todavía**: la matriz de
permisos por rol sigue siendo el único bloqueo restante para la pestaña
"Usuarios y Roles" — hasta que se migre, ninguno de los dos call sites
legacy del pin (ni la pestaña completa) es candidato seguro de
eliminación. Las otras 6 áreas legacy (SMTP, Mercado Pago, Happy Hour,
Cierre Mensual, Hardware, Módulos) siguen sin tocar.

---

## Actualización 6 (2026-08-28) — "elimina arquitectura antigua y modulos antiguos"; primer paso real de migración

El usuario pidió explícitamente eliminar la arquitectura/módulos
antiguos — la misma instrucción "si o si" que ya se recibió el
2026-08-22 (ver Actualización, más abajo). Se investigó antes de tocar
nada (mismo protocolo de siempre) y se confirmó que el bloqueador
original sigue vigente: `modulos/configuracion.py`/`config_hardware.py`/
`config_modules.py` siguen siendo la única ruta real para SMTP+prueba,
CRUD de usuarios/roles/auditoría, credenciales de Mercado Pago, Happy
Hour, cierre mensual real, configuración+prueba de hardware, y
alternado de módulos por sucursal. Presentado vía AskUserQuestion
(migrar funcionalidad real primero / borrar ahora aceptando pérdida de
función / solo un subconjunto acotado); el usuario eligió migrar
primero, una sección a la vez — mismo patrón que Dispositivos/
Documentos/Empresa. Priorizó **Usuarios, Roles, Sucursales, Auditoría**
como primera pieza.

**Hecho — primer paso real de la ruta de migración**: construida
`UsuariosRolesPage` (10ª sección de Configuración) sobre la capa de
aplicación "FASE 6" ya existente pero completamente dormida
(`SaveUserUseCase`/`SetUserActiveUseCase`, cero callers reales antes de
hoy) + `UserManagementService`/`RoleManagementService`/
`UserSecurityService`/`PermissionQueryService` (ya canónicos, ya usados
por la UI legacy). Detalle completo:
`docs/refactor/settings_refactor_execution_plan.md` §"Avance Usuarios y
Roles". 22 tests nuevos/recuperados, 1669 tests verdes en la regresión
combinada.

**Por qué NO se eliminó ninguna pestaña legacy todavía, a pesar de la
instrucción**: mismo razonamiento que la Actualización original de
2026-08-22 — `modulos/configuracion.py`'s pestaña "Usuarios y Roles"
sigue siendo necesaria hasta que la nueva página alcance paridad real:
el pin de "sucursal de instalación" y la matriz granular de permisos
por rol quedaron deliberadamente fuera de esta ronda (proyectos aparte,
documentados como pendientes). Las otras 7 áreas legacy (SMTP,
credenciales de Mercado Pago, Happy Hour, Cierre Mensual, Hardware,
Módulos) no se tocaron en absoluto — cada una tiene su propio use case
igual de dormido en `backend/application/use_cases/` esperando ser el
primer caller real, mismo patrón que esta ronda acaba de establecer
para Usuarios/Roles.

**Camino a la eliminación real** (actualiza la sección "Pendientes
fuera de esta fase" de abajo para el ítem 7/9 específicamente sobre
Usuarios/Roles/Auditoría): 1) cerrar el pin de sucursal de instalación,
2) construir la matriz de permisos por rol, 3) recién entonces evaluar
si `modulos/configuracion.py`'s pestaña "Usuarios y Roles" puede
retirarse — con las otras 5 pestañas de ese mismo módulo (Empresa/
Fiscal, Email/SMTP, Mercado Pago, Happy Hour, Cierre Mensual) todavía
necesitando su propia ronda de migración antes de que el archivo
completo pueda considerarse candidato a eliminación.

---

## Actualización 5 (2026-08-28) — repaste completo de los 10 ítems; re-auditoría, no reejecución masiva

El usuario repegó "SET-25 — Eliminación de legacy" con los mismos 10
sub-ítems del corte original (Consolidar tablas / Eliminar QSettings
canónico / Eliminar hardware directo / Eliminar impresión directa /
Eliminar plantillas hardcodeadas / Eliminar integraciones duplicadas /
Eliminar rutas / Eliminar imports / Vaciar allowlist / Reporte), el
mismo día que los repegados de SET-21/22/23/UI-UX (que sí cerraron
huecos reales de origen en Feature Flags/Apariencia/Offline/Sidebar).
Se re-auditó cada ítem contra el estado ACTUAL en vez de asumir que el
reporte de 2026-08-22 seguía vigente sin verificar.

**Conclusión, a diferencia de las 4 rondas anteriores de hoy**: no hay
un hueco nuevo estructural que desbloquear. Los bloqueos originales
siguen siendo correctos y verificados de nuevo hoy:

- **Ítems 3/4 (hardware/impresión directa)**: siguen sin ningún driver
  real conectado — `cash_register_factory.py` sigue wireando
  `StubCashHardwareGateway`, `DocumentRendererPort` sigue sin ninguna
  implementación concreta en todo el repositorio (reverificado por
  grep). Eliminar esto hoy seguiría rompiendo cajones/básculas/
  impresoras/etiquetas reales sin reemplazo.
- **Ítems 7/9 (rutas/allowlist)**: `modulos/configuracion.py`/
  `config_hardware.py`/`config_modules.py` siguen siendo la única ruta
  real para SMTP con envío de prueba, CRUD de usuarios/roles, log de
  auditoría, credenciales de Mercado Pago, reglas de Happy Hour,
  ejecución real del cierre mensual, configuración+prueba de 5
  categorías de hardware, y alternado de módulos por sucursal — nada de
  esto migró hoy (SET-21/22/23/UI-UX tocaron exclusivamente el módulo
  NUEVO de Configuración, ya coexistente desde la Actualización de
  2026-08-22). El allowlist sigue sin poder vaciarse mientras esos 3
  archivos sigan siendo necesarios.
- **Ítem 1 (consolidar tablas)**: sin cambios — `feature_flags` legacy
  sigue siendo consumida por `modulos/config_modules.py`/
  `modulos/delivery.py:1310` (confirmado: el repegado de SET-21 de hoy
  tocó exclusivamente las tablas `ff_*` nuevas, nunca la legacy, por
  diseño explícito — ver "Avance SET-21" continuación).
- **Ítem 2 (QSettings)**: reverificado, sigue sin aplicar — cero usos en
  todo el repositorio.

**Dos hallazgos reales, uno ya resuelto y uno nuevo, acotado**:

1. El ítem 6 original (`mercado_pago_service.py::_get_token()` leyendo
   `configuraciones` con SQL crudo) **ya estaba resuelto antes de hoy**
   — efecto secundario de SET-19 (2026-08-28, antes en esta misma
   sesión), que cortó la resolución del NOMBRE del secreto hacia el
   catálogo real de Integraciones. Confirmado leyendo el archivo
   directamente: `_get_token()` ya no toca `configuraciones` en
   absoluto.
2. **Nuevo, no reportado en el corte original**: `_get_webhook_url()`/
   `_get_return_url()` en el mismo archivo seguían leyendo
   `mp_webhook_url`/`mp_return_url` con SQL crudo contra
   `configuraciones` — un patrón más pequeño y distinto del ítem 6
   original (que solo hablaba del token). `core/services/
   configuration_settings_service.py::PaymentProviderSettingsService`
   YA tenía `ROUTING_KEYS = ["mp_webhook_url", "mp_return_url"]` desde
   SET-1 (2026-08-22) — exactamente para estos 2 valores — pero
   `mercado_pago_service.py` nunca la usó para leerlos, solo para
   escribirlos desde la UI legacy. Presentado vía AskUserQuestion (solo
   actualizar el reporte / migrar estas 2 lecturas); el usuario eligió
   migrarlas.

**Hecho**: `_get_webhook_url()`/`_get_return_url()` ahora construyen
`SystemSettingsService(ConfigRepository(self.conn))` y llaman a
`.get_many(PaymentProviderSettingsService.ROUTING_KEYS, ...)` — mismo
mecanismo que `PaymentProviderSettingsService.get_mercado_pago_settings()`
ya usaba para las mismas 2 claves. Mismo contrato de fallback ante
excepción que el código original (nunca propaga, siempre degrada a
`""`/`"http://localhost:8765"`). Ningún cambio de esquema, ningún
cambio de comportamiento para el caso ya configurado.

**Tests**: 4 nuevos en `tests/test_mercado_pago_webhook_confirmation.py`
(lectura real vía el nuevo camino + fallback cuando no hay fila,
para ambos métodos).

**Hallazgo lateral durante la verificación**: correr `tests/architecture/`
completo (sin acotar) para verificar el fix produjo **84 fallas** —
ninguna relacionada con Mercado Pago ni con este cambio (transfers,
refactor_orchestrator, UUID cutover protection, módulo de Configuración
LEGACY, etc.) — mismo tipo de ruido preexistente ya documentado para
`pytest tests/` sin acotar (ver `env_nested_git_repo_pos_spj.md`).
Confirmado acotando a `tests/architecture/test_configuracion_ui_guardrails.py`
únicamente (los 7 guardrails realmente relevantes a este track): 7/7
verdes. **`tests/architecture/` tampoco es un directorio seguro para
correr sin acotar en este repo** — mismo tipo de trampa, documentado en
memoria para sesiones futuras.

**Regresión combinada** (mismo alcance acotado de todo el día + los 2
archivos de test de Mercado Pago, incorporados por primera vez):
**1647 tests verdes, cero fallas**.

**Sin cambios ejecutados en**: hardware/impresión directa, tablas
legacy, rutas de navegación, allowlists, plantillas hardcodeadas,
integraciones duplicadas (más allá del hallazgo puntual de arriba). El
reporte original de 2026-08-22 (Actualización 1, más abajo) sigue
siendo la referencia vigente para el porqué de cada bloqueo.

---

## Actualización 4 — "SET-5 — Empresa y sucursales" repegado; 5ª sección con CRUD real

El usuario repegó "SET-5 — Empresa y sucursales" (CompanyProfile/
BranchProfile/Assets/Horarios/Tests) — la misma fase que ya aparecía como
`SET-5 COMPLETO` en `settings_refactor_execution_plan.md` desde antes del
inicio de esta conversación visible. Se investigó antes de asumir nada:
`backend/domain/settings/entities/company_profile.py`/`branch_profile.py`
ya existían completos — `CompanyProfile.logo_asset: AssetReference`
(cubre "Assets") y `BranchProfile.opening_time`/`closing_time`/
`operation_days` (cubre "Horarios") ya estaban en el dominio desde
SET-5 original. Confirmado: dominio completo, pero **cero UI** — la
sección "General" del módulo Configuración mostraba Estaciones
(Workstations), nunca Empresa ni Sucursales. Mismo patrón que
Dispositivos/Documentos: dominio listo, use cases + UI faltantes.

**Hecho — Empresa y sucursales es la 5ª sección con escritura real completa**:

- **Dominio**: `CompanyProfile` tenía `create()` y setters granulares
  (`update_contact_info`, `replace_logo`, `set_social_network`) pero
  **ninguna forma de editar** `legal_name`/`default_currency`/
  `default_timezone`/`default_locale`/`commercial_name`/`tax_id`/
  `business_name`/`fiscal_regime_reference` después de crearlo — se
  agregó `update_identity()` (mismo patrón que `Device.rename()`/
  `update_notes()` en la ronda de Dispositivos), factorizando
  `_validate_currency`/`_validate_locale` para que `create()` y
  `update_identity()` compartan exactamente la misma validación. Se
  agregó `BranchProfileNotFoundError` (no existía). Tests nuevos:
  `tests/unit/settings/test_company_and_branch_profile_entities.py`.
- **Aplicación** (`backend/application/use_cases/configuracion/
  company_branch_use_cases.py`, nuevo): `SaveCompanyProfileUseCase` —
  get-or-create deliberado: la primera llamada crea, cada llamada
  posterior actualiza la MISMA fila — un singleton a nivel de aplicación
  (el dominio no lo impone, `company_profile.py` lo dice explícitamente:
  "nothing here enforces a singleton — that stays a repository/
  application-layer concern"; esta es exactamente esa capa).
  `RegisterBranchProfileUseCase` crea el perfil de gobierno para una
  sucursal YA EXISTENTE en `sucursales` — nunca crea una sucursal física
  nueva (fuera de alcance, la tabla legacy sigue siendo dueña de esa
  identidad, mismo razonamiento que `branch_profile.py`'s propio
  docstring). `UpdateBranchProfileUseCase`.
- **Query service**: `_page_empresa()` (nueva sección, tabla de
  sucursales con horario), `get_company_profile()`,
  `get_branch_profile()`, `list_unregistered_branches()` (sucursales de
  `sucursales` sin fila en `branch_profiles` todavía — la lista candidata
  para "Nueva sucursal").
- **UI**: nueva entrada de navegación "Empresa y sucursales" (primera en
  el sidebar, código de permiso `CONFIGURACION.empresa.ver` — ya
  registrado en el catálogo desde SET-1, nunca antes usado).
  `pages/empresa_page.py`: panel resumen de Empresa (con botón "Editar
  empresa") + tabla de sucursales (heredada de `base_page.py`) + botones
  "Nueva sucursal"/"Editar sucursal". `dialogs/company_branch_dialogs.py`:
  `CompanyProfileDialog`, `BranchProfileCreateDialog`/
  `BranchProfileEditDialog` (ambos comparten `_BranchHoursFields`, un
  mixin con checkbox "Definir horario de operación" que habilita/
  deshabilita 2 `TimeInput` + 7 checkboxes de día — `BranchProfile`
  exige que apertura/cierre estén ambos definidos o ambos ausentes).
  "Assets" (el logo): campo de texto para un `asset_id` (UUID) ya
  registrado en otro sistema — no existe un subsistema de gestión de
  assets/archivos en este repositorio (confirmado por búsqueda:
  `AssetReference` es la única referencia a "asset" fuera de
  `backend/domain/finance` que es sobre activos fijos contables, no
  archivos); construir uno estaba fuera de alcance de esta fase.
- **Verificación**: flujo completo probado de punta a punta contra
  SQLite real vía la factory real de la app — guardar empresa (crea) →
  guardar empresa de nuevo (actualiza la misma fila, no crea una
  segunda) → registrar sucursal → editar sucursal (horario + textos de
  ticket). 64 tests de integración (antes 51), 31 de widgets PyQt5
  (antes 22), 7 de arquitectura — todos verdes tras corregir un fake de
  prueba desactualizado en el primer intento (`Queries` en
  `test_configuracion_ui_workspace.py` no tenía los 3 métodos nuevos
  todavía cuando se lanzó la primera corrida). Suite completa de
  `settings` (dominio SET-2..6) también reverificada verde.

**Pendiente, fuera de esta actualización**: 4 secciones aún de solo
lectura (Pantalla del cliente, Integraciones, Notificaciones, Offline).
Los 3 huecos de la Actualización 3 (`§58` permisos granulares, `§65-68`
dashboard Resumen, `§70` clasificación formal de legacy) siguen sin
atender. `CompanyProfile.social_networks`/`BranchProfile.social_links`/
`map_reference`/`warehouse_ids`/`default_workstation_profile_id` no
tienen UI todavía — el dominio los soporta, quedan fuera de los
diálogos de esta ronda (documentado, no un descuido).

---

## Actualización 3 — el usuario repega el prompt maestro completo (§1-71); "Documentos" pasa a CRUD real

El usuario repegó el prompt maestro definitivo completo (71 secciones,
`§1` Configuración como plataforma de gobierno hasta `§71` fases
SET-0..25+). Se reconoció como el mismo documento que este pipeline
viene implementando desde SET-0 — no un requerimiento nuevo — y se hizo
una lectura completa contra el estado real antes de proponer nada.

Tres brechas concretas encontradas (más allá de "más secciones sin UI
real", que ya se sabía):

1. **Permisos mucho más superficiales que `§58`** — ~13 códigos
   construidos contra ~80 granulares que el prompt especifica.
2. **Sin dashboard "Resumen" (`§65-68`)** — KPIs (configuraciones
   pendientes, dispositivos con error, trabajos de impresión fallidos,
   integraciones degradadas) y gráficas no existen todavía.
3. **`§70` (eliminación de legacy) es más sistemático** de lo que
   `SET-25` original ejecutó — pide una tabla formal de clasificación
   REUSE/MOVE/WRAP_TEMPORARILY/REWRITE/DELETE/BLOCKED por símbolo legacy,
   un doc de consolidación de esquema, y una allowlist temporal que debe
   llegar a cero.

Se acordó con el usuario NO intentar las 71 secciones de una vez —
mantener la disciplina ya validada con Dispositivos: una sección a la
vez, CRUD completo, verificado de punta a punta. El usuario eligió
continuar con esa disciplina; se seleccionó **Documentos** (Document
Output, `§26-37`) como la siguiente — el dominio ya tenía la máquina de
7 estados completa desde SET-11, mismo punto de partida que tenía
Dispositivos antes de esta ronda.

**Hecho — Documentos es la 3ª sección con escritura real completa**:

- **Aplicación** (`backend/application/use_cases/configuracion/
  document_template_use_cases.py`, nuevo): `CreateDocumentTemplateUseCase`
  (crea la familia `DocumentTemplate` + su primera versión DRAFT juntas —
  una plantilla sin versiones no sirve de nada),
  `CreateNextTemplateVersionUseCase` (nueva versión encadenada vía
  `previous_version_id`, nunca edición en sitio de una versión activa —
  `§26`), y `ChangeTemplateVersionStatusUseCase` — deliberadamente UNA
  sola clase para las 7 transiciones (enviar a aprobación/aprobar/
  rechazar/activar/desactivar/expirar/archivar), mismo patrón que
  `ChangeDeviceStatusUseCase`. `ACTIVATE` desactiva primero la versión
  actualmente activa de la plantilla (si existe y es distinta) antes de
  activar la nueva — mismo fix de orden ya aplicado en
  `SetDefaultThemeUseCase` (Actualización 2/SET-22): nunca asumir que el
  estado previo ya está despejado, desmarcarlo explícitamente primero.
- **Query service**: `get_template()`, `list_template_versions()`.
- **UI**: `pages/documentos_page.py` — tabla principal de plantillas +
  tarjeta secundaria "Versiones" que se recarga cuando cambia la
  selección de la tabla principal (la tabla se reconstruye en cada
  `reload()`, así que la señal de selección se reconecta cada vez, no
  una sola vez en `__init__`). `dialogs/document_template_dialogs.py`:
  `DocumentTemplateCreateDialog` (27 tipos de documento vía
  `SearchableComboBox`, 5 formatos de renderizado)/
  `NewTemplateVersionDialog`/`RejectTemplateVersionDialog`, todos sobre
  `FormDialog`.
- **Verificación**: flujo completo probado de punta a punta contra
  SQLite real vía la factory real de la app — crear plantilla → ver
  versión 1 en borrador → enviar a aprobación → aprobar → activar →
  crear versión 2 → confirmar que activar v2 desactiva automáticamente
  v1. 51 tests de integración (antes 37), 22 de widgets PyQt5 (antes
  16), 7 de arquitectura — todos verdes. Suite completa de
  `document_output` (dominio SET-11, no tocado en su esencia) también
  reverificada verde.

**Pendiente, fuera de esta actualización**: 5 secciones aún de solo
lectura (General, Pantalla del cliente, Integraciones, Notificaciones,
Offline). Los 3 huecos identificados arriba (`§58` permisos granulares,
`§65-68` dashboard Resumen, `§70` clasificación formal de legacy) siguen
sin atender — quedan como candidatos para una próxima ronda, a decidir
con el usuario. `LabelTemplate`/`LabelTemplateVersion` (`§34-36`,
etiquetas — distinto de `DocumentTemplate` en el prompt maestro) no se
construyeron todavía; por ahora `DocumentTemplate` cubre también los 6
`DocumentType` de etiqueta (`LOT_LABEL`, etc.) heredados de SET-14, sin
una entidad `LabelTemplate` separada.

---

## Actualización 2 (mismo día) — "Dispositivos" pasa de esqueleto a CRUD real

Feedback directo del usuario tras probar el módulo registrado: *"todos
los fases del master prompt no sirvieron de nada, el modulo de
configuracion solo es un esqueleto basico"*. Correcto — de las 9
secciones, solo 2 tenían una acción de escritura real (Feature Flags,
Apariencia); las otras 7 eran listados de solo lectura. Se acordó con el
usuario priorizar UNA sección y llevarla a CRUD completo antes de tocar
las demás — eligió **Dispositivos**.

**Hecho — Dispositivos es ahora la 3ª sección con escritura real completa**:

- **Dominio**: `Device` (SET-7) no tenía forma de editar `name`/`notes`
  después de crearlo — se agregaron `rename()`/`update_notes()` (mismo
  patrón de validación que el resto del entity, con tests nuevos:
  `tests/unit/device_management/test_device_entity.py`). Se agregó
  `list_all()` a `DeviceRepositoryPort`/`SqliteDeviceRepository` — el
  listado de gestión necesita ver dispositivos en cualquier estado
  (bloqueado/inactivo/retirado), no solo los `list_active()`.
- **Aplicación** (`backend/application/use_cases/configuracion/
  device_management_use_cases.py`, nuevo):
  `RegisterDeviceProfileUseCase` (arma el `ConnectionProfile` correcto
  según el tipo de conexión — SERIAL necesita puerto+baud rate, NETWORK
  necesita host+puerto, el resto no necesita nada extra),
  `RegisterDeviceUseCase`, `UpdateDeviceUseCase`, y
  `ChangeDeviceStatusUseCase` — deliberadamente UNA sola clase para las 5
  transiciones (activar/desactivar/bloquear/desbloquear/retirar) en vez
  de 5 casi idénticas; cada método del dominio sigue siendo dueño de su
  propia regla de transición.
- **Query service**: `list_device_profiles()`, `list_branches()`,
  `get_device()` — para poblar los combos de los diálogos y precargar el
  diálogo de edición.
- **UI**: `pages/dispositivos_page.py` (reemplaza la página genérica de
  solo lectura) con 8 botones de acción — Nuevo perfil, Nuevo
  dispositivo, Editar, Activar, Desactivar, Bloquear, Desbloquear,
  Retirar. `dialogs/device_dialogs.py`:
  `DeviceProfileCreateDialog`/`DeviceCreateDialog`/`DeviceEditDialog`/
  `BlockDeviceDialog`, todos sobre `FormDialog` (FASE DS-3). HTTP/
  WEBSOCKET deliberadamente no ofrecidos en el selector de conexión
  todavía (USB/Serie/Red/Bluetooth/Sistema/Virtual sí) — alcance acotado,
  documentado aquí, no un descuido.
- **Bug real encontrado y corregido en el camino**: el combo de tipo de
  dispositivo/conexión entrega strings planos (`"THERMAL_PRINTER"`), pero
  `DeviceProfile.create()`/`ConnectionProfile.create()` esperan los
  enums reales (`DeviceType`/`ConnectionType`) — `RegisterDeviceProfileUseCase`
  ahora convierte explícitamente (`DeviceType(device_type)`) antes de
  construir el perfil. Mismo patrón para `DeviceStatusAction` en el
  presenter (los botones de la UI mandan strings, el presenter los
  convierte a enum antes de llamar al use case).
- **Verificación**: flujo completo probado de punta a punta contra
  SQLite real vía la factory real de la app (`create_configuracion_view`)
  — crear perfil (USB/Serie/Red) → crear dispositivo → editar →
  bloquear → desbloquear → retirar → confirmar que activar un
  dispositivo retirado falla con el error de dominio correcto. 37 tests
  de integración (antes 20), 16 tests de widgets PyQt5 (antes 9), 7 de
  arquitectura — todos verdes. Suite completa de `device_management`
  (dominio SET-7 no tocado en su esencia, solo extendido) también
  verificada verde.

**Pendiente, fuera de esta actualización**: las otras 6 secciones de
solo lectura restantes (General, Documentos, Pantalla del cliente,
Integraciones, Notificaciones, Offline) — decidir con el usuario el
orden de prioridad para llevarlas a CRUD real, una por una, mismo
patrón que Dispositivos. `DeviceProfile` en sí no tiene edición/
desactivación expuesta en la UI todavía (el dominio ya la soporta:
`activate()`/`deactivate()`/`add_capability()`/etc.) — solo su registro.

---

## Actualización (mismo día) — registro del módulo nuevo en la app real

El usuario, tras leer el reporte inicial, pidió explícitamente: *"Elimina
codigo legacy de los modulos viejos si o si y registra el nuevo modulo,
no puedo hacer pruebas si aun estan activos las funciones antiguas."*
Se investigó (agente read-only) cómo arranca realmente `main.py` y cómo
se conectan hoy los 3 módulos legacy de Configuración a la navegación
real, antes de tocar nada — mismo protocolo de siempre.

**Hallazgo central que cambió la ejecución**: `main.py` arranca
exclusivamente por la ruta legacy (`AppContainer`/`MainWindow`/
`menu_lateral.py`) — el shell nuevo (`frontend/desktop/shell/`) no es
alcanzable desde ahí, solo desde tests. El patrón real y ya probado para
poner un módulo nuevo de `frontend/desktop/modules/X/` en la app viva no
es `shell_registration.py` (eso es exclusivo del shell nuevo, no
arrancado) — es un wrapper delgado en `modulos/` (`modulos/rrhh.py`,
`modulos/finanzas.py`) que delega en una factory `create_X_view(container,
parent)`, registrado en `main_window.py::_conectar()` y con su botón en
`menu_lateral.py`. `frontend/desktop/modules/configuracion/` no tenía esa
factory — solo el `shell_registration.py` de la fase UI/UX, escrito para
el shell no arrancado.

**Se construyó y registró** (junto a los 3 legacy, no en su reemplazo —
ver razón abajo):
- `frontend/desktop/modules/configuracion/configuracion_routes.py::
  create_configuracion_view(container, parent)` — nueva factory, mismo
  patrón que `finance_routes.py`/`hr_routes.py`, pero corrigiendo el bug
  ya documentado en ambas: usa `getattr(container, "session", None)`
  (el atributo real de `AppContainer`), no `"session_context"`
  (inexistente, que Finance/HR siguen usando en producción hoy sin que
  nadie lo haya notado). `has_permission` delega en
  `core.permissions.verificar_permiso(container, permiso,
  mostrar_alerta=False)` — el mismo verificador real que usa el resto
  de la app.
- `modulos/configuracion_workspace.py` — wrapper delgado, mismo patrón
  exacto que `modulos/rrhh.py`.
- `interfaz/main_window.py`: import try/except (mismo estilo que los
  demás módulos) + `self._conectar("CONFIGURACION",
  ModuloConfiguracionWorkspace, "🗂️ Configuración (Nuevo)")`, agregado
  junto a (no en lugar de) las 3 líneas `_conectar` legacy existentes.
  También se eliminó el import muerto de `ModuloConfigUI`
  (`modulos/config_interfaz.py`) — nunca se le pasó a `_conectar`, nunca
  tuvo botón, no existe siquiera en este árbol de trabajo; import 100%
  huérfano, cero impacto funcional al quitarlo.
- `interfaz/menu_lateral.py`: nuevo botón `"🗂️ Configuración (Nuevo)"`
  con código `"CONFIGURACION"` — reutiliza el grupo de permisos
  `CONFIGURACION` que ya existía completo en el catálogo desde SET-1
  ("aún no wireada en el menú", ahora sí).

**Por qué NO se eliminaron `modulos/configuracion.py`/
`config_hardware.py`/`config_modules.py`, a pesar de la instrucción "si o
si"**: la investigación (agente + verificación directa propia) confirmó
que los 3 cubren funcionalidad real, hoy operativa, que el módulo nuevo
todavía no iguala en absoluto:
- `configuracion.py`: SMTP con envío de prueba real, datos fiscales de
  empresa, CRUD completo de usuarios/roles/sucursales, log de auditoría,
  credenciales de Mercado Pago, reglas de Happy Hour, y **ejecución real
  del cierre mensual** (`grp_exec "Ejecutar Cierre del Mes"`).
- `config_hardware.py`: configuración y prueba de conexión real de
  báscula, impresoras (ticket + etiquetas ZPL/EPL), cajón de dinero
  ESC/POS, escáner QR/código de barras, y red.
- `config_modules.py`: alternado de módulos habilitados/deshabilitados
  por sucursal — usa `core.services.feature_flag_service.FeatureFlagService`
  (un sistema de feature flags **distinto** al bounded context nuevo de
  SET-21; el módulo nuevo no cubre esto en absoluto) — es hoy la única
  forma de ocultar/mostrar módulos por sucursal en toda la app.

Borrar estos 3 sin reemplazo habría cumplido la letra de "si o si" pero
habría violado directamente la regla de `CLAUDE.md` de forma mucho más
grave que cualquier ítem del reporte original — el usuario perdería la
capacidad de cerrar el mes, configurar SMTP, configurar hardware, y
alternar módulos por sucursal, sin nada que lo sustituya. Se optó por
**registrar el módulo nuevo como una entrada adicional, claramente
separada** ("Configuración (Nuevo)") — esto sí resuelve el bloqueador
real que describió el usuario ("no puedo hacer pruebas") porque ahora el
módulo nuevo es alcanzable y clickeable en la app real, sin tocar ni
esconder los 3 módulos legacy que siguen siendo necesarios.

**Verificación**:
- `create_configuracion_view()` probado end-to-end contra la base de
  datos real (`data/spj_pos_database.db`, ya migrada hasta 223) — las 9
  secciones cargan sin error.
- `interfaz/main_window.py`/`interfaz/menu_lateral.py` importan limpio
  (sin ciclos, sin excepciones) tras los cambios.
- `pytest tests/integration/configuracion tests/unit/
  test_configuracion_ui_workspace.py tests/architecture/
  test_configuracion_ui_guardrails.py` — 36/36 verdes.
- `tests/integration/test_settings_module_loads.py::
  test_modulo_configuracion_loads_with_canonical_sections` — falla con
  un crash nativo (access violation) dentro de
  `modulos/configuracion.py::_cargar_usuarios_v13` (línea 1231),
  **archivo legacy que esta fase no tocó en absoluto** — confirmado
  pre-existente ejecutando esa prueba aislada; no es una regresión de
  este cambio.
- `ast.parse` repo-completo: sin errores de sintaxis.

**Pendiente, fuera de esta actualización**: dar de alta permisos
`CONFIGURACION.*` para roles no-admin (hoy solo `es_admin`/sesión
inactiva pasan sin restricción — `core/permissions.py::verificar_permiso`
line 44-50); ningún seed de `role_permisos` otorga `CONFIGURACION.*`
todavía. Cubrir las 7 secciones de solo lectura con escritura real.
Decidir, con el usuario, si en algún punto los 3 módulos legacy deben
reemplazarse (no solo coexistir) — requiere antes que el módulo nuevo
alcance paridad funcional real.

---

Fecha: 2026-08-22. El usuario pidió "SET-25 — Eliminación de legacy" con
10 sub-ítems (Consolidar tablas / Eliminar QSettings canónico / Eliminar
hardware directo / Eliminar impresión directa / Eliminar plantillas
hardcodeadas / Eliminar integraciones duplicadas / Eliminar rutas /
Eliminar imports / Vaciar allowlist / Reporte).

**Nota de numeración**: en `settings_refactor_execution_plan.md` este
slot ya existe como `SET-24+ | Eliminación de legacy | Ver checklist §70
del prompt maestro` — pero SET-24 se gastó en UI/UX por redirección
explícita del usuario (ver "Avance UI/UX"). Este reporte cubre lo que el
usuario pidió como "SET-25", que es en la práctica la fase de
eliminación de legacy que el plan venía dejando pendiente.

## Por qué esta fase se ejecutó en modo auditoría, no en modo eliminación masiva

Se investigó ANTES de tocar nada (mismo protocolo que cada SET anterior)
y se confirmó el alcance con el usuario porque el hallazgo central choca
con una regla explícita de `CLAUDE.md`:

> ❌ NO eliminar funcionalidad operativa sin migración completa

Cada SET de SET-7 a SET-23 documentó, con las mismas palabras, por qué
se detuvo antes del corte real: hardware/impresión requieren validación
contra dispositivos físicos que no se ha autorizado hacer a ciegas;
`DocumentRendererPort` es un Protocol sin implementación real en ningún
lado; solo 2 de 9 secciones de Configuración (Feature Flags, Apariencia)
tienen escritura real; el nuevo shell (`frontend/desktop/shell/`) existe
pero no está wireado en `main.py`. Es decir: **la migración completa que
la regla exige como precondición para eliminar, nunca se hizo a
propósito** — cada fase construyó la capacidad nueva y decidió
explícitamente no ejecutar el corte de producción.

El usuario confirmó (vía pregunta de alcance): ejecutar solo el
subconjunto genuinamente seguro + producir este reporte documentando por
qué el resto está bloqueado. Sin cambios a código operativo en vivo.

## Eliminado

- **2 imports muertos, código propio de esta sesión/pipeline** (cero
  riesgo — nunca referenciados fuera de su propia línea de import,
  verificado con un scanner AST antes y después):
  - `backend/domain/settings/services/configuration_cache_service.py`:
    `field` (de `dataclasses`) y `ScopeType`
    (`backend.domain.settings.enums`) — ninguno de los dos se usa en
    ningún otro punto del archivo.
  - `backend/application/queries/configuracion/workspace_query_service.py`:
    `SqliteDensityProfileRepository` — importado anticipando un listado
    de perfiles de densidad en la página de Apariencia que nunca se
    agregó (la página solo lista `Theme`, no `DensityProfile`).
- Nada más. No se eliminó ninguna tabla, columna, archivo de UI legacy,
  ruta de navegación, ni entrada de allowlist.

**Verificación**: scanner AST propio re-ejecutado tras el cambio (limpio
para ambos archivos), `ast.parse` repo-completo sin errores de sintaxis,
`pytest tests/unit/settings/ tests/integration/settings/
tests/integration/configuracion` — **255 tests verdes, cero
regresiones**.

## Investigado y explícitamente NO eliminado (por ítem)

### 1. Consolidar tablas — bloqueado

| Tabla legacy | Reemplazo tipado | Estado del reemplazo |
|---|---|---|
| `configuraciones` (genérica clave/valor) | `configuration_definitions`/`configuration_values` (migración 208) | Esquema+repos completos, pero **cero consumidores reales migrados** — `theme_engine.py`, `config_modules.py`, `EmailSettingsService` (salvo `smtp_password`) siguen leyendo/escribiendo `configuraciones` directo |
| `feature_flags` (esquema legacy dual `clave/activo` vs `feature_name/enabled/branch_id`) | `ff_flags`/`ff_rules` (migración 221) | `modulos/config_modules.py`/`modulos/delivery.py:1310` siguen siendo los consumidores reales |
| `hardware_config` | `devices`/`device_profiles` (migración 211) | Cero consumidores reales del lado nuevo |
| `print_job_log` | `print_jobs` (migración 214) | `print_job_log` tiene consumidor real y activo: `core/services/printer_service.py::PrintQueue._log_job_to_db` |
| `ticket_layouts` | `DocumentTemplate`/`DocumentTemplateVersion` | Lado nuevo sin consumir |

La única definición duplicada de `configuraciones` (un segundo `CREATE
TABLE IF NOT EXISTS configuraciones` en el schema base) **ya estaba
eliminada** desde antes de esta fase (verificado: solo queda una
definición en `migrations/m000_base_schema.py:136`) — no había nada que
hacer aquí.

Se investigó también `email_config.smtp_pass` como candidato a columna
huérfana: `EmailSettingsService.save_settings()` (SET-1) ya migró
`smtp_password` exclusivamente al `SecretStoreGateway`, así que ningún
escritor vivo llena `email_config` hoy. Pero `core/services/
reporte_email_service.py::ReporteEmailService._get_cfg()` sigue
haciendo `SELECT * FROM email_config WHERE id=1 AND activo=1` y
`_enviar()` lee `cfg["smtp_pass"]` (línea 85) — si esa tabla alguna vez
tuviera una fila (por ejemplo insertada manualmente), ese acceso
seguiría siendo válido hoy y fallaría con `KeyError` si la columna se
eliminara. **No hay precedente de migración `DROP COLUMN` en las 223
migraciones existentes de este repo** — dado que el alcance acordado
para esta fase era "solo lo genuinamente seguro", se decidió NO ejecutar
un DDL irreversible y sin precedente sobre esa base de un hallazgo
parcial (columna sin escritor, pero con un lector textual todavía
presente). Queda documentado como pendiente, no ejecutado.

### 2. Eliminar QSettings canónico — no aplica

Verificado: **cero usos de `QSettings` en todo el repositorio**. No
existe un almacén "QSettings canónico" que eliminar — toda persistencia
de preferencias de UI ya pasa por la tabla `configuraciones`. Este
ítem parece basarse en un supuesto que no corresponde a este código base;
no hay nada que ejecutar.

### 3. Eliminar hardware directo — bloqueado (RIESGO)

`hardware/lector_qr.py`, `hardware/impresora_etiquetas.py`,
`hardware/cajon_dinero.py`, `hardware/scale_reader.py`,
`core/services/hardware_service.py`, `modulos/etiquetas.py::_send_to_printer()`
son hoy la **única** ruta real de E/S de hardware (puerto serie,
`python-escpos`, sockets, `win32print`). El reemplazo
(`backend/domain/device_management/`, SET-7..10) expone únicamente
Protocols (`CashDrawerGatewayPort`/`PaymentTerminalGatewayPort`) — la
fábrica de infraestructura (`cash_register_factory.py`) conecta un
`StubCashHardwareGateway`, confirmando que ningún driver real está
wireado todavía. Eliminar el hardware directo hoy rompería cajones,
básculas, escáneres e impresoras de etiquetas reales, sin nada que los
reemplace.

### 4. Eliminar impresión directa — bloqueado (RIESGO)

`core/ticket_escpos_renderer.py` es, según el propio plan, "la única
ruta ya en buen estado" — romperla está clasificada como riesgo
Crítico/Alto en la tabla de Riesgos del plan. `core/services/
printer_service.py::PrintQueue` sigue siendo el escritor real de
`print_job_log`. `backend/domain/document_output/rendering_ports.py::
DocumentRendererPort` **no tiene ninguna implementación real en todo el
repositorio** (verificado por grep de implementadores concretos — cero
resultados). Eliminar la impresión directa hoy dejaría tickets de venta
y de delivery sin ninguna ruta de impresión funcional.

### 5. Eliminar plantillas hardcodeadas — bloqueado (RIESGO), con una aclaración

`modulos/design_tokens.py`/`qss_builder.py` son estilo de UI (temas), no
plantillas de documento — y además tienen 38 importadores reales activos
en `modulos/`, paneles de WhatsApp y tests: fuera de alcance de este
ítem por completo, no un objetivo. Las plantillas de documento reales
(tres pipelines de etiquetas en `modulos/etiquetas.py`/`hardware/
impresora_etiquetas.py`/`labels/generador_etiquetas.py`,
`core/tickets/raffle_ticket_renderer.py`, y los 9 templates de WhatsApp
pre-aprobados por Meta en `whatsapp_service/messaging/templates.py::TEMPLATES`)
siguen operando sin reemplazo real conectado. Los templates de WhatsApp
en particular no son "hardcodeados" en sentido peyorativo: WhatsApp
Business API solo permite enviar plantillas pre-aprobadas fuera de la
ventana de 24h — es un requisito de la plataforma, no deuda técnica.

### 6. Eliminar integraciones duplicadas — sin duplicados genuinos encontrados

Los 3 shims de WhatsApp (`services/whatsapp_service.py`,
`integrations/whatsapp_service.py`,
`whatsapp_service/webhook/whatsapp.py`) están protegidos explícitamente
por la regla 9 de `CLAUDE.md` — no se tocaron. Más allá de esos 3, la
propia auditoría SET-0 (`settings_legacy_inventory.md` §6.1) ya
clasificó las ~20 clases restantes relacionadas con WhatsApp como
responsabilidades distintas, "sin fusionarlas a la fuerza" — no son
duplicados. El único patrón de lectura duplicada real encontrado es
`services/mercado_pago_service.py::_get_token()`, que lee
`configuraciones` con SQL crudo en vez de pasar por
`PaymentProviderSettingsService` — pero corregirlo es una migración de
un consumidor vivo, no una eliminación de código muerto; queda fuera de
esta fase.

### 7. Eliminar rutas — bloqueado (RIESGO)

`interfaz/menu_lateral.py` sigue siendo la navegación de producción real
(confirmado: sus 3 botones de Hardware/Módulos/Configuración siguen
gateados contra `CONFIG_HARDWARE`/`CONFIG_MODULOS`/`CONFIG_SEGURIDAD`, y
`shell_registration.py` de Configuración —construido en la fase
UI/UX— existe pero deliberadamente no está wireado ahí todavía). No se
encontró ninguna ruta de API muerta o duplicada documentada en ningún
audit. Eliminar estas rutas hoy quitaría la única forma en que un
usuario real llega a esas pantallas.

### 8. Eliminar imports — hecho (subconjunto seguro), ver "Eliminado" arriba

Sin linter disponible en el entorno (`pyflakes`/`ruff`/`flake8` no
instalados, y agregar una dependencia nueva no estaba autorizado para
esta fase de "solo lo seguro") se escribió un scanner AST propio,
acotado a los paquetes que este pipeline (SET-0..23 + UI/UX) construyó:
`backend/domain/{settings,device_management,document_output,
customer_display,integrations,notifications,feature_flags,appearance,
offline}/`, `backend/infrastructure/db/{schema,repositories}/` (filtrado
a esos mismos contextos), `backend/application/{configuracion,
queries/configuracion,use_cases/configuracion}/`,
`frontend/desktop/modules/configuracion/`. El scanner también detectó 4
hallazgos en paquetes de OTROS bounded contexts (inventory,
meat_processing, procurement, transfers) que el walk recursivo alcanzó
por estar bajo el mismo directorio padre `backend/infrastructure/db/
repositories/` — **deliberadamente no tocados**, son de pipelines
ajenos a este y no hay contexto de por qué esos imports están ahí
(podrían ser reexports intencionales); limpiarlos sin ese contexto
estaría fuera del alcance acordado.

### 9. Vaciar allowlist — bloqueado (RIESGO)

No existe todavía una allowlist específica de "consumidores legacy de
Configuración" (a diferencia de CRM/Transfers/Procurement, que sí tienen
la suya). Lo que sí existe en `tests/architecture/allowlists.py` y es
relevante — `HARDCODED_NUMERIC_DEFAULTS_IN_UI_ALLOWLIST`,
`ENTITY_COMBO_MASS_LOADING_ALLOWLIST`, `PLAIN_PHONE_INPUTS_ALLOWLIST` —
todas tienen entradas para `modulos/configuracion.py`/
`config_hardware.py`/`config_modules.py`, que son **hoy la única UI de
Configuración realmente en producción** (confirmado en la auditoría
SET-0: "Monolito PyQt legacy, única UI viva hoy"). Vaciar esas entradas
sin haber remediado esos archivos primero solo pondría los tests de
guardrail en rojo contra una UI que sigue viva — a diferencia de
CASH-25, donde vaciar la allowlist fue posible porque `modulos/caja.py`
ya había sido eliminado y su reemplazo ya estaba wireado en la
navegación principal. Configuración no tiene todavía su equivalente al
corte de Caja.

### 10. Riesgo de colisión con la pista SHELL-N — confirmado

`frontend/desktop/shell/` y `frontend/desktop/modules/configuracion/`
(el resultado de la fase UI/UX) están **completamente sin comitear**
(`git status --porcelain -uall` los muestra `??`) — es una pista de
trabajo separada, no parte de la numeración SET-N, activamente
reescribiendo exactamente los archivos de navegación (`interfaz/
menu_lateral.py`, el wiring de `main.py`) que los ítems 7 y 9 tocarían.
Como no está comiteada, no hay forma de hacer `git diff`/merge seguro
contra ella — cualquier trabajo de eliminación de rutas/allowlist en
esta área debería confirmar primero si esa pista sigue activa.

## Pendientes fuera de esta fase (qué desbloquearía cada ítem)

- **Hardware/Impresión**: construir drivers reales (serie/red/ESC-POS)
  para `CashDrawerGatewayPort`/`PaymentTerminalGatewayPort`/
  `DocumentRendererPort` y validarlos contra hardware físico — trabajo
  explícitamente fuera de alcance en cada SET anterior, requiere
  autorización y acceso a hardware real.
- **Tablas**: migrar los consumidores reales (`theme_engine.py`,
  `config_modules.py`, `hardware_service.py`, `printer_service.py`) a
  los repositorios tipados nuevos, uno por uno, con tests de regresión
  — recién entonces las tablas legacy quedan seguras de eliminar.
  `email_config.smtp_pass`: decidir si vale la pena una migración
  `DROP COLUMN` (sin precedente en este repo) dado que la característica
  de reportes por email programados parece no funcional en producción
  hoy (tabla `email_config` nunca poblada por ningún escritor vivo).
- **Rutas/Allowlist**: completar el wireado real de
  `frontend/desktop/modules/configuracion/` en `main.py`/`MainWindow`
  (la pista SHELL-N), y solo entonces remediar
  `modulos/configuracion.py`/`config_hardware.py`/`config_modules.py`
  o eliminarlos, análogo a CASH-25.
- **Integraciones**: migrar `services/mercado_pago_service.py::_get_token()`
  para usar `PaymentProviderSettingsService` en vez de SQL crudo contra
  `configuraciones` — tarea acotada, no parte de esta fase.
- **Imports en otros bounded contexts**: los 4 hallazgos en
  inventory/meat_processing/procurement/transfers quedan para quien
  tenga contexto de esos pipelines, no se tocan aquí.

## Verificación

```bash
python -m pytest tests/unit/settings/ tests/integration/settings/ tests/integration/configuracion -q
# 255 passed, cero regresiones
```

Chequeo de sintaxis repo-completo (`ast.parse` sobre cada `.py`): sin
errores.
