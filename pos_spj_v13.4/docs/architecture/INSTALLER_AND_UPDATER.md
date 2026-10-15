# Installer and Updater

Contract of the Windows distribution of SPJ ERP/POS (2026-10-14). Decisions
and evidence: [`docs/refactor/INST-0_instalador_actualizador.md`](../refactor/INST-0_instalador_actualizador.md).
Branch procedure: [`docs/runbooks/instalacion_actualizacion_sucursal.md`](../runbooks/instalacion_actualizacion_sucursal.md).

## Pieces and who owns what

| Piece | Where | Owns |
| --- | --- | --- |
| Version | `backend/shared/app_version.py` | `VERSION` (semver) — the ONLY hand-edited version. Build metadata comes from `build_info.json` written by the build script. |
| Paths | `backend/shared/app_paths.py` + `install_config.py` | The one resolution of data root, database, logs, backups, updater folders. |
| Legacy relocation | `backend/infrastructure/db/database_relocation.py` | Moving a pre-installer database ONCE, verified. |
| Backups | `backend/infrastructure/db/sqlite_backup.py` | SQLite Online Backup API + verification + sidecar. |
| Instance lock | `backend/infrastructure/runtime/instance_lock.py` | "Who has this database open" (desktop, updater, relocation). |
| Domain | `backend/domain/software_distribution/` | SemVer, release manifest, eligibility/rollout, deferral, maintenance window, install profiles, update job state machine. |
| Use cases | `backend/application/software_updates/` | Status, check, download, offline import, schedule, channel/window, startup ingestion, startup gate, install transaction. |
| Updater infra | `backend/infrastructure/updater/` | Signed manifests + embedded keys, HTTPS downloader, job journal, process control, Authenticode/cached-installer trust, launcher, `updater_main`. |
| UI | `frontend/desktop/modules/configuracion/pages/actualizaciones_page.py` | «Acerca de y actualizaciones». |
| Packaging | `installer/windows/` | `spj.spec`, `spj_updater.spec`, `spj_setup.iss`, pinned requirements. |
| Release tooling | `scripts/release/` | Build, sign manifest, generate key, verify, offline package. |
| CI | `.github/workflows/windows-release.yml` (repo root) | Windows build, install tests, artifacts, gated publication. |

## Paths

* **Source checkout** (no `install_config.json`, not frozen): database
  `<package>/data/spj_pos_database.db`, logs `<package>/logs`, other user data
  `%APPDATA%/SPJ/SPJ ERP POS` — unchanged, so the development reset runbooks keep working.
* **Installed**: binaries in `C:\Program Files\SPJ\SPJ ERP POS` (read-only);
  data root chosen in the installer and written to `install_config.json`:
  * `machine` (default for tills): `%PROGRAMDATA%\SPJ\SPJ ERP POS` — Users get modify rights;
  * `user`: `%LOCALAPPDATA%\SPJ\SPJ ERP POS` (never roaming).
  Database `<data>/db/spj_pos_database.db`; also `backups/`, `logs/`, `imagenes_productos/`,
  `media/`, `whatsapp/`, `updater/` (downloads, manifests, `update_job.json`).
* **Rollback installers**: `%PROGRAMDATA%\SPJ\Installers\SPJ ERP POS` — outside the data root,
  written only by the elevated installer, indexed by `installers.json` (SHA-256).
* Overrides for tests/CI/support only: `SPJ_APP_DATA_DIR`, `SPJ_DB_PATH`, `SPJ_LEGACY_DB_PATH`.

Every consumer (desktop, connection pool, API settings, updater, local WhatsApp
service) asks `AppPaths`; `tests/architecture/test_installer_updater_guardrails.py`
fails if any other code names the database file.

## Start sequence (desktop)

`--self-test` → QApplication → update gate (updater alive? recovery needed?) →
instance lock → legacy relocation → integrity → **schema compatibility** (a
database migrated by a newer release stops the start) → migrations → schema/UUID
validation → installation state → station version inventory + last update outcome →
login → window.

