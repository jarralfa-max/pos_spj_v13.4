# SHELL-0 — Inventario de responsabilidades legacy: main.py / AppContainer / MainWindow / MenuLateral / SessionContext

Auditoría de solo lectura. No se modificó código de aplicación. Alcance: los 5
archivos primarios (`main.py`, `core/app_container.py`, `core/session_context.py`,
`interfaz/main_window.py`, `interfaz/menu_lateral.py`) y sus consumidores directos.

Clasificación por responsabilidad: **REUSE** (se conserva tal cual detrás de la
nueva fachada) · **MOVE** (se traslada de carpeta/capa sin reescritura de fondo)
· **WRAP_TEMPORARILY** (se envuelve con un adaptador hasta que el consumidor
migre) · **REWRITE** (se reescribe porque mezcla capas o tiene defectos) ·
**DELETE** (código muerto/duplicado a eliminar) · **BLOCKED** (no se puede tocar
todavía; requiere condición externa).

---

## 1. `main.py` — Bootstrap del proceso

| # | Responsabilidad | Clasificación | Notas |
|---|---|---|---|
| 1.1 | `QApplication.setAttribute(AA_ShareOpenGLContexts)` antes de crear `QApplication` | REUSE | Debe ejecutarse en el módulo de entrada del futuro `DesktopApplicationBootstrapper`, en el mismo orden. |
| 1.2 | Inserción de `_BASE_DIR` en `sys.path` | MOVE | Candidato natural a `AppPaths` (skill spj-refactor regla 27). |
| 1.3 | `setup_logging()` con fallback a `logging.basicConfig` | REUSE | El propio try/except ya es el patrón defensivo correcto; mover a `DesktopApplicationBootstrapper.configure_logging()`. |
| 1.4 | `sys.excepthook = _crash_handler` (crash handler global con `QMessageBox`) | MOVE | Debe vivir en el bootstrapper; es responsabilidad de arranque, no de `main.py` como script. |
| 1.5 | Cálculo de `DB_PATH` (`data/spj_pos_database.db`) + `set_db_path()` | MOVE | A `AppPaths` / `CompositionRoot`. |
| 1.6 | `_instancia_unica()` (QLocalServer/QLocalSocket, single-instance lock) | MOVE | Responsabilidad de bootstrap del proceso; no depende de UI de negocio. |
| 1.7 | `_verificar_bd()` (`PRAGMA integrity_check` + diálogo de restaurar backup) | REWRITE | Hoy hace `sqlite3.connect()` crudo y muestra `QMessageBox` desde una función de "bootstrap" — mezcla infra + UI. Debe separarse en `DatabaseIntegrityChecker` (infra, sin Qt) + un manejador de UI que decide qué mostrar. |
| 1.8 | `_restaurar_backup()` (mueve BD dañada, copia backup, importa `modulos.sistema.backup_engine`) | WRAP_TEMPORARILY | Depende de `modulos/sistema/backup_engine.py` (aún no migrado). Envolver tras un `BackupService` port hasta que ese módulo se mueva a `infrastructure/`. |
| 1.9 | `_bootstrap_db()` — ejecuta `bootstrap_database()` y, si falla, hace fallback manual llamando `migrator.up()` + `migrate_db()` + `verificar_tablas()` | **BLOCKED** | Ver `application_bootstrap_audit.md` §"Migraciones duplicadas". Causa: el flujo real de `inicializar_sistema()` invoca este fallback Y TAMBIÉN `bootstrap_database()` directamente Y TAMBIÉN un tercer bloque con `migrator.up/migrate_db/verificar_tablas` (líneas 173-217). Riesgo: tres rutas de migración en el mismo arranque; si divergen silenciosamente (una atrapa una excepción que la otra no) el estado de la BD puede quedar inconsistente sin que el operador se entere. Dependencia: `migrations/engine.py` (`MIGRATIONS` list), `scripts/bootstrap_db.py`. Responsable: quien construya `CompositionRoot.bootstrap_database()`. Condición exacta de eliminación: colapsar las 3 rutas en una sola función idempotente única, cubierta por un test que verifique que `schema_migrations` recibe cada versión exactamente una vez por arranque, antes de borrar las rutas redundantes. |
| 1.10 | Bloque de migraciones con `assert_uuid_identity()` / `IntegerIdentityError` (REGLA CERO gate) | REUSE | Es exactamente el guardado que exige la regla cero del proyecto — debe sobrevivir intacto en el nuevo bootstrapper, incluyendo el mensaje de error y el `sys.exit(1)`. |
| 1.11 | `except Exception: logger.error(...)` que **continúa** tras fallo de migraciones ("continuando con repositorios como fallback") | BLOCKED | Causa: un error no-`RuntimeError`/no-`IntegerIdentityError` en migraciones se traga y la app sigue arrancando con un `AppContainer` sobre una BD potencialmente a medio migrar. Riesgo: silent startup failure — exactamente el patrón que `application_bootstrap_audit.md` marca como el mayor riesgo. Dependencia: catálogo de excepciones que puede lanzar `migrator.up`. Responsable: dueño de `CompositionRoot`. Condición de eliminación: clasificar cada excepción posible de migración como fatal o no-fatal explícitamente (no un `except Exception` genérico) antes de permitir continuar. |
| 1.12 | Construcción de `AppContainer(db_path=DB_PATH)` | REWRITE | Se convierte en `CompositionRoot.build()`; ver `container_dependency_inventory.md`. |
| 1.13 | `launch_microservice_async(app_root)` (arranque del microservicio WhatsApp) | REUSE | `core/services/microservice_launcher.py` ya está aislado y es correcto (thread daemon, healthcheck, timeout). Solo cambia quién lo invoca. |
| 1.14 | `container.whatsapp_webhook.start()` | MOVE | Debe quedar detrás de un puerto explícito en vez de `hasattr(container, ...)`. |
| 1.15 | Construcción de `MainWindow(container)` + `.show()` | REWRITE | Pasa el `AppContainer` completo a la ventana — viola la regla 15 del skill ("no pasar AppContainer completo a servicios"; MainWindow desde SHELL en adelante debe recibir solo lo que necesita vía `ApplicationShellWindow`). |
| 1.16 | `VersionChecker` async + `window.mostrar_notif_update` | REUSE | Aislado y con manejo de ciclo de vida correcto (guardado como atributo de `window` para evitar GC del QThread). |
| 1.17 | Loop de cleanup al cerrar (`whatsapp_webhook.stop()`, `container.close()`, `_LOCAL_SERVER.close()`) con `except Exception: pass` por cada uno | REWRITE | Correcto en intención (best-effort shutdown) pero cada `except: pass` oculta errores de cierre sin loguearlos ni una vez — debe al menos loguear a nivel debug/warning antes de continuar. |

