# SET-26 — Re-auditoría de Configuración, Dispositivos, Documentos e Integraciones (2026-10-04)

El prompt maestro de Configuración (76 secciones) se volvió a pegar. SET-0..25
ya estaban construidos (agosto), y desde entonces se borraron `core/`,
`modulos/` e `interfaz/`. Esto es una **re-auditoría sobre lo que corre de
verdad**: la vista de Configuración armada por la shell viva contra una COPIA de
la base real, recorrida con el dueño (JoseR, `system_owner`) y con usuarios de
prueba `gerente`, `solo_lectura` y `cajero` creados sólo en la copia.

## 1. Lo que se encontró (medido, no supuesto)

| # | Hallazgo | Gravedad |
|---|----------|----------|
| 1 | La shell armaba Configuración con `ConfiguracionModuleActivator`, que nunca pasaba `has_permission`: **un `solo_lectura` (19 permisos) veía las 11 secciones**, incluidos usuarios y auditoría. El presenter no revalidaba ninguna lectura. Las pruebas no lo veían: usaban OTRA fábrica (`create_configuracion_view`), la única que filtraba. Dos composiciones con las mismas 84 dependencias. | P0 |
| 2 | «Nueva ruta de impresión» pedía tipo de documento y módulo como **texto libre**; el tooltip sugería el módulo «ventas», pero Ventas pide la ruta con `sales`. `PrintRoute.matches` compara exacto: la ruta se guardaba y no emparejaba nunca, y el POS seguía diciendo «no hay impresora configurada». Lo mismo con «Ticket de venta» o cualquier canal (ningún consumidor resuelve por canal). La tabla de rutas mostraba UUIDs en respaldo y ámbito. | P0 |
| 3 | `logistics.qr_signing_secret` en **texto plano** en `configuraciones` (§46); si la lectura fallaba se generaba otro en silencio, lo que invalida toda etiqueta impresa. | P1 |
| 4 | 12 de las 23 claves de `configuraciones` sin **ningún lector** (sync, escalación de WhatsApp legacy, `app_version`). | P2 |
| 5 | `HardwareDiagnosticsService` abría `serial.Serial` desde la capa de aplicación (§70.6), sin consumidores. Su prueba inspeccionaba pantallas legacy ya borradas y fallaba por `FileNotFoundError`. | P2 |
| 6 | **Gobierno de configuración (§5-11) 100% a oscuras**: `ConfigurationDefinition/Value`, políticas de herencia/aprobación/rollback y repositorios existen, pero 0 casos de uso, 0 UI, 0 consumidores y 0 filas. Los 30 archivos que leen parámetros siguen en la tabla clave/valor `configuraciones`. | P0 (núcleo del prompt) |
| 7 | **Siete tablas paralelas de trabajos de impresión** (`print_jobs`, `cash_print_jobs`, `logistics_print_jobs`, `loyalty_card_print_jobs`, `inventory_label_print_log`, `transfer_print_log`, `delivery_print_log`; más la legacy `print_job_log`). Ventas imprime sin `PrintJob` si no hay plantilla `SALE_TICKET`. | P1 (§76) |
| 8 | Funciones de la Configuración legacy **sin pantalla** desde el borrado de `modulos/`: prueba de SMTP, verificación de Mercado Pago, Happy Hour, cierre mensual, módulos por sucursal. Sus casos de uso existen, sin llamadores. | P1 |
| 9 | `gerente` nunca recibió los permisos granulares de lectura de Configuración (patrón otorgable ≠ otorgado de la 260/290). | P1 |
| 10 | Base real: 0 dispositivos, 0 rutas, 0 plantillas. No es un error de código: falta configurarlos (y el hallazgo 2 lo impedía en la práctica). | — |

## 2. Lo que se cerró (commit 1)

