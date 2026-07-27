# Runbook — Reset limpio de la base de desarrollo

> Plan B — Desarrollo limpio sin migraciones legacy.
> Contrato: `docs/skills/SPJ_REFACTOR_SKILL.md` → sección
> **REGLA DE DESARROLLO — SIN CONSERVACIÓN DE DATOS LEGACY**.

SPJ ERP/POS está en fase de desarrollo activo. **No se conservan datos.** Si la
base local queda en estado híbrido, contaminado o parcialmente migrado, no se
repara: se respalda (opcional) y se elimina para que el código cree una base
nueva, born-UUIDv7, desde cero.

## No usar la migración 200 en desarrollo

La migración `200_uuid_identity_cutover` es una herramienta de **rescate** para
escenarios excepcionales donde haya que conservar datos. **No** es el flujo
normal de arranque y no debe ejecutarse para obtener una DB limpia: una base
nueva debe nacer ya en UUIDv7.

## Procedimiento

### Windows (PowerShell)

```powershell
cd "C:\Users\Diego Rodriguez\Downloads\pos_spj_v13.4\pos_spj_v13.4"

# Respaldo opcional (descartable)
Copy-Item ".\data\spj_pos_database.db" ".\data\spj_pos_database_backup_dev_reset.db" -ErrorAction SilentlyContinue

# Eliminar la base contaminada
Remove-Item ".\data\spj_pos_database.db" -ErrorAction SilentlyContinue

# Arrancar: el bootstrap crea una base limpia
python main.py
```

### Linux / macOS (bash)

```bash
cd pos_spj_v13.4

cp ./data/spj_pos_database.db ./data/spj_pos_database_backup_dev_reset.db 2>/dev/null || true
rm -f ./data/spj_pos_database.db

python main.py
```

## Criterio de éxito

- El arranque crea la DB sin ejecutar la migración 200.
- El guard de arranque `assert_uuid_identity` (en `main.py`) no rechaza el inicio.
- `PRAGMA foreign_key_check` devuelve vacío.

## Si algo falla por código/schema viejo

No escribir una migración de rescate ni un parche temporal. Atacar la causa raíz:

1. corregir el schema fuente (`migrations/m000_base_schema.py` y `migrations/`),
2. corregir repositorios/servicios para mintar UUIDv7 (`backend/shared/ids.py::new_uuid()`),
3. eliminar el código muerto o legacy,
4. resetear la DB de desarrollo y reintentar.

## Estado actual (Plan B COMPLETADO — cero deuda)

El schema activo es 100% born-clean UUIDv7: una BD nueva creada por el bootstrap
normal (`m000_base_schema.up` + `migrations.engine.up`) produce
`find_integer_pks(conn) == {}`. Los antiguos techos de deuda
(`INTEGER_PK_TABLE_CEILING`, `SERVICES_WITH_DDL_CEILING`,
`LASTROWID_FILE_CEILING`) fueron reemplazados por **cero tolerancia** en
`tests/architecture/test_clean_birth_guardrails.py`:

- cero tablas con PK entera (base sola y cadena completa);
- cero `AUTOINCREMENT` en el schema activo;
- cero FK funcionales `INTEGER` y cero `DEFAULT 1` en FKs;
- cero `lastrowid` como identidad y cero `int(..._id)` en código de dominio;
- cero DDL fuera de `migrations/` (allowlist mínima documentada).

`uuid_cutover` (migración 200) queda como **herramienta excepcional de
conservación de datos en producción**; nunca es el flujo de desarrollo.
```
