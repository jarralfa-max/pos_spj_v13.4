# INST-0 — Instalador Windows y actualizador seguro

Fecha: 2026-10-14/15 · Rama `claude/erp-financial-bounded-context-uqxz6b` sobre `968e0bc`
· Migraciones 338/339 · Fuente: `auditoria_instalador_actualizador_968e0bc.md` + prompt Opus 5.5.

## 1. Estado de partida (verificado leyendo código y una copia de la base real)

| Hallazgo de la auditoría | Verificación | Estado |
| --- | --- | --- |
| P0 sin binario/instalador | Sin `.spec`/`.iss`/job Windows; `start_all.bat` con `--reload`. | Cerrado (§3) |
| P0 dos rutas de datos | Escritorio: `<paquete>/data/spj_pos_database.db` (WAL, esquema 336). `AppPaths.sqlite_database_path()` → `%APPDATA%/…/db/spj.sqlite3`, archivo que nadie escribía; lo usaban `UpdateInstaller` y las dependencias de la API. | Cerrado: una sola resolución |
| P0 descarga sin verificación | `urlretrieve` directo al destino, sin hash ni firma. | Cerrado |
| P0 `install()` sólo planeaba; `copy2` sobre SQLite WAL | Confirmado; cero llamadores en producción. | Reemplazado |
| P1 semver | `13.4.0-rc1` → `(13,4,1)` > `13.4.0`. | Cerrado |
| P1 versión duplicada | `version.py` sin consumidores. | Eliminado |
| P1 módulos no seleccionables | Shell importa los 17 módulos estáticamente. | Fase 1: perfiles lógicos |
| P1 sin política de esquema ni rollback de datos | Confirmado. | Cerrado |

Hallazgos adicionales durante el trabajo:

* Secretos: en Windows van al Administrador de credenciales; el respaldo cifrado
  (`%APPDATA%/…/secrets/master.key`) está protegido con DPAPI y **requiere pywin32**. El
  `.venv` de desarrollo no tiene pywin32, así que esa clave no se puede leer hoy en esta
  máquina (falla preexistente, aparece en `tests/integration/shell` con el APPDATA real).
  El build de release fija `pywin32==311`.
* `media/pantalla_cliente` guarda nombres RELATIVOS: si la carpeta de datos cambia, deben
  copiarse. Las imágenes de producto guardan rutas absolutas y siguen funcionando donde están.
* `sales` reales: 58 `DRAFT` y 10 `ACTIVE` abandonadas; «venta en captura» = `ACTIVE` con líneas
  en las últimas 12 h, o una actualización nunca podría instalarse.
* El `.venv` no tiene `pyyaml` (falla de colección preexistente en `tests/architecture/test_ci_workflow.py`).

## 2. Decisiones (valores de desarrollo reversibles; producción explícita)

| Decisión | Valor | Cómo cambiarlo |
| --- | --- | --- |
| Datos por estación | `machine` (`%PROGRAMDATA%`) por defecto; `user` (`%LOCALAPPDATA%`, no roaming) | Página del instalador / `/DATASCOPE=` |
| Código fuente | Sin cambios: `<paquete>/data` y `<paquete>/logs` | — |
| Firma de manifiesto | Ed25519, claves EMBEDDED en `trusted_keys.py`, rotación con varias firmas | **Vacío hasta generar la clave de producción**: sin clave, toda actualización se rechaza con mensaje explícito |
| Authenticode | Exigido al instalador que se eleva cuando la compilación en curso está firmada | Certificado vía `SPJ_SIGNTOOL` / secretos CI; sin él `publishable=false` |
| Servidor de releases | `install_config.update_feed_url` (`…/{channel}/manifest.json`) + `allowed_update_hosts` | Parámetros del build; ejemplo `.invalid` |
| Canales | `stable`, `pilot`; despliegue por %, sucursal o estación | Manifiesto + Acerca de → Canal |
| Venta/cobro/corte en curso | Bloquean «Instalar ahora» y la ventana; outbox pendiente sólo avisa | `UpdateDeferralPolicy` |
| Instalación de rollback | Caché máquina `%PROGRAMDATA%\SPJ\Installers\SPJ ERP POS` + `installers.json` (SHA-256), escrita sólo por el instalador elevado | — |
| Python del release | 3.13 (el del proyecto, 3.13.12 local); la CI Linux sigue en 3.11 | `PYTHON_VERSION` del workflow |
| WhatsApp | Remoto por defecto; local = componente opcional, servicio `SPJWhatsApp`, `127.0.0.1:8000` | Instalador / `whatsapp.env` |
| Perfiles | Fase 1 lógica (mismo bundle); fase 2 física NO implementada | — |

