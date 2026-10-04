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

## 3. Pendiente

- Hallazgo 6 — siguiente bloque (decisión del usuario).
- Hallazgos 7 y 8 — no elegidos en esta ronda.
- Preexistentes, no causados aquí: `test_sales_hardware.py::TestScanCodeRouter::test_auto_context_falls_back_to_customer_card_when_no_product_matches` (falta `loyalty_card_tokens` en el fixture desde LOY-29) y `tests/integration/shell/test_meat_processing_module_migration.py::test_the_remaining_routes_are_still_honest_placeholders` (cambios ajenos sin commitear en `meat_processing_view.py`).
