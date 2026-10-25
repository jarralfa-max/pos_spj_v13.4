"""351 — Estructura organizacional (auditoría enterprise, Fase 1; N06/N12).

La organización es el perfil de empresa que ya existe (`company_profiles`,
`installation.company_id`). Esta migración agrega lo que faltaba debajo:

1. `org_units`: unidades con tipo (sucursal, planta, centro de distribución,
   almacén, oficina corporativa, operación logística, región), jerarquía por
   `parent_id` y ciclo ACTIVE/INACTIVE/CLOSED.
2. `org_unit_capabilities`: capacidades explícitas por unidad (SALES, POS,
   CASH…), con quién y por qué.
3. `org_unit_id` en `cost_centers`, `profit_centers` y `hr_departments`, para
   colgar centros de costo/utilidad y departamentos de cualquier unidad (una
   región, la oficina corporativa), no sólo de una sucursal.
4. Respaldo: cada fila de `sucursales` se vuelve una unidad RETAIL_BRANCH con el
   MISMO id —todo `branch_id` existente sigue siendo válido— y con TODAS las
   capacidades: hoy toda sucursal puede hacer todo, y eso no cambia sin que
   alguien lo decida. Si la base todavía no tiene empresa (instalación sin
   aprovisionar) no se respalda nada: el aprovisionamiento crea la unidad.
5. Siembra `CONFIGURACION.organizacion.*`: `system_owner` y `admin` todo,
   `gerente` sólo ver (otorgable ≠ otorgado, criterio de la 290/349).

Sólo agrega: no renombra, no borra, no cambia ningún comportamiento. Idempotente.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.351")

_TIPOS = ("RETAIL_BRANCH", "PRODUCTION_PLANT", "DISTRIBUTION_CENTER", "WAREHOUSE",
          "CORPORATE_OFFICE", "LOGISTICS_OPERATION", "REGION")
#: Foto fija de `backend/domain/organization/org_unit.py::Capability`.
CAPACIDADES = ("SALES", "POS", "CASH", "INVENTORY", "PURCHASING", "RECEIVING",
               "PRODUCTION", "LOGISTICS", "FINANCE", "CRM", "BI")
#: Foto fija de `ConfiguracionPermissions.ORGANIZACION_*`.
ACCIONES = ("organizacion.ver", "organizacion.crear", "organizacion.editar",
            "organizacion.cerrar", "organizacion.capacidades")
_ASIGNACIONES = {
    "system_owner": ACCIONES,
    "admin": ACCIONES,
    "gerente": ("organizacion.ver",),
}

_DDL = (
    f"""
    CREATE TABLE IF NOT EXISTS org_units (
        id TEXT NOT NULL PRIMARY KEY,
        company_id TEXT NOT NULL,
        parent_id TEXT REFERENCES org_units(id),
        unit_type TEXT NOT NULL CHECK (unit_type IN ({", ".join(f"'{t}'" for t in _TIPOS)})),
        code TEXT NOT NULL CHECK (trim(code) <> ''),
        name TEXT NOT NULL CHECK (trim(name) <> ''),
        status TEXT NOT NULL DEFAULT 'ACTIVE'
            CHECK (status IN ('ACTIVE','INACTIVE','CLOSED')),
        created_by TEXT,
        closed_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK (parent_id IS NULL OR parent_id <> id),
        CHECK ((status = 'CLOSED') = (closed_at IS NOT NULL)),
        UNIQUE (company_id, code)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_org_units_parent ON org_units(parent_id)",
    f"""
    CREATE TABLE IF NOT EXISTS org_unit_capabilities (
        org_unit_id TEXT NOT NULL REFERENCES org_units(id),
        capability TEXT NOT NULL CHECK (capability IN ({", ".join(f"'{c}'" for c in CAPACIDADES)})),
        granted_by TEXT,
        reason TEXT NOT NULL CHECK (trim(reason) <> ''),
        granted_at TEXT NOT NULL,
        PRIMARY KEY (org_unit_id, capability)
    )
    """,
)

_COLUMNAS_UNIDAD = ("cost_centers", "profit_centers", "hr_departments")
_CODIGO = re.compile(r"^[A-Z0-9][A-Z0-9_-]{1,23}$")


def _table(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (name,)).fetchone() is not None


def _columns(conn, table: str) -> set[str]:
    return {str(r[1]) for r in conn.execute(f'PRAGMA table_info("{table}")')}