## 3. Qué se construyó (archivos)

**Dominio** `backend/domain/software_distribution/`: `semantic_version.py`, `release_manifest.py`,
`eligibility.py`, `operations.py` (aplazamiento + ventana), `install_profile.py`, `update_job.py`.

**Aplicación** `backend/application/software_updates/`: `installation.py`, `use_cases.py`
(estado, buscar, descargar en 3 tiempos, offline, programar, ventana, cancelar, canal, ventana,
inventario de arranque), `startup_gate.py`, `update_transaction.py` (instalar / revertir / recuperar).

**Infraestructura**: `shared/app_paths.py` (layouts, una ruta de base), `shared/install_config.py`,
`shared/app_version.py` (fuente única + `build_info.json`), `db/sqlite_backup.py`,
`db/database_relocation.py`, `runtime/instance_lock.py`, `db/schema/software_updates_schema.py`,
`db/repositories/software_updates/station_update_repository.py`,
`updater/{update_manifest,trusted_keys,update_downloader,package_integrity,update_job_store,process_control,installer_trust,update_launcher,updater_main}.py`,
`desktop/software_updates_factory.py`, `bootstrap/self_test.py`,
`bootstrap/steps/schema_compatibility_step.py`.

**Eliminados**: `version.py`, `updater/update_installer.py`, `updater/version_checker.py`
(esqueletos reemplazados; un solo circuito de actualización).

**Arranque** `frontend/desktop/app.py`: `--self-test`, compuerta de actualización, candado de
instancia por archivo (reemplaza `QLocalServer`), reubicación, compatibilidad de esquema,
inventario de versión, traspaso ordenado al actualizador. `connection.py`,
`database.py` y `whatsapp_service/config/settings.py` usan `AppPaths`.

**Perfil de instalación**: `ApplicationContext.capabilities`; `PermissionEvaluator` niega familias
de módulos no instalados (también al admin); `SidebarResolver` los oculta; `DesktopRouter` los rechaza.

**UI**: Configuración → «Acerca de y actualizaciones» (`actualizaciones_page.py`,
`software_updates_presenter.py`); descarga en hilo sin tocar la base; disparador de ventana en
los servicios de fondo de la shell.

**Empaquetado/CI**: `installer/windows/{spj.spec,spj_updater.spec,spj_setup.iss,requirements-release.txt,README.md,examples/}`,
`scripts/release/*`, `whatsapp_service/service_host.py`, `.github/workflows/windows-release.yml`.

**Docs**: `docs/architecture/INSTALLER_AND_UPDATER.md`, `docs/runbooks/instalacion_actualizacion_sucursal.md`.

## 4. Mapa de compatibilidad de esquema y transición de la base

* Versión de esquema = mayor migración aplicada (`schema_migrations`); el binario conoce
  `MIGRATIONS` (hoy 339). Manifiesto: `requires_at_least` (la base debe estar al menos ahí)
  y `migrates_to` (no puede ser menor que el esquema actual → sin «downgrade» de esquema).