---

## 2. `core/app_container.py` — Contenedor de dependencias

| # | Responsabilidad | Clasificación | Notas |
|---|---|---|---|
| 2.1 | Construcción de `self.session = SessionContext()` | REUSE | `SessionContext` ya es limpio (ver §5). |
| 2.2 | Apertura de conexión canónica (`set_db_path` + `get_connection()`, WAL + FK + busy_timeout) | REUSE | Correcto, es la ruta canónica exigida por la regla "PyQt no debe ejecutar SQL / servicios no crean schema". |
| 2.3 | Resolución de sucursal instalada (`resolve_installation_branch`) + espejo `self.sucursal_id`/`self.sucursal_nombre` | WRAP_TEMPORARILY | La lógica en sí (`branch_resolution.py`) ya es UUID-limpia; lo que hay que envolver es el **patrón de espejo** (`AppContainer.sucursal_id` duplicando `session.sucursal_id`) hasta que todos los consumidores lean solo de `SessionContext`. |
| 2.4 | Instanciación de ~35 repositorios (capa 1) | MOVE | A `infrastructure/persistence/*`, sin cambios de lógica — son ya clases repository correctamente aisladas. |
| 2.5 | Instanciación de ~60 servicios de aplicación/dominio (capa 2-3), la mayoría con `try/except` individual que deja el atributo en `None` si falla | BLOCKED | Causa: cada servicio opcional (`report_engine`, `forecast_engine`, `uc_*`, etc.) se envuelve en su propio try/except silencioso (`logger.debug`). Riesgo: un consumidor que hace `container.forecast_engine.algo()` sin `hasattr()` primero explota en producción con `AttributeError: NoneType`, y el log del motivo real quedó en nivel `debug` (invisible salvo con logging verboso). Dependencia: cada uno de esos ~15 servicios "opcionales" y sus imports transitivos. Responsable: dueño de `CompositionRoot` + cada bounded context. Condición de eliminación: sustituir el patrón `try/except → None` por un `Result`/`ServiceRegistry` explícito que documente qué servicios son opcionales por diseño vs. cuáles deberían ser fatales si fallan. |
| 2.6 | `CashRegisterApplicationService` + ~20 use cases de caja (bloque try/except de 120 líneas, líneas 188-322) | REUSE (la lógica) / REWRITE (el emplazamiento) | El wiring de casos de uso de caja en sí es correcto y ya usa UUIDv7 (`CashSessionPermissionChecker(self.session)`); el problema es que vive inline en el constructor del contenedor en vez de una factory dedicada de bounded context (ya existe el patrón correcto en `backend/infrastructure/desktop/cash_register_factory.py` para la UI — falta aplicar el mismo patrón al wiring de servicios). |
| 2.7 | `_configurar_scheduler()` — registra ~10 tareas periódicas (alertas, backup, depreciación, escalación de pedidos WA, recordatorios, mantenimiento semanal, auto-cierre de turno, reporte nocturno) | MOVE | Cada tarea es lógica de aplicación válida; el conjunto debe moverse a un `SchedulerBootstrapper` en `infrastructure/messaging/` o `application/`, no vivir como método privado de 200+ líneas dentro del DI container. |
| 2.8 | `_check_escalacion_pedidos` / `_check_recordatorios_ordenes` (SQL directo embebido dentro de closures del scheduler) | REWRITE | Estas closures ejecutan `self.db.execute("SELECT ... FROM pedidos_whatsapp ...")` y `UPDATE ... SET notificado_gerente=1` directamente — es SQL en una capa que debería ser orquestación pura. Debe extraerse a un repository/query service antes de mover el scheduler. |
| 2.9 | `set_sucursal_activa()` — reflexión sobre `self.__dict__` para propagar `sucursal_id` a "todos los servicios que tengan el atributo" | BLOCKED | Causa: usa `hasattr(svc, 'sucursal_id')` / `hasattr(svc, 'set_sucursal')` genéricamente sobre TODO el `__dict__` del contenedor. Riesgo: cualquier servicio nuevo que por casualidad tenga un atributo `sucursal_id` (aunque no sea semánticamente la sucursal activa) será mutado silenciosamente al cambiar de sucursal — acoplamiento implícito, no hay lista explícita de quién participa. Dependencia: todos los servicios del contenedor. Responsable: dueño de `SessionContext`/eventos. Condición de eliminación: reemplazar por suscripción explícita a `ACTIVE_BRANCH_CHANGED` (el evento ya existe y se publica, ver 3.9) — cada servicio que necesite reaccionar se suscribe él mismo en vez de ser barrido por reflexión. |
| 2.10 | `set_session_user()` / `clear_session()` — delega a `SessionContext` pero mantiene atributos espejo `self.sucursal_id/nombre` | WRAP_TEMPORARILY | Mismo patrón de doble fuente de verdad que 2.3. |
| 2.11 | `close()` — cierra `printer_service`, detiene `scheduler_service`, cierra `self.db` | REUSE | Orden correcto y con manejo de errores por partes. |

