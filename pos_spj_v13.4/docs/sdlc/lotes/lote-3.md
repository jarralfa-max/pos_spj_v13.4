# Lote 3 — Instalador y actualizador

Rama `fix/lote-3`, base `claude/erp-financial-bounded-context-uqxz6b`. Corrección directa, sin spec ni plan. Falta la revisión independiente que piden los intents T0.

## Estado por ítem

| Ítem | Estado | Commit | Prueba que lo cubre |
| --- | --- | --- | --- |
| SDLC-ARQ-INST-001 | LISTO | `863e8b26` | `tests/integration/bootstrap/test_pre_migration_backup.py` |
| SDLC-INST-001 | LISTO | `68ba984d` | `tests/integration/software_distribution/test_release_authority.py` |
| SDLC-ARQ-INST-002 | LISTO | `df164946`, `f31cf7bd` | `tests/integration/software_distribution/test_update_preserves_station.py` |
| SDLC-INST-002 | BLOQUEADO | — | — |
| SDLC-INST-003 | LISTO, con riesgo residual | `3b01f72a` | `tests/integration/software_distribution/test_data_folder_acl.py` |
| SDLC-ARQ-INST-003 | LISTO | `a971e345` | `tests/unit/security/test_secret_store_protection_scope.py` |

## Qué se cambió

### SDLC-ARQ-INST-001: respaldo antes de migrar

- Se reprodujo: una migración destructiva fallida dejaba sólo `spj.db`, sin respaldo.
- Nuevo paso `PreMigrationBackupStep`, antes de `DatabaseMigrationStep`. Con datos y migraciones pendientes toma un respaldo verificado `pre-migration-<versión>` con `SQLiteBackupService`.
- Si el respaldo falla, el arranque se detiene sin migrar y lo explica.
- Si una migración falla, el mensaje indica la ruta del respaldo. La restauración sigue siendo manual (runbook §6).
- Sin pendientes (por ejemplo «Reparar») o con base nueva no respalda.
- Costo aceptado: la autoprueba de una actualización toma una copia más, además de `pre-update`. Ni estos respaldos ni los `pre-update` tienen retención.

### SDLC-INST-001: qué instalador puede correr elevado

- El hash del instalador sale del manifiesto firmado, que viaja en el job y se verifica en el actualizador. Ya no sale del propio job.
- Se rechaza un manifiesto de otra versión o uno que no sea más nuevo que la instalada.
- El instalador se copia a una carpeta privada y se ejecuta esa copia.
- `update_job.json` no se movió de carpeta: ya no se confía en él.
- Authenticode exige exactamente el sujeto que firma el `SPJ.exe` instalado. La comparación por subcadena aceptaba «CN=SPJ Falso» si el esperado era «CN=SPJ».
- Las reglas de firma salen del `build_info.json` instalado, no de la línea de comandos.
- Un build sin firma en instalación de máquina se rechaza, salvo `--dev-unsigned` explícito, que se ignora en un build firmado.
- `recover` ya no ejecuta la ruta escrita en el job: sólo lo que lista la caché de instaladores.
- `spj_updater.spec` deja de excluir `cryptography`, y la guardia `test_external_updater_does_not_load_qt_or_the_erp` se ajustó a eso.
- La pregunta del certificado sigue sin respuesta, y este arreglo no la necesita porque compara contra el firmante del `SPJ.exe` instalado.

### SDLC-ARQ-INST-002: configuración e identidad

- Cada actualización guarda `station-config-pre-update-<versión>/` con `install_config.json`, `station_settings.json` y hashes. Se restaura en reversión y recuperación.
- No copia secretos.
- En instalación de máquina, `install_config.json` no se restaura desde esa carpeta: define los hosts de actualización y la carpeta la modifica cualquier usuario. Lo reescribe el instalador elevado.
- Si la configuración no se puede restaurar, se informa en el resultado y no bloquea la estación.
- La desinstalación conserva `install_config.json` y `InstalledVersion`. Sólo los borra con `/PURGECONFIG` o respondiendo «Sí» (por omisión, «No»).
- El canal sobrevive a reparar y reinstalar. Una reinstalación silenciosa que no elige nada conserva el perfil.
- `ci_data_marker.py` ahora cubre cola, identidad, ancla y permisos en sus tablas reales. Lo usan CI y la prueba T12.

### SDLC-INST-003: permisos de la carpeta de datos

- Respuesta del responsable: varios usuarios de Windows por PC.
- `Users` conserva Modificar en las 10 carpetas de trabajo y pasa a lectura en la raíz, también en actualizaciones (con `icacls`, primero las carpetas).
- Si falla una carpeta, la raíz no se toca.
- Una prueba exige que toda carpeta nueva bajo la raíz se agregue al instalador.

### SDLC-ARQ-INST-003: secretos

