from __future__ import annotations

import json
import re
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parent
BASE_PATH = PACKAGE_ROOT / "docs" / "refactor"
MODULES_PATH = BASE_PATH / "modules"

ALLOWED_MODULE_STATES = (
    "PENDING",
    "AUDIT",
    "PROTECTION",
    "IMPLEMENTATION",
    "LEGACY_REMOVAL",
    "INTEGRATION",
    "VALIDATION",
    "BLOCKED",
    "DONE",
)

MODULE_QUEUE: tuple[tuple[str, str], ...] = (
    ("CONFIGURACION", "Configuración"),
    ("MERMA", "Merma"),
    ("PRODUCTOS", "Productos"),
    ("INVENTARIO", "Inventario"),
    ("VENTAS", "Ventas"),
    ("PROCESAMIENTO_CARNICO", "Procesamiento cárnico"),
    ("RECETAS", "Recetas"),
    ("PRODUCCION", "Producción"),
    ("TRANSFERENCIAS", "Transferencias"),
    ("DELIVERY", "Delivery"),
    ("CAJA", "Caja"),
    ("BI_DASHBOARD", "BI / Dashboard"),
    ("PLANEACION_COMPRAS", "Planeación de compras"),
    ("COTIZACIONES", "Cotizaciones"),
    ("FIDELIDAD", "Fidelidad"),
    ("TARJETAS_FIDELIDAD", "Tarjetas de fidelidad"),
    ("ACTIVOS", "Activos"),
    ("CLIENTES", "Clientes"),
    ("PROVEEDORES", "Proveedores"),
    ("COMPRAS", "Compras"),
    ("RECEPCION", "Recepción"),
    ("PEDIDOS", "Pedidos"),
    ("TICKETS", "Tickets"),
    ("ETIQUETAS", "Etiquetas"),
    ("HARDWARE", "Hardware"),
    ("NOTIFICACIONES", "Notificaciones"),
    ("WHATSAPP", "WhatsApp"),
    ("FINANZAS", "Finanzas"),
    ("RRHH", "Recursos humanos"),
    ("REPORTES", "Reportes"),
    ("API", "API FastAPI"),
    ("SINCRONIZACION", "Sincronización"),
    ("INSTALADOR", "Instalador"),
    ("ACTUALIZADOR", "Actualizador"),
    ("CIERRE_GLOBAL", "Cierre global"),
)

def _module_report_for(code: str) -> str:
    return f"docs/refactor/modules/{code.lower()}.md"



def _module_name_for(code: str) -> str:
    return dict(MODULE_QUEUE).get(code, code)


def _current_module_markdown(code: str, status: str = "PENDING", iteration: int = 0) -> str:
    if code == "UUIDV7_CUTOVER":
        return INITIAL_FILES["CURRENT_MODULE.md"]
    return f"""# Módulo actual

## Código

```text
{code}
```

## Nombre

{_module_name_for(code)}.

## Estado

```text
{status}
```

## Iteración

```text
{iteration}
```

## Objetivo

Pendiente de definición detallada en el reporte acumulativo del módulo.

## Hallazgos abiertos

Pendientes de auditoría del módulo.

## Tests requeridos

Pendientes de auditoría del módulo.

## Bloqueos

Ninguno registrado.

## Próxima acción

Ejecutar auditoría del módulo actual según el flujo maestro.
"""

def _initial_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "skill_version": "uuidv7-strict",
        "global_status": "IN_PROGRESS",
        "current_module": "CONFIGURACION",
        "global_iteration": 0,
        "last_completed_module": None,
        "modules": {
            code: {
                "status": "PENDING",
                "iteration": 0,
                "score": 0,
                "open_violations": None,
                "tests_failed": None,
                "report": _module_report_for(code),
            }
            for code, _name in MODULE_QUEUE
        },
    }


def _module_queue_markdown() -> str:
    states = "\n".join(ALLOWED_MODULE_STATES)
    rows = "\n".join(
        f"| {index:5d} | {code:<21} | {name:<24} | PENDING |"
        for index, (code, name) in enumerate(MODULE_QUEUE)
    )
    return f"""# Cola maestra de módulos

## Estados permitidos

```text
{states}
```

## Cola

| Orden | Código                | Módulo                   | Estado  |
| ----: | --------------------- | ------------------------ | ------- |
{rows}

## Regla

Codex selecciona siempre el primer módulo que no esté en `DONE`, salvo que una dependencia documentada obligue a reordenar temporalmente la cola.
"""