---

## 3. `interfaz/main_window.py` — Ventana principal / orquestador visual

| # | Responsabilidad | Clasificación | Notas |
|---|---|---|---|
| 3.1 | ~26 imports `try/except` de `modulos.*` (uno por módulo de negocio) | MOVE | Este es exactamente el patrón que `ModuleRegistry` + view factories deben reemplazar. Cada bloque try/except es, en esencia, una entrada de catálogo de módulos escrita a mano. Ver `navigation_route_inventory.md`. |
| 3.2 | `DialogoLogin` (QDialog completo: UI de login, `paintEvent` con gradiente, drag sin bordes, lectura de sucursal de instalación, llamada a `auth_service.authenticate`) | MOVE | Es una vista legítima; debe convertirse en la vista de `AuthenticationCoordinator`, sin lógica de negocio nueva. |
| 3.3 | `DialogoLogin._leer_sucursal_instalacion()` (usa `resolve_installation_branch` vía `self.auth_service.repo.db`, accediendo a atributos internos del repo) | REWRITE | `getattr(getattr(self.auth_service, 'repo', None), 'db', None)` es un acceso frágil a la cadena interna del servicio; debería recibir la conexión o un `BranchResolutionService` inyectado explícitamente. |
| 3.4 | `MainWindow.__init__` — arma menú superior, UI, stack de pantallas, tema, logo, suscripción a eventos de catálogo | MOVE | Se convierte en la construcción de `ApplicationShellWindow` (GlobalTopBar + ContentHost + GlobalSidebar). |
| 3.5 | `_construir_todas_las_pantallas()` / `_conectar()` — instancia cada `ModuloXxx(self.container)` pasando el contenedor completo, agrega al `QStackedWidget`, aplica auto-estilos, conecta `abrir_modulo`/`navigation_requested` | REWRITE | Pasar `self.container` completo a cada módulo es el patrón central que la nueva arquitectura de `RouteRegistry` + view factories debe romper — cada módulo debería recibir solo sus dependencias declaradas. Ya existe un test de arquitectura (`tests/architecture/test_sales_pos_ui_does_not_receive_app_container.py`, `test_customers_crm_ui_does_not_receive_app_container.py`) que exige exactamente esto para 2 módulos — el patrón objetivo ya está validado, falta generalizarlo a los ~20 restantes. |
| 3.6 | `_registrar_placeholder()` (pantalla de aviso "Módulo en integración..." si el import falló) | REUSE | Buen patrón defensivo — un módulo roto no tira la app. Debe conservarse en `ModuleRegistry`/`RouteRegistry`. |
| 3.7 | `mostrar_login()` — oculta ventana, muestra `DialogoLogin` modal, cierra la app si se cancela | MOVE | A `AuthenticationCoordinator`. |
| 3.8 | `_propagar_usuario()` (110 líneas) — set session, resuelve sucursal con lógica de invalidez (`_inv()`), actualiza barra de sesión, carga permisos vía `PermissionQueryService`, aplica feature flags al menú, notifica a cada widget del stack (`set_usuario_actual`/`set_sucursal`/`refresh_permissions`), llama `container.set_sucursal_activa()`, publica `ACTIVE_BRANCH_CHANGED` | BLOCKED | Causa: concentra en un solo método de la vista: resolución de identidad de sesión, autorización, propagación a ~25 widgets por duck-typing (`hasattr`), mutación del contenedor y publicación de eventos de dominio. Riesgo: es el método más denso de todo el shell — cualquier refactor de `MainWindow` que no preserve el orden exacto de estos pasos (sesión → permisos → feature flags → fan-out a widgets → contenedor → evento) puede dejar módulos con sucursal/permiso desactualizado sin ningún error visible (todo son `except Exception: pass`/`logging.debug`). Dependencia: `PermissionQueryService`, `ModuleConfig`, `EventBus`, contrato duck-typed de cada módulo (`set_usuario_actual`, `set_sucursal`, `refresh_permissions`). Responsable: dueño de `AuthenticationCoordinator` + `ApplicationShellWindow`. Condición de eliminación: reemplazar el fan-out por `hasattr` por una interfaz explícita (`Protocol`) que cada módulo implemente, y separar "propagar sesión" de "publicar evento de dominio" en pasos testeables por separado. |
| 3.9 | `aplicar_sucursal_activa()` — replica gran parte de la lógica de 3.8 para cambios de sucursal en caliente (re-anclaje desde Configuración) | REWRITE | Duplica ~40 líneas de 3.8 con variaciones sutiles (no vuelve a cargar permisos, por ejemplo). Candidato claro a unificarse con 3.8 en un solo `SessionPropagationService`. |
| 3.10 | `_suscribir_eventos_catalogo()` / `_on_branches_changed*` / `_on_products_changed*` — hot-refresh de catálogos vía EventBus con debounce | REUSE | Patrón correcto (salta a hilo Qt con `QTimer.singleShot`, debounce de ráfagas). Documentar y mover tal cual a `ApplicationShellWindow`. |
| 3.11 | `_arrancar_session_timeout()` / `_on_session_warning()` (`SessionTimeoutMonitor`) | REUSE | Correcto, usa `installEventFilter` global. |
| 3.12 | `_mostrar_inbox_login()` — muestra notificaciones pendientes del inbox tras login | **REWRITE (bug real)** | Contiene una variable no definida: `self.container.notification_service.marcar_inbox_leido(empleado_id=row[0])` en la línea final del método usa `row`, que nunca se asigna en ese scope (la variable local se llama `personal_id`, no `row`). Esto lanza `NameError` en tiempo de ejecución cada vez que hay notificaciones pendientes que mostrar, pero el `except Exception as e: logger.debug(...)` de nivel método lo traga silenciosamente — el inbox nunca se marca como leído y nadie se entera. Debe corregirse (`row[0]` → `personal_id`) como parte de la migración de este método, con un test de regresión que hoy no existe. |
| 3.13 | `manejar_navegacion()` — switch de pantalla en el `QStackedWidget`, chequeo de permisos vía `core.permissions.verificar_acceso_modulo`, sincroniza sidebar | MOVE | Es el precursor directo de `DesktopRouter.navigate()`. |
| 3.14 | `_NAVIGATION_ROUTES` + `_handle_navigation_intent()` + `_resolve_legacy_customer_id()` (CRM-32/CRM-37 cross-module navigation con contexto) | REUSE | Patrón ya correcto y extensible (mapa `route → código`, contrato `aplicar_contexto(context)`); es el prototipo de lo que `RouteRegistry` debe generalizar. |
| 3.15 | `_aplicar_tema()` / `_cargar_tema_inicial()` / `_cargar_logo_empresa()` | MOVE | Responsabilidad de `GlobalTopBar`/tema del shell. |
| 3.16 | `closeEvent()` / `showEvent()` — detiene threads (`_gestor_notif`, `_version_checker`) al cerrar; arranca notificaciones y login tras el primer `show()` | REUSE | Manejo de ciclo de vida de QThread ya correcto (evita el warning "QThread: Destroyed"). |
| 3.17 | `_configurar_busqueda_global()` / `_abrir_busqueda_global()` (Ctrl+F, búsqueda de productos/clientes/ventas) | REWRITE | Usa `MainWindowReadRepository` (correcto, sin SQL directo en la vista) pero es 100% lógica de aplicación (búsqueda cruzada) viviendo dentro de la vista — candidato a `GlobalSearchQueryService` + un componente `ContentHost` reutilizable. |
| 3.18 | `_iniciar_gestor_notificaciones()` — doble ruta de notificación: EventBus (`PEDIDO_NUEVO`) + polling `GestorNotificaciones` (fallback 30s) | WRAP_TEMPORARILY | El fallback de polling es deuda intencional documentada ("Cola de mensajes (retries) — Pendiente" en el benchmark de FASE 2); envolver ambas rutas detrás de un solo `OrderNotificationService` hasta que el polling pueda eliminarse. |