* Base con migraciones desconocidas ⇒ arranque detenido (`SchemaCompatibilityStep`).
* Binario anterior + base migrada sólo se reúnen tras restaurar el respaldo `pre-update-*`.
* Transición de la base legacy (sólo instalaciones): candidatos `<app>/data/…`,
  `legacy_database_paths` (página del instalador), `SPJ_LEGACY_DB_PATH`. Una sola base anterior
  sin base nueva ⇒ checkpoint WAL, renombrado (detecta archivo abierto), respaldo verificado,
  copia verificada (integridad, filas por tabla, esquema), reemplazo atómico, marcador
  `relocation.json`, original renombrado `.relocated-*` + LEEME. Dos bases o base reubicada
  desaparecida ⇒ arranque detenido con diagnóstico. Nunca se arranca sobre una base vacía si
  hay una anterior conocida.

## 5. Criterios de aceptación y evidencia

| Criterio | Evidencia | Estado |
| --- | --- | --- |
| Instala y ejecuta en PC limpia sin Python/Git | Job CI `windows-release.yml` (autoprueba con Python fuera del PATH). Local: ver §6. | Pendiente de ejecutar en CI |
| Upgrade conserva datos; ruta legacy una vez y recuperable | `test_backup_relocation_lock.py` (reubicación con WAL, conflicto, base desaparecida, archivo abierto en Windows, medios); `test_update_transaction.py`; marcador de datos en CI (reparación y desinstalación). | Probado en tests; CI pendiente |
| Manifiesto/paquete alterado, incompleto, otro canal/arquitectura/anterior se rechaza antes de ejecutar | `test_domain_policies.py`, `test_manifest_and_download.py`, `test_update_use_cases.py` | Probado |
| Interrupción/migración fallida no deja base corrupta; diagnóstico y recuperación real | `test_update_transaction.py` (instalador falla, migración falla → restauración, reversión falla → NEEDS_RECOVERY → recover, UAC rechazado, base bloqueada, paquete alterado, actualizador interrumpido) | Probado con instalador simulado |
| Perfiles sin ImportError; navegación y backend reflejan módulos; servicios opcionales no arrancan solos | `test_profiles_and_schema_gate.py`, `test_install_profile_catalog_matches_the_shell_modules`; WhatsApp sólo como servicio del instalador | Probado (lógico) |
| Versiones coinciden en UI, instalador, manifiesto y reportes | Fuente única `app_version.VERSION` → `build_info.json`, recurso de versión, `/DAppVersion`, manifiesto, autoprueba; guardrail `test_single_version_source` | Probado (UI/autoprueba); instalador por CI |

Pruebas nuevas: 66 unitarias + 63 de integración + 8 de arquitectura (ver §7 para la corrida completa).
Migraciones 338/339 sobre copia de la base real: 336 → 339, idempotentes.

## 5 bis. Build local real (2026-10-15, Windows 11, Python 3.13.12)

Entorno limpio (venv en carpeta temporal) con `requirements.txt` completo + PyQtWebEngine
5.15.7 + pywin32 311 + PyInstaller 6.22.3, congelado en `installer/windows/requirements-release.txt`.
`build_windows_release.py --skip-installer` (sin Inno Setup en esta máquina):

* `dist/SPJ/` 431 MB (`SPJ.exe`, `spj_whatsapp.exe`, `_internal`) y `spj_updater.exe` 11 MB;
  icono convertido del SVG oficial; `build_info.json` con commit 968e0bc.
* **Defecto encontrado y corregido**: el primer build salió SIN migraciones ni módulos de
  `backend` cargados por nombre (`collect_submodules` devolvía 0 porque el proceso auxiliar no
  tenía la raíz del paquete en `sys.path`). Lo detectó `SPJ.exe --self-test`
  («Cannot import required migration 000»). Arreglado en `spj.spec`, que ahora además ABORTA el
  build si faltan módulos dinámicos (2 395 de `backend`, 340 de `migrations`).
* `SPJ.exe --self-test` congelado, **sin Python en el PATH**: base nueva → esquema 339 en 19 s.
* Disposición instalada simulada (`install_config.json` junto al exe, datos en carpeta temporal,
  base legacy = copia de la base real): 1.ª ejecución `RELOCATED` (742 tablas, esquema 336 → 339,
  respaldo verificado, original renombrado `.relocated-*` + LEEME, archivo de medios copiado);
  2.ª ejecución `IN_PLACE`. Defecto menor corregido: el respaldo heredaba la extensión
  `.relocating`; ahora lleva el nombre real `spj_pos_database-pre-relocation-*.db`.