def _empresa(conn) -> str | None:
    if _table(conn, "installation"):
        fila = conn.execute("SELECT company_id FROM installation"
                            " WHERE company_id IS NOT NULL LIMIT 1").fetchone()
        if fila and fila[0]:
            return str(fila[0])
    if _table(conn, "company_profiles"):
        filas = conn.execute("SELECT id FROM company_profiles WHERE active=1").fetchall()
        if len(filas) == 1:   # un solo RFC (decisión D2): sin ambigüedad
            return str(filas[0][0])
    return None


def site_code(nombre: str, perfil: str | None, usados: set[str]) -> str:
    """Código para una sucursal existente: el de su perfil si es válido; si no,
    derivado del nombre. Único dentro de la empresa."""
    candidato = str(perfil or "").strip().upper()
    if not _CODIGO.match(candidato):
        limpio = re.sub(r"[^A-Z0-9]+", "-",
                        _sin_acentos(str(nombre or "")).upper()).strip("-")
        candidato = (limpio or "SUC")[:20].strip("-")
        if len(candidato) < 2:
            candidato = f"SUC-{candidato}" if candidato else "SUC"
    base, n = candidato, 2
    while candidato in usados:
        sufijo = f"-{n}"
        candidato = base[:24 - len(sufijo)] + sufijo
        n += 1
    usados.add(candidato)
    return candidato


def _sin_acentos(texto: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", texto)
                   if not unicodedata.combining(c))


def backfill_sites(conn, company_id: str, *, actor: str | None = None,
                   reason: str = "Sucursal existente antes de la estructura organizacional") -> int:
    """Crea la unidad RETAIL_BRANCH (mismo id, todas las capacidades) de cada fila
    de `sucursales` que aún no tenga unidad. Devuelve cuántas creó."""
    if not (_table(conn, "sucursales") and _table(conn, "org_units")):
        return 0
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    usados = {str(r[0]) for r in conn.execute(
        "SELECT code FROM org_units WHERE company_id=?", (company_id,))}
    perfiles = {}
    if _table(conn, "branch_profiles"):
        perfiles = {str(r[0]): r[1] for r in conn.execute(
            "SELECT branch_id, code FROM branch_profiles")}
    creadas = 0
    for sid, nombre, activa in conn.execute(
            "SELECT s.id, s.nombre, COALESCE(s.activa, 1) FROM sucursales s"
            " WHERE NOT EXISTS (SELECT 1 FROM org_units u WHERE u.id = s.id)"
            " ORDER BY s.rowid").fetchall():
        codigo = site_code(nombre, perfiles.get(str(sid)), usados)
        conn.execute(
            "INSERT INTO org_units (id, company_id, parent_id, unit_type, code, name, status,"
            " created_by, closed_at, created_at, updated_at)"
            " VALUES (?,?,NULL,'RETAIL_BRANCH',?,?,?,?,NULL,?,?)",
            (str(sid), company_id, codigo, str(nombre or codigo).strip() or codigo,
             "ACTIVE" if int(activa or 0) else "INACTIVE", actor, ahora, ahora))
        conn.executemany(
            "INSERT OR IGNORE INTO org_unit_capabilities (org_unit_id, capability, granted_by,"
            " reason, granted_at) VALUES (?,?,?,?,?)",
            [(str(sid), cap, actor, reason, ahora) for cap in CAPACIDADES])
        creadas += 1
    return creadas


def _sembrar_permisos(conn) -> None:
    tablas = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('roles','rol_permisos')")}
    if tablas != {"roles", "rol_permisos"}:
        return
    for rol, acciones in _ASIGNACIONES.items():
        fila = conn.execute("SELECT id FROM roles WHERE lower(trim(nombre))=?",
                            (rol,)).fetchone()
        if fila is None:
            continue
        for accion in acciones:
            conn.execute(
                "INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
                " VALUES (?,?,?,?,1)", (new_uuid(), str(fila[0]), "CONFIGURACION", accion))


def create_org_structure_schema(conn) -> None:
    for sentencia in _DDL:
        conn.execute(sentencia)


def run(conn) -> None:
    create_org_structure_schema(conn)
    for tabla in _COLUMNAS_UNIDAD:
        if _table(conn, tabla) and "org_unit_id" not in _columns(conn, tabla):
            conn.execute(f'ALTER TABLE "{tabla}" ADD COLUMN org_unit_id TEXT')
    empresa = _empresa(conn)
    creadas = backfill_sites(conn, empresa) if empresa else 0
    _sembrar_permisos(conn)
    conn.commit()
    logger.info("351: estructura organizacional lista; %s sucursal(es) respaldada(s)%s.",
                creadas, "" if empresa else " (sin empresa todavía: se omite el respaldo)")


up = run