---

## 4. `interfaz/menu_lateral.py` — Sidebar / navegación

| # | Responsabilidad | Clasificación | Notas |
|---|---|---|---|
| 4.1 | Constante `MODULOS` (lista de 23 strings en minúsculas: `"ventas"`, `"clientes"`, `"merma"`, `"contabilidad"`, ...) | **DELETE** | Código muerto: no se usa en ningún otro punto del archivo ni se importa desde otro módulo (grep confirma cero referencias fuera de esta declaración). Además está desincronizada con los códigos de ruta reales (`"ventas"` vs `"POS"`, `"merma"` vs `"MERMAS"`, incluye `"contabilidad"` que no es una ruta registrada en ningún lugar). Eliminar antes de construir `RouteRegistry` para no heredar una fuente de verdad falsa. |
| 4.2 | `_build_sidebar_qss()` / `_SIDEBAR_DARK_QSS` — QSS generado desde `design_tokens.Colors.SIDEBAR` | REUSE | Correcto: el sidebar es intencionalmente siempre oscuro por regla de producto; la generación centralizada en `design_tokens` es el patrón correcto para `GlobalSidebar`. |
| 4.3 | `enforce_dark_mode()` — reaplica QSS oscuro tras cualquier cambio de tema global | REUSE | Necesario mientras el tema global sea mutable en caliente; documentar la invariante al mover a `GlobalSidebar`. |
| 4.4 | `_configurar_ui()` — construye secciones fijas (Operaciones/Comercial/Producción/Administración/Sistema) con botones hardcodeados uno por uno | MOVE | Es exactamente la superficie que `RouteRegistry`/catálogo de navegación (Inicio, Punto de Venta, Pedidos y Delivery, ...) debe reemplazar por datos, no por 30 líneas de `layout_botones.addWidget(self._crear_boton(...))`. Ver `navigation_route_inventory.md` para el mapeo completo. |
| 4.5 | `set_permisos()` / `_is_allowed_by_permissions()` — filtra botones por permiso `{codigo}.ver` / `{codigo}.acceder`, admin/wildcard bypass | REUSE | Ya es data-driven y no hardcodea roles (usa permisos, ver `feedback_permissions_compras_standard` en memoria: dotted `MODULO.accion`). Cubierto por tests de arquitectura (`test_menu_lateral_uses_permissions_not_roles.py`, `test_menu_lateral_respects_role_permissions.py`). |
| 4.6 | `set_module_config()` — oculta (nunca concede) botones vía feature flags (`toggle_map` fijo de 5 entradas) | REUSE | Patrón correcto: "solo para ocultar, nunca para conceder acceso negado" ya está documentado en el propio código. |
| 4.7 | `_apply_access_filters()` / `hidden_reason()` — combina permiso + feature flag + búsqueda en una sola decisión de visibilidad, con motivo diagnosticable | REUSE | Buen diseño para debug (`hidden_reason` expone por qué un botón está oculto) — conservar tal cual. |
| 4.8 | `_matches_search()` / `_filtrar_modulos_menu()` / Ctrl+K | REUSE | Búsqueda cliente-side simple sobre labels ya cargados; sin lógica de negocio. |
| 4.9 | `_crear_boton()` / `_on_clic_boton()` / `set_modulo_activo()` (grupo exclusivo simulado con `setChecked`) | REUSE | Correcto. |
| 4.10 | `set_status_badges()` — inyecta contador de pedidos/programados/ajustes en el label de "Delivery" mutando texto y tooltip | WRAP_TEMPORARILY | Acopla el sidebar a la existencia de un botón con código `"DELIVERY"` por string literal (`if str(btn.property("modulo_codigo")...) != "DELIVERY": continue`); envolver detrás de un contrato de "badge por ruta" hasta que `RouteRegistry` permita declarar badges por metadata en vez de por comparación de string. |
| 4.11 | `toggle_collapse()` / `_aplicar_modo_colapso()` / `_extraer_icono()` (animación de ancho, colapso a solo íconos) | REUSE | Puramente presentacional, sin lógica de negocio; trasladable a `GlobalSidebar` sin cambios. |