1. **Una sola composición** — `configuracion_routes.build_configuracion_view(connection, session_context)`; la shell y las pruebas la usan. Se borró la duplicada (287 líneas del activador).
2. **Guardia de ruta** en `ConfiguracionView.show_route`: una sección sin permiso de lectura no se construye y muestra `NO_PERMISSION`.
3. **Revalidación de lecturas** en el presenter (§57): `load_page` y 21 lectores sensibles (usuarios, roles, auditoría, integraciones, flags, notificaciones, offline). Las tarjetas Roles y Auditoría muestran `NO_PERMISSION` sin su permiso propio.
4. **Rutas de impresión**: tipo de documento y módulo se eligen de listas cerradas (`document_type_labels.py`, `PrintRouteModule` en backend, el mismo valor que pide Ventas); sin campo de canal. `CreatePrintRouteUseCase` rechaza códigos que nadie resolvería. La tabla muestra nombres, no UUIDs.
5. **Migración 300** — secreto de QR al almacén de secretos.
6. **Migración 301** — retira las 12 claves sin lector.
7. **Migración 302** — `gerente`: lectura de todo + dispositivos/asignaciones/rutas (decisión del usuario).
8. `HardwareDiagnosticsService` eliminado; su prueba reescrita sobre lo que sigue existiendo.
9. `test_empresa_page_installation_branch.py` repuntado de `repositories.config_repository` (borrado) al repositorio canónico.

Verificado en la copia real: dueño 11/11 secciones; `solo_lectura` 1/11
(«General»); `gerente` 11/11 tras la 302.

## 3. Gobierno de configuración (hallazgo 6) — commit 2

**Regla del usuario (2026-10-04): Configuración no controla nada que ya exista
en otro módulo** — dos pantallas para lo mismo se contradicen. Se construyó una
página «Parámetros» en Configuración y se retiró antes del commit por esa regla.

Lo que quedó:

- **Backend compartido, sin pantalla en Configuración** (`backend/application/settings/`):
  `catalog.py` (18 parámetros tipados con su valor de omisión, ámbitos y
  criticidad), `ConfigurationReader` (herencia con la regla única del dominio;
  devuelve valor, ámbito de origen y versión; sin caché), `GovernedSettingsWriter`
  (versiona, expira la versión anterior, audita en `configuracion_audit_log` en
  la transacción del módulo y publica `CONFIGURATION_*` después del commit; un
  parámetro crítico no se puede cambiar por aquí).
- **Contextos cortados** — cada uno sigue editándose en SU pantalla:
  Fidelidad (6 parámetros, Fidelidad → Ajustes), Tarjetas (2, privacidad),
  Cárnico (3 tolerancias; el resolvedor propio de 9 niveles pasa a la regla
  única con los ámbitos SPECIES/WORK_CENTER/PRODUCTION_AREA/PLANT agregados al
  dominio, misma precedencia de §17), Costeo (política de costo desde Precios →
  Configuración; método y factores de reparto), Compras (tolerancias de factura
  afinables por proveedor, ámbito SUPPLIER; el nivel «naturaleza» se retiró:
  ningún llamador lo pedía).
- **Migración 303**.
- **Eliminado sin consumidores**: `TicketSettingsQueryService`,
  `HardwareSettingsQueryService`, `SaveHardwareConfigUseCase` (+ su comando).
- **Sin pantalla en ningún módulo** (igual que antes del corte): tolerancias de
  factura de Compras, método/factores de reparto de Costeo y las tolerancias de
  Cárnico por especie/producto/etc. Su editor pertenece a SU módulo.

## 4. Duplicados de Configuración frente a otros módulos (decisiones del usuario)

| Sección | Contraparte | Decisión | Hecho |
|---|---|---|---|
| Dispositivos: cajones y terminales de pago | Caja (CASH-18: `cash_drawers`, `pos_terminals`, su página) | Los administra Caja | Configuración ya no los ofrece; los casos de uso de perfil y asignación los rechazan |
| Documentos/rutas: tarjeta de fidelidad, boleto de sorteo | Fidelidad (diseñador versionado, impresión de boletos) | Los administra Fidelidad | Fuera de las listas de plantillas y rutas; los casos de uso los rechazan |
| Notificaciones (0 consumidores) | Caja tiene la suya | Se concentrarán en un solo módulo en el futuro | Sin cambios por ahora |

## 5. Resto del bloque (2026-10-04, decisión del usuario)

Happy Hour y cierre mensual se omiten: los controlan Fidelidad y Finanzas.