INITIAL_FILES: dict[str, str] = {
    "MASTER_REFACTOR_STATE.md": """# Estado maestro del refactor SPJ

## Estado global

```text
IN_PROGRESS
```

## Regla de cierre

El proyecto solo puede pasar a `DONE` cuando:

* todos los módulos estén en `DONE`;
* no existan violaciones abiertas;
* todos los tests pasen;
* UUIDv7 sea la única identidad;
* no exista código legacy funcional;
* no existan rutas duplicadas;
* la validación global esté completa.

## Módulo actual

```text
UUIDV7_CUTOVER
```

## Última actualización

Pendiente de primera ejecución.

## Resumen

| Módulo         | Estado  | Iteración | Violaciones | Tests fallidos |
| -------------- | ------- | --------: | ----------: | -------------: |
| UUIDV7_CUTOVER | PENDING |         0 |   Pendiente |      Pendiente |

## Historial

El historial debe agregarse de forma acumulativa. No borrar entradas anteriores.
""",
    "MODULE_QUEUE.md": _module_queue_markdown(),
    "CURRENT_MODULE.md": """# Módulo actual

## Código

```text
UUIDV7_CUTOVER
```

## Nombre

Corte global de identidad UUIDv7.

## Estado

```text
PENDING
```

## Iteración

```text
0
```

## Objetivo

Eliminar por completo:

* IDs enteros funcionales;
* PK y FK enteras;
* `AUTOINCREMENT`;
* `lastrowid`;
* casts `int(..._id)`;
* `legacy_id`;
* escritura dual;
* lectura dual;
* fallback de identidad;
* tablas paralelas.

## Hallazgos abiertos

Pendientes de auditoría inicial.

## Tests requeridos

Pendientes de auditoría inicial.

## Bloqueos

Ninguno registrado.

## Próxima acción

Ejecutar auditoría completa del esquema y contratos de identidad.
""",
    "GLOBAL_VIOLATIONS.md": """# Violaciones globales del refactor

## Estado

Pendiente de primera auditoría global.

## Categorías obligatorias

### Identidad UUIDv7

- Pendiente.

### SQL en UI

- Pendiente.

### Commit o rollback en UI

- Pendiente.

### Schema fuera de migrations

- Pendiente.

### Rutas duplicadas

- Pendiente.

### Fuentes duplicadas de verdad

- Pendiente.

### Defaults numéricos hardcodeados

- Pendiente.

### Estilos hardcodeados

- Pendiente.

### Excepciones silenciosas

- Pendiente.

### Código legacy

- Pendiente.

### Tests

- Pendiente.

## Formato de hallazgo

Cada hallazgo debe registrar:

```text
ID:
Severidad:
Categoría:
Módulo:
Archivo:
Línea:
Descripción:
Causa raíz:
Test de protección:
Estado:
Iteración detectada:
Iteración corregida:
```

## Regla

No borrar hallazgos corregidos.

Cambiar su estado a `RESOLVED` para conservar trazabilidad.
""",
    "UUIDV7_CUTOVER_REPORT.md": """# Reporte de corte global UUIDv7

## Estado

```text
PENDING
```

## Alcance

* Tablas.
* PK.
* FK.
* Commands.
* DTO.
* Use Cases.
* Application Services.
* Query Services.
* Repositories.
* Eventos.
* Outbox.
* API.
* PyQt.
* Tests.
* Fixtures.
* Seeds.
* Scripts.
* Sincronización.

## Inventario inicial

Pendiente.

## Grafo PK/FK

Pendiente.

## Tablas migradas

Pendiente.

## Contratos migrados

Pendiente.

## Violaciones eliminadas

Pendiente.

## Validaciones

```text
[ ] Backup verificado.
[ ] Migración atómica ejecutada.
[ ] Conteos pre/post coinciden.
[ ] PRAGMA foreign_key_check sin errores.
[ ] PRAGMA integrity_check = ok.
[ ] Cero PK funcionales enteras.
[ ] Cero FK funcionales enteras.
[ ] Cero AUTOINCREMENT funcional.
[ ] Cero lastrowid funcional.
[ ] Cero casts int(..._id).
[ ] Cero legacy_id.
[ ] Cero escritura dual.
[ ] Cero fallback.
[ ] Tests UUIDv7 aprobados.
```

## Resultado

```text
NOT DONE
```
""",
    "modules/README.md": """# Reportes por módulo

Cada módulo debe tener un reporte acumulativo:

```text
modules/<codigo_modulo>.md
```

Ejemplos:

```text
modules/productos.md
modules/inventario.md
modules/ventas.md
```

No crear un reporte diferente para cada iteración.

Cada iteración se agrega al mismo archivo para conservar historial.

## Formato mínimo

```text
Módulo
Estado
Iteración
Hallazgos
Causas raíz
Tests agregados
Archivos creados
Archivos modificados
Archivos eliminados
Migraciones
Validación manual
Regresiones
Violaciones restantes
Siguiente estado
```
""",
}