---

## 5. `core/session_context.py` — Fuente única de verdad de sesión

| # | Responsabilidad | Clasificación | Notas |
|---|---|---|---|
| 5.1 | Estado privado (`_user_id`, `_usuario`, `_rol`, `_active_branch_id`, `_active_warehouse_id`, `_permisos`, `_is_active`) con properties de solo lectura | REUSE | Ya cumple REGLA CERO: comentarios explícitos ("D6/REGLA CERO: la sucursal es UUIDv7 (str) y su ÚNICA fuente es `_active_branch_id`"), sin PK enteras, sin `int(...)` sobre IDs. Es el único de los 5 archivos primarios que ya está en el estado objetivo — no requiere reescritura, solo trasladarse de carpeta si `AuthenticationCoordinator` termina viviendo fuera de `core/`. |
| 5.2 | `set_user()` — resuelve `active_branch_id` con fallback a `sucursal_id` legacy (`_suc_legacy = user_data.get('sucursal_id')`) | WRAP_TEMPORARILY | El fallback es defensivo (por si el dict de usuario aún no trae `active_branch_id` explícito) pero technically acepta cualquier valor no-UUID como sucursal si viniera de una fuente vieja. No hay validación de formato UUIDv7 en este punto — depende de que el emisor (`AuthRepository`/`DialogoLogin`) ya entregue UUID. Confirmar con tests de integridad antes de eliminar el fallback. |
| 5.3 | `tiene_permiso()` — admin bypass + wildcard exacto + wildcard de módulo (`"MODULO.*"`) + global (`"*"`) | REUSE | Coincide con el patrón CRM-29 documentado en memoria del proyecto (permisos con wildcard de módulo). |
| 5.4 | `to_dict()` — expone `sucursal_id` como alias explícito de `active_branch_id` con comentario "una sola identidad" | REUSE | Ejemplo de buena práctica a replicar en otros DTOs de sesión. |