## Update flow

1. **Check** (`actualizacion.ver`): fetch `{feed}/{channel}/manifest.json` over HTTPS
   from an allowed host; verify the Ed25519 signature against the keys EMBEDDED in
   `trusted_keys.py`; only then parse; evaluate product, channel, platform,
   no-downgrade (semver with pre-release), minimum installed version, schema range,
   host allow-list and staged rollout (percent bucket per station / branch / station lists).
2. **Download** (`actualizacion.administrar`): HTTPS, allow-listed host on every redirect,
   timeout, hard size cap, streamed SHA-256, `.part` → atomic rename. Offline media: signed
   `manifest.json` + installer, same checks (no host/rollout).
3. **Schedule**: «Instalar ahora» refuses while a sale is in capture (ACTIVE with lines in the
   last 12 h), a payment is pending or a cash cut is in progress; or «Instalar en la ventana»
   (`HH:MM-HH:MM`, may cross midnight) — a background tick launches it only inside the window
   and only when nothing is in progress. Mandatory releases inform a deadline; nothing ever
   interrupts an operation.
4. **Hand-over**: the desktop stops background services, checkpoints the WAL, closes
   connections, releases the lock, starts a temporary copy of `spj_updater.exe` and quits.
5. **Transaction** (external process, `update_transaction.py`): wait for exit → lock →
   re-verify package (+ Authenticode when the build is signed) → verified backup
   `pre-update-<version>` → installer elevated through UAC (`/SILENT`) → `SPJ.exe --self-test`
   (migrations run here) must report the announced version → COMPLETED. Failure after the
   installer: restore the database (if migrations may have run) + reinstall the cached previous
   installer + self-test → ROLLED_BACK; if that fails → NEEDS_RECOVERY.
6. **Journal**: `update_job.json` is written at every transition; the desktop records the
   outcome in `software_update_events` on its next start (exactly once) and archives it.
   An interrupted updater is diagnosed at start (`UpdateStartupGate`); NEEDS_RECOVERY blocks
   normal start and offers «Recuperar» (restore + previous version, via the updater).

## Install profiles (phase 1)

One complete bundle for everyone. The installer's *POS esencial / ERP completo /
Personalizado* selects capabilities (`install_profile.py`), written to `install_config.json`.
Three separate layers are evaluated: install profile (station) → feature flags `modulo.<id>`
(branch) → permissions (user). A capability not installed is hidden from the menu, refused by
the router and its permission families are denied even to administrators
(`PermissionEvaluator`). Core (POS, Caja, Productos, Inventario, Precios, Clientes,
Configuración) cannot be removed; dependencies are closed automatically (RR. HH./Activos →
Finanzas). No disk space is saved per module in phase 1. Phase 2 (physical per-module
packages) requires conditional imports, per-module metadata/migrations/signatures and a
compatibility matrix — not implemented.

## WhatsApp

The desktop never starts WhatsApp. Production profile: remote service. Optional local
service = installer component (machine data scope only), Windows service `SPJWhatsApp`
(`spj_whatsapp.exe`, pywin32), bound to `127.0.0.1:8000` by default, configuration and
conversations in `<data>/whatsapp/`. `start_all.bat`/`start_all.sh` remain development tools only.

## Security rules (enforced by tests)

No `os.system`/`shell=True`/`urlretrieve` in the updater; no byte copy of SQLite files; the
SHA-256 of an unauthenticated manifest is never trusted; trusted keys are code, not files;
the external updater loads neither Qt nor the ERP; nothing downloaded runs inside the POS
process; the only elevated program is the (signed) installer.

## Read-only bundled resources

`AppPaths.resource_root` is `sys._MEIPASS` in a bundle (`_internal` for one-folder builds).
`spj.spec` bundles `assets/` (official JUANIS artwork, unchanged), `build_info.json` and the
non-Python resources of `frontend`, `backend` and `migrations`. The `.exe`/installer icon is
rendered at build time from `assets/branding/app_icon.svg` (format conversion only; the
asset folder keeps only originals).
