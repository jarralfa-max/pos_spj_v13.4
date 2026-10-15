# Empaquetado Windows de SPJ ERP POS

| Archivo | Qué es |
| --- | --- |
| `spj.spec` | PyInstaller one-folder: `SPJ.exe` (escritorio) + `spj_whatsapp.exe` (servicio WhatsApp local opcional), un solo `_internal`. |
| `spj_updater.spec` | PyInstaller single-file: `spj_updater.exe`, el actualizador externo (sin Qt ni ERP). |
| `spj_setup.iss` | Inno Setup 6: AppId fijo, perfiles, ubicación de datos, base anterior, caché de reversión, servicio WhatsApp, desinstalación que conserva datos. |
| `requirements-release.txt` | Entorno de build FIJADO (versiones exactas, incluido PyInstaller). |
| `examples/manifest.example.json` | Forma del manifiesto firmado (sin firma válida, sin secretos). |

## Construir (en Windows)

```powershell
py -3.13 -m venv .buildvenv
.buildvenv\Scripts\python -m pip install -r pos_spj_v13.4\installer\windows\requirements-release.txt
# Inno Setup 6 (ISCC.exe) instalado: choco install innosetup
.buildvenv\Scripts\python pos_spj_v13.4\scripts\release\build_windows_release.py `
    --channel stable --build-number 1 `
    --artifact-base-url https://updates.example.com/spj/stable `
    --feed-url "https://updates.example.com/spj/{channel}/manifest.json"
```

Resultado en `build\windows\release\`: `SPJ-Setup-<ver>-x64.exe`, `.sha256`,
`manifest.payload.json` (sin firmar) y `release.json` (`publishable`).

## Firmar y publicar (sólo el responsable de releases)

1. Clave del manifiesto (una vez): `scripts\release\generate_signing_key.py --key-id spj-release-2026a --out <fuera del repo>`,
   pegar la línea `TrustedKey(...)` en `backend\infrastructure\updater\trusted_keys.py` y publicar
   una versión con ella. Sin clave embebida, las estaciones rechazan toda actualización.
2. Authenticode: `--sign` con `SPJ_SIGNTOOL` (comando `signtool sign ...` con su certificado).
   Sin certificado la compilación es de desarrollo y `release.json` dice `"publishable": false`.
3. `scripts\release\sign_manifest.py --payload ...manifest.payload.json --key-id ... --key-file ... --out ...manifest.json`
4. `scripts\release\verify_release.py build\windows\release --production`
5. Paquete offline: `scripts\release\make_offline_package.py build\windows\release E:\SPJ-<ver>`
6. Subir instalador + `manifest.json` al servidor de actualizaciones (`<base>/<canal>/`).

En CI (`.github/workflows/windows-release.yml`) la publicación crea sólo un release
BORRADOR, con etiqueta `v*`, entorno protegido `production` y ambas firmas.