---

## 6. Resumen de bloqueos (BLOCKED) — requieren decisión antes de tocar código

| Bloqueo | Causa | Riesgo | Dependencia | Responsable | Condición de eliminación |
|---|---|---|---|---|---|
| 1.9 Migraciones triplicadas en `main.py` | 3 rutas de bootstrap de esquema en el mismo arranque | Estado de BD inconsistente sin aviso si divergen | `migrations/engine.py`, `scripts/bootstrap_db.py` | Dueño de `CompositionRoot` | Colapsar a una sola función idempotente + test de conteo único en `schema_migrations` |
| 1.11 `except Exception` que continúa tras fallo de migración | Catch genérico no diferencia fatal/no-fatal | App arranca sobre BD a medio migrar sin bloquear | Catálogo de excepciones de `migrator.up` | Dueño de `CompositionRoot` | Clasificar excepciones explícitamente antes de permitir continuar |
| 2.5 ~15 servicios opcionales `try/except → None` | Fallos silenciosos a nivel `debug` | `AttributeError: NoneType` en producción sin traza útil | Cada servicio opcional y sus imports | Dueño de `CompositionRoot` + cada bounded context | `ServiceRegistry` explícito que documente opcionalidad por diseño |
| 2.9 `set_sucursal_activa()` por reflexión sobre `__dict__` | Acoplamiento implícito vía `hasattr` | Mutación silenciosa de cualquier servicio con atributo `sucursal_id` casual | Todos los servicios del contenedor | Dueño de `SessionContext`/eventos | Reemplazar por suscripción explícita a `ACTIVE_BRANCH_CHANGED` |
| 3.8 `_propagar_usuario()` concentra 6 responsabilidades | Método más denso del shell, todo con `except: pass` | Módulo con sesión/permiso desactualizado sin error visible | `PermissionQueryService`, `ModuleConfig`, `EventBus`, contrato duck-typed de cada módulo | Dueño de `AuthenticationCoordinator` | Interfaz `Protocol` explícita + separar propagación de sesión de publicación de evento |

---

*Generado en FASE SHELL-0 (auditoría). No se modificó ningún archivo de aplicación.*