* `spj_updater.exe` congelado, sin Python: trabajo con instalador inexistente →
  `WAITING_FOR_APP_EXIT → CANCELLED`, diario y `updater.log` escritos, sin respaldo ni instalación.
* `spj_whatsapp.exe run` congelado: responde en 1 s, escucha SÓLO en `127.0.0.1`, lee la base
  reubicada de la instalación.

## 6. Lo que NO se ejecutó (y por qué)

* **No se compiló ni probó el instalador Inno Setup** (ISCC no está en esta máquina): ni la
  instalación en `Program Files`, ni accesos directos, UAC, reparación, desinstalación ni el
  servicio Windows de WhatsApp. El job `windows-release.yml` lo hace (instalación silenciosa,
  autoprueba sin Python, reparación y desinstalación con marcador de datos) — no se ha corrido.
* El actualizador congelado no se probó instalando de verdad (requiere UAC interactivo e
  instalador compilado); la transacción completa está cubierta con instalador simulado.
* Sin clave de firma de producción embebida: hoy toda actualización se rechaza (a propósito).
* Sin Authenticode: todo build es de desarrollo, `publishable=false`.
* Prueba manual de hardware (impresora, báscula, cajón) y POS en Windows tras instalar: pendiente,
  checklist en el runbook.
* Actualización real desde una versión publicada anterior: el job la hace sólo cuando exista
  un release previo publicado.
* Fase 2 (paquetes físicos por módulo): no implementada; no se promete ahorro de espacio.

## 7. Corridas

* Nuevas (`tests/unit/software_distribution`, `tests/integration/software_distribution`,
  `tests/architecture/test_installer_updater_guardrails.py`): **138 passed** con el entorno
  de release completo (`requirements-release.txt`).
* Regresión bootstrap + shell + Configuración (1 018 pruebas). Ajustadas por cambio legítimo:
  conteo de pasos del arranque (4→5, 2→3, 6→7), `test_phase2_infrastructure.py` y
  `test_app_paths_resources.py` (API retirada `sqlite_database_path`/`UpdateInstaller`),
  prueba del gerente (ahora también corre la 339), y nuevo handler `_page_actualizaciones` en
  `ConfiguracionWorkspaceQueryService` (toda ruta del menú se puede leer por la vía genérica).
  `ensure_directories()` ya no crea carpetas fuera de la raíz de datos.
* `tests/architecture` completo, comparado con un worktree limpio de `HEAD`: base 118 fallas /
  829 OK; árbol actual 123 / 834. Las 5 nuevas que eran de este trabajo se corrigieron (PK
  `TEXT NOT NULL` en las tablas 338; `PRAGMA` del arranque movido a `checkpoint_wal()` de
  infraestructura; `sqlite_backup.py`/`database_relocation.py` en la lista justificada de
  conexiones crudas). Las otras 2 nuevas están en `test_whatsapp_runtime_imports.py`, archivo que
  no existe en `HEAD` (trabajo sin commitear de otra sesión: `core.*` en `whatsapp_service` y
  `dotenv` ausente del `.venv`).
* Fallas que existen igual en `HEAD` 968e0bc (worktree limpio), no de este trabajo:
  `test_meat_processing_module_migration::…honest_placeholders`,
  `test_products_module_migration::…real_products_view`, los 2 errores de
  `test_main_startup_gates`.
* Fallas de entorno: `test_whatsapp_credentials_regression.py` (archivo sin commitear de otra
  sesión) no encuentra `whatsapp_service` en `sys.path`; con la raíz del repo en `PYTHONPATH`
  pasa 5/5. `test_ci_workflow.py` necesita `pyyaml`; shell con el APPDATA real necesita pywin32.