- **Permisos por rol** (Usuarios y Roles → Roles → «Permisos»). `SaveRolePermissionsUseCase`
  envolvía un servicio borrado con `core/` y nunca se pudo ejecutar; reescrito
  en el mismo archivo como la única ruta. Matriz con los 35 módulos y 1081
  acciones del catálogo canónico, por módulo, con búsqueda y marcar/quitar todo.
  El caso de uso revalida: permiso `CONFIGURACION.rol.permisos` (migración 304),
  sólo códigos del catálogo, sin escalamiento (nadie otorga lo que no tiene,
  salvo dueño y administradores), roles administradores no se editan, al dueño
  no se le quita nada, nadie se quita en su propio rol lo que necesita para
  volver a la pantalla. Auditoría con antes/después. Rige en el siguiente
  inicio de sesión.
- **Probar conexión** (Integraciones → Salud). La salud sólo se capturaba a
  mano; ahora llama a Mercado Pago con el token guardado en el almacén de
  secretos y registra el resultado real. El token no sale a la pantalla ni al
  mensaje. Otros proveedores: registro manual, como antes.
- **Módulos por sucursal** (migración 305): un flag `modulo.<id>` por módulo,
  encendido; una regla de sucursal en Feature Flags lo apaga y la barra global
  lo oculta y el enrutador no lo abre. Configuración no se puede apagar. Se
  retiró `SaveModuleToggleUseCase` (duplicaba esto sobre un servicio borrado).
- **Prueba de SMTP**: queda para el módulo único de notificaciones.

## 6. Tres pedidos del usuario (2026-10-08)

- **Permisos por usuario** (Usuarios → «Permisos»). `usuario_permisos` y su
  evaluación existían; no había forma de escribirlas. Por acción: «Como su
  rol», «Conceder» o «Negar». `SaveUserPermissionsUseCase` revalida: permiso
  `CONFIGURACION.usuario.permisos`, nadie edita los suyos, sólo catálogo, sin
  escalamiento (salvo dueño/admin), administradores no llevan excepciones, al
  dueño no se le niega nada. Auditado; rige al siguiente inicio de sesión.
- **Probar un dispositivo** (Dispositivos → «Pruebas del dispositivo»).
  `DeviceTestResult` y su tabla no tenían escritor. «Probar conexión» no
  imprime (abre la conexión o consulta la cola de Windows y su estado);
  «Imprimir página de prueba» pide confirmación. Misma vía que tickets y
  cortes (`routed_printer`). **Hallazgo en la base real**: PRN-01 («TL2X
  Printer», USB) no indicaba la cola de Windows y todo USB iba a la
  predeterminada, que en esa computadora es «Microsoft Print to PDF». Ahora el
  perfil guarda la cola de Windows (elegida de las instaladas; acción «Elegir
  impresora de Windows») y la prueba falla explicando qué predeterminada se
  usaría. Las etiquetas tenían una copia propia de esa regla: unificada.
- **Media en la pantalla del cliente**. IMAGE/VIDEO sólo aceptaban texto
  escrito a mano y la pantalla mostraba un aviso. Ahora el archivo se adjunta
  (selector de archivo), se copia a la carpeta de media de la aplicación, se
  registra (`display_media`, migración 313; mismo archivo = un registro) y el
  contenido guarda su id. La pantalla muestra la imagen escalada a pantalla
  completa y reproduce el video en bucle y sin sonido (Qt Multimedia). HTML
  sigue sin motor.

## 7. Pendiente

- Módulo único de notificaciones (decisión del usuario, futuro).
- Editores en su módulo para los parámetros sin pantalla (sección 3).
- Hallazgos 7 y 8 — no elegidos en esta ronda.
- Preexistentes, no causados aquí: `test_sales_hardware.py::TestScanCodeRouter::test_auto_context_falls_back_to_customer_card_when_no_product_matches` (falta `loyalty_card_tokens` en el fixture desde LOY-29) y `tests/integration/shell/test_meat_processing_module_migration.py::test_the_remaining_routes_are_still_honest_placeholders` (cambios ajenos sin commitear en `meat_processing_view.py`).