- En Windows sin DPAPI el almacén falla cerrado. Una llave en claro heredada se protege al primer uso.
- La instalación de máquina usa el almacén local con `CRYPTPROTECT_LOCAL_MACHINE`, porque Credential Manager es un cofre por usuario.
- El cofre de cada usuario se copia una vez, sin sobrescribir ni vaciarlo, y así queda disponible para volver atrás.
- Una llave de otro usuario se reemplaza sólo si no cifra nada. Si hay secretos, falla cerrado y la conserva.
- La instalación por usuario sigue con Credential Manager.

## Bloqueo

**SDLC-INST-002:** el problema sigue: `EMBEDDED_RELEASE_KEYS` está vacío en `backend/infrastructure/updater/trusted_keys.py:30`. El intent está aprobado, pero su pregunta no tiene respuesta:

> ¿Dónde se genera y custodia la llave privada de release? (el humano la crea; Claude no la ve)

Sin esa llave no hay llave pública que embeber ni build real que probar. Las herramientas ya existen (`scripts/release/generate_signing_key.py`, `sign_manifest.py`, `verify_release.py --production`). Falta decidir también si la llave pública vive en el repositorio o sólo en el build de release.

## Riesgos y decisiones para el responsable

1. **Sin certificado no hay autoactualización en máquina.** Es el objetivo aprobado de SDLC-INST-001, pero con presupuesto $0 cada estación de máquina se actualizaría sólo con Setup manual. Con la llave de INST-002 y sin certificado, el actualizador cerraría SPJ, cancelaría y explicaría la causa al reabrir.
2. **SDLC-INST-003 no impide editar la base.** SQLite necesita escritura, así que cualquier usuario de Windows de la estación aún puede cambiar `usuarios` o `rol_permisos` con una herramienta externa. Cerrarlo exige un servicio local dueño de la base o un sello verificable. Conviene abrir un ítem nuevo.
3. **La llave de máquina no protege contra usuarios locales.** Protege contra copiar `secrets` a otra PC. Es la consecuencia de compartir secretos entre varios usuarios.
4. **Reinstalar en pantalla tras desinstalar** muestra el perfil por omisión, y lo que elija la persona reemplaza al conservado.
5. **Si se configura un certificado en CI,** el paso «Real update» debe preparar un manifiesto firmado: `--dev-unsigned` no aplica a un build firmado y la actualización forzada a 99.0.0 no tendría manifiesto válido.

## Migraciones

Ninguna. No se usaron los números 362–364. La nota del paso de respaldo está en `migrations/MIGRATION_LOG.md`.

## Resultados de las pruebas finales

| Corrida | Resultado |
| --- | --- |
| `python -m compileall -q .` | Sin errores |
| Unit e integración del área (`tests/integration/bootstrap`, `tests/integration/software_distribution`, `tests/unit/bootstrap`, `tests/unit/software_distribution`, `tests/unit/security`, `tests/unit/test_app_paths_resources.py`, `tests/unit/test_phase2_infrastructure.py`) | 650 pasaron, en `a971e345` |
| `tests/architecture` completo | 22 fallaron, 879 pasaron, 1 omitida, 2 xfail, en 1 h 40 min, en `a971e345` |
| Tras corregir el marcador: `test_update_preserves_station.py`, `test_installer_updater_guardrails.py` y `test_no_schema_changes_outside_migrations.py` | 27 pasaron, 1 falló (`test_no_schema_changes…`, preexistente) |
| Compilación de `spj_setup.iss` con ISCC, paquete de juguete, sin ejecutar | Sin errores, en `3b01f72a`; el `.iss` no cambió después |

`tests/architecture` no se repitió completo después de `a971e345`. El único cambio posterior es `scripts/release/ci_data_marker.py`, cubierto por la tercera fila.

### Corrección que dejó la corrida de arquitectura

Las 22 fallas coinciden en nombre con las de `docs/sdlc/baseline/2026-10-28.md`. Aun así, el lote había agregado una infracción dentro de una de ellas: `test_no_schema_changes_outside_migrations` contaba 2 `CREATE TABLE` en `ci_data_marker.py`. Se quitó la tabla `ci_marker_values`; los valores viven en `ci_marker`. Queda 1, la que ya existía antes del lote.

### Fallos preexistentes

- `tests/architecture`: las 22 de la línea base, agrupadas ahí en SDLC-CORE-008, SDLC-CORE-009 y SDLC-WA-005.
- `tests/integration/integrations/test_mercadopago_credential_resolver.py`: 3 fallas por `ModuleNotFoundError: services`, código ya borrado.

## No verificado

- El instalador no se ejecutó, por regla del encargo. Quedan sin probar en Windows real: desinstalar, `/PURGECONFIG`, `icacls` en `ProgramData` y el uso con un usuario de Windows sin privilegios. La semántica de `icacls` sí se probó sobre un árbol temporal.
- Los pasos nuevos de `windows-release.yml` no se han corrido.
- `spj_updater.exe` no se construyó con `cryptography` porque PyInstaller no está instalado aquí. Si el empaquetado falla, el actualizador no arrancaría: verificar en el primer build de CI.
- Authenticode y DPAPI se probaron con dobles, no con un certificado ni varios usuarios reales.
