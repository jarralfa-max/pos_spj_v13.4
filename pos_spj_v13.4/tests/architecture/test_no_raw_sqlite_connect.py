"""Fase G — Guardrail: prohibición de `sqlite3.connect` fuera del pool.

El ERP tiene UNA fuente de conexiones: el pool de `core/db/connection.py`
(WAL, `foreign_keys=ON`, `busy_timeout`, `row_factory=Row`, thread-safe). Un
`sqlite3.connect()` desnudo en código de negocio (servicios, repositorios, UI)
salta todas esas garantías: sin FK, sin WAL, sin timeout, con transacciones
implícitas — la clase de bug que este proyecto ya erradicó del schema.

Este guardrail es un HARD LOCK con allowlist: el conjunto de archivos que llaman
`sqlite3.connect` debe ser EXACTAMENTE la allowlist. Consecuencias:

  * Un archivo NUEVO que abra una conexión cruda ⇒ falla (debe usar el pool /
    la conexión inyectada, o justificarse editando la allowlist).
  * Un archivo de la allowlist que se refactorice al pool ⇒ falla hasta que se
    quite de la allowlist (ratchet decreciente: la superficie solo baja).

Detección por AST (no regex): ignora comentarios y strings, y resuelve alias
(`import sqlite3 as _sqlite3`) e importación directa (`from sqlite3 import
connect`).
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]  # pos_spj_v13.4/ (paquete)

# Directorios fuera del runtime del ERP (no consumen el pool): tests, scripts
# CLI, migraciones (fuente del schema), entornos y vendored.
EXCLUDE_DIRS = {
    "tests", "scripts", "migrations", ".venv", "venv", "__pycache__",
    "rasa", "rasa_project", "frontend", "node_modules", ".git",
}

# Archivos autorizados a abrir una conexión cruda, con su justificación. Toda
# entrada es infraestructura/arranque o un proceso independiente que NO puede
# consumir el pool del AppContainer.
ALLOWLIST = {
    # El pool canónico: la única fuente legítima de conexiones del ERP.
    "core/db/connection.py",
    # VACUUM no corre dentro de transacción → conexión separada (documentado in-line).
    "core/app_container.py",
    # Validador de arranque (diagnóstico), no ruta de negocio.
    "core/migration_validator.py",
    # Lee la BD del microservicio WhatsApp (DB foránea, distinta del pool).
    "core/repositories/whatsapp_metrics_repository.py",
    # Lectura de config antes de existir el AppContainer (bootstrap).
    "core/integrations/whatsapp_client.py",
    # ConnectionFactory de la capa de infraestructura (reservada API/backend).
    "backend/infrastructure/db/database.py",
    # DB `:memory:` desechable de diagnóstico.
    "interfaz/diagnostico.py",
    # Respaldos a nivel de archivo: conexiones crudas src/dest de otra BD.
    "modulos/sistema/backup_engine.py",
    # Bootstrap de arranque: migraciones/integridad antes del AppContainer.
    "main.py",
    # Microservicio web independiente (proceso propio, puerto 8769).
    "webapp/api_pedidos.py",
    # Herramientas CLI (diagnóstico/reparación/refactor), fuera del runtime.
    "tools/born_clean_audit.py",
    "tools/fix_invalid_branch_identity.py",
    "tools/refactor_control/build_cutover_spec.py",
    # Visores ad-hoc de desarrollo (CLI en la raíz).
    "ver_datos.py",
    "ver_table.py",
}


def _sqlite_connect_lines(tree: ast.AST) -> list[int]:
    """Líneas donde se llama a `<sqlite3-alias>.connect(...)` o `connect(...)`
    importado desde sqlite3."""
    aliases: set[str] = set()
    direct = False
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name == "sqlite3":
                    aliases.add(a.asname or "sqlite3")
        elif isinstance(n, ast.ImportFrom) and n.module == "sqlite3":
            for a in n.names:
                if a.name == "connect":
                    direct = True

    hits: list[int] = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if (isinstance(f, ast.Attribute) and f.attr == "connect"
                and isinstance(f.value, ast.Name) and f.value.id in aliases):
            hits.append(n.lineno)
        elif direct and isinstance(f, ast.Name) and f.id == "connect":
            hits.append(n.lineno)
    return hits


def _scan() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for f in REPO.rglob("*.py"):
        rel = f.relative_to(REPO)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        hits = _sqlite_connect_lines(tree)
        if hits:
            found[rel.as_posix()] = hits
    return found


def test_no_raw_sqlite_connect_outside_pool():
    offenders = _scan()
    offending_files = set(offenders)

    nuevos = sorted(offending_files - ALLOWLIST)
    assert not nuevos, (
        "Conexiones SQLite crudas fuera del pool en archivos NO autorizados.\n"
        "Usa el pool (`core.db.connection.get_connection`) o la conexión "
        "inyectada (AppContainer.db / repos). Si es infraestructura o un "
        "proceso independiente legítimo, justifícalo en la ALLOWLIST:\n"
        + "\n".join(f"  {f}: líneas {offenders[f]}" for f in nuevos)
    )

    obsoletos = sorted(ALLOWLIST - offending_files)
    assert not obsoletos, (
        "Estos archivos ya NO llaman sqlite3.connect (¿migrados al pool?). "
        "Quítalos de la ALLOWLIST para que el ratchet siga bajando:\n"
        + "\n".join(f"  {f}" for f in obsoletos)
    )