def _backup(path: Path) -> Path:
    suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak.{suffix}")
    shutil.copy2(path, backup_path)
    return backup_path


def _write_missing_file(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _parse_queue_rows(content: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in content.splitlines():
        match = re.match(r"^\|\s*\d+\s*\|\s*([A-Z0-9_]+)\s*\|.*\|\s*([A-Z_]+)\s*\|$", line)
        if match:
            rows.append((match.group(1), match.group(2)))
    return rows


def _parse_current_module_code(content: str) -> str | None:
    matches = re.findall(r"## Código\s*\n\s*```text\s*\n([^\n]+)\n```", content)
    if len(matches) != 1:
        return None
    return matches[0].strip()


def _read_state(state_path: Path, repaired: list[str]) -> dict[str, Any]:
    if not state_path.exists():
        return _initial_state()
    try:
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _backup(state_path)
        repaired.append(str(state_path.relative_to(PACKAGE_ROOT)))
        return _initial_state()
    if not isinstance(loaded, dict):
        _backup(state_path)
        repaired.append(str(state_path.relative_to(PACKAGE_ROOT)))
        return _initial_state()
    return loaded


def _normalize_state(state: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(_initial_state())
    normalized.update({k: v for k, v in state.items() if k != "modules"})
    existing_modules = state.get("modules") if isinstance(state.get("modules"), dict) else {}
    normalized["modules"] = deepcopy(_initial_state()["modules"])
    for code, data in existing_modules.items():
        if code not in normalized["modules"] or not isinstance(data, dict):
            continue
        normalized["modules"][code].update(data)
        if normalized["modules"][code].get("status") not in ALLOWED_MODULE_STATES:
            normalized["modules"][code]["status"] = "PENDING"
        normalized["modules"][code]["report"] = _module_report_for(code)
    if normalized.get("current_module") not in normalized["modules"]:
        normalized["current_module"] = "CONFIGURACION"
    return normalized


def bootstrap_refactor_state(base_path: Path = BASE_PATH) -> dict[str, list[str]]:
    base_path = base_path.resolve()
    package_root = PACKAGE_ROOT.resolve()
    if not base_path.is_relative_to(package_root):
        raise ValueError(f"Refactor base path must be inside package root: {package_root}")

    created: list[str] = []
    repaired: list[str] = []
    base_path.mkdir(parents=True, exist_ok=True)
    (base_path / "modules").mkdir(parents=True, exist_ok=True)

    for relative_path, content in INITIAL_FILES.items():
        path = base_path / relative_path
        if _write_missing_file(path, content):
            created.append(str(path.relative_to(PACKAGE_ROOT)))

    queue_path = base_path / "MODULE_QUEUE.md"
    queue_rows = _parse_queue_rows(queue_path.read_text(encoding="utf-8"))
    queue_codes = [code for code, _status in queue_rows]
    queue_statuses = [status for _code, status in queue_rows]
    expected_codes = [code for code, _name in MODULE_QUEUE]
    if queue_codes != expected_codes or any(status not in ALLOWED_MODULE_STATES for status in queue_statuses):
        _backup(queue_path)
        queue_path.write_text(_module_queue_markdown(), encoding="utf-8")
        repaired.append(str(queue_path.relative_to(PACKAGE_ROOT)))

    state_path = base_path / "refactor_state.json"
    state = _normalize_state(_read_state(state_path, repaired))
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    current_path = base_path / "CURRENT_MODULE.md"
    current_code = _parse_current_module_code(current_path.read_text(encoding="utf-8"))
    if current_code != state["current_module"]:
        _backup(current_path)
        current_module = state["modules"][state["current_module"]]
        current_path.write_text(
            _current_module_markdown(
                state["current_module"],
                str(current_module.get("status", "PENDING")),
                int(current_module.get("iteration", 0)),
            ),
            encoding="utf-8",
        )
        repaired.append(str(current_path.relative_to(PACKAGE_ROOT)))

    json.loads(state_path.read_text(encoding="utf-8"))

    missing_modules = sorted(set(expected_codes) - set(state["modules"]))
    if missing_modules:
        raise ValueError(f"refactor_state.json is missing modules: {missing_modules}")

    return {"created": created, "repaired": repaired}


def main() -> int:
    result = bootstrap_refactor_state()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
