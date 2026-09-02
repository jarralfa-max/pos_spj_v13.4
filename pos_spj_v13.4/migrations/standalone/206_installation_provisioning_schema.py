# migrations/standalone/206_installation_provisioning_schema.py
"""SHELL-2 — Installation provisioning schema.

Creates the `installation` singleton table (provisioning lifecycle state:
UNINITIALIZED → PROVISIONING → PROVISIONED, or LOCKED/RECOVERY_REQUIRED) and
`installation_recovery_codes` (hashed, single-use backup codes for the
installation's recovery kit).

Also seeds the `system_owner` system role — the role assigned to the first
account created by `InitialSetupWizard` / `CreateInitialOwnerUseCase`.
Distinct from `admin` (which stays available as a normal operational role
afterwards): full access, same permission matrix as admin, born with a
canonical UUIDv7 identity (see `backend.shared.ids.SYSTEM_ROLE_UUIDS`) —
never seeded with integers, matching the born-clean pattern m000 already
established for the other system roles.

DDL lives in `backend/infrastructure/db/schema/installation_schema.py`; only
this migration may call `create_installation_schema`.
"""
from __future__ import annotations

import logging

from backend.infrastructure.db.schema.installation_schema import create_installation_schema
from backend.shared.ids import SYSTEM_ROLE_UUIDS, new_uuid

logger = logging.getLogger("spj.migrations.206")

_MODULOS = [
    'DASHBOARD', 'POS', 'INVENTARIO', 'PRODUCTOS', 'CLIENTES', 'COMPRAS',
    'CAJA', 'REPORTES_BI', 'FINANZAS_UNIFICADAS', 'TESORERIA', 'RRHH',
    'CONFIGURACION', 'USUARIOS', 'DELIVERY', 'COTIZACIONES', 'MERMA',
    'PROVEEDORES', 'PRODUCCION', 'TRANSFERENCIAS',
]
_ACCIONES = ['ver', 'crear', 'editar', 'eliminar', 'exportar']


def _add_recovery_contact_column(conn) -> None:
    """`usuarios.recovery_contact` — email or E.164 phone captured on the
    owner_account_page of InitialSetupWizard, used by AccountRecoveryService
    to know where to deliver a recovery token. Additive, idempotent."""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(usuarios)").fetchall()]
    if "recovery_contact" not in cols:
        conn.execute("ALTER TABLE usuarios ADD COLUMN recovery_contact TEXT")


def _seed_system_owner_role(conn) -> None:
    role_id = SYSTEM_ROLE_UUIDS["system_owner"]
    conn.execute(
        "INSERT OR IGNORE INTO roles (id, nombre, descripcion, activo) VALUES (?,?,?,1)",
        (role_id, "system_owner", "Propietario del sistema — acceso total (creado en provisioning)"),
    )
    for modulo in _MODULOS:
        for accion in _ACCIONES:
            conn.execute(
                "INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido) "
                "VALUES (?,?,?,?,1)",
                (new_uuid(), role_id, modulo, accion),
            )


def run(conn) -> None:
    create_installation_schema(conn)
    _add_recovery_contact_column(conn)
    _seed_system_owner_role(conn)
    conn.commit()
    logger.info("206: installation provisioning schema + system_owner role created.")


up = run
