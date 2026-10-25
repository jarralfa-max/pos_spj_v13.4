"""347 — Auditoría global de permisos 968e0bc (2026-10-23).

1. PER-04 — los códigos PLANOS de Mermas, Proveedores y Transferencias
   (`LOSSES_APPROVE`, `SUPPLIERS_ACTIVATE`, `TRANSFERS_RECEIVE`) pasan a
   `MERMA.`, `PROVEEDORES.` y `TRANSFERENCIAS.<accion>`. Correspondencia 1:1
   explícita (abajo): ningún código plano se traduce a más de uno, así que la
   traducción no amplía ningún privilegio. Se traducen las filas de
   `rol_permisos`, `usuario_permisos` y `usuario_sucursal_permisos` que hubiera
   con el código plano (la matriz no podía crearlas, pero un import o una
   escritura directa sí). Medido en la base real: 0 filas.
2. PER-06 — `usuario_permisos` y `usuario_sucursal_permisos` no tenían llave
   única por (usuario[, sucursal], módulo, acción): dos filas del mismo permiso
   se aplicaban en orden indefinido. Se normaliza la forma (MÓDULO en
   mayúsculas, acción en minúsculas), se eliminan duplicados —si chocan conceder
   y negar, gana NEGAR, la opción conservadora— y se crean índices únicos.
   Medido en la base real: 0 filas, 0 duplicados.
3. PER-08 — `security_grant_versions`: una versión que sube cada vez que cambia
   una concesión (rol o excepción). Las sesiones abiertas la consultan y
   recargan sus permisos: una revocación ya no espera a que el usuario cierre
   sesión.

No toca las tablas del RBAC heredado (`permisos`, `roles_permisos`,
`usuarios_roles`): 0 filas en la base real y ya sin consumidores, pero la
especificación del corte UUID (`_cutover_spec_generated.py`) y la migración 116
todavía las nombran; retirarlas es una migración aparte (ver
docs/refactor/PERM-AUD_auditoria_968e0bc.md).

Idempotente.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.347")

#: Código plano → (MÓDULO, acción). Idéntico a las constantes de
#: `backend/application/{losses,suppliers,transfers}/permissions.py`; la prueba
#: tests/integration/security/test_permissions_audit_968e0bc.py lo comprueba.
FLAT_CODE_TRANSLATION: dict[str, tuple[str, str]] = {
    # ── Mermas ──────────────────────────────────────────────────────────────
    "LOSSES_ACCESS": ("MERMA", "acceso"), "LOSSES_VIEW": ("MERMA", "ver"),
    "LOSSES_VIEW_OWN_BRANCH": ("MERMA", "ver.sucursal_propia"),
    "LOSSES_VIEW_ASSIGNED_BRANCHES": ("MERMA", "ver.sucursales_asignadas"),
    "LOSSES_VIEW_ALL_BRANCHES": ("MERMA", "ver.todas_sucursales"),
    "LOSSES_VIEW_COST": ("MERMA", "costo.ver"), "LOSSES_VIEW_AUDIT": ("MERMA", "auditoria.ver"),
    "LOSSES_EXPORT": ("MERMA", "exportar"),
    "LOSSES_OVERVIEW_VIEW": ("MERMA", "resumen.ver"),
    "LOSSES_REGISTRATION_VIEW": ("MERMA", "registro.ver"),
    "LOSSES_PENDING_VIEW": ("MERMA", "pendientes.ver"),
    "LOSSES_PRODUCTION_VIEW": ("MERMA", "produccion.ver"),
    "LOSSES_INVENTORY_VIEW": ("MERMA", "inventario.ver"),
    "LOSSES_EXPIRY_DAMAGE_VIEW": ("MERMA", "caducidad_dano.ver"),
    "LOSSES_QUALITY_VIEW": ("MERMA", "calidad.ver"),
    "LOSSES_YIELD_VIEW": ("MERMA", "rendimiento.ver"),
    "LOSSES_RECOVERY_VIEW": ("MERMA", "recuperacion.ver"),
    "LOSSES_DISPOSITION_VIEW": ("MERMA", "disposicion.ver"),
    "LOSSES_INVESTIGATION_VIEW": ("MERMA", "investigacion.ver"),
    "LOSSES_CORRECTIVE_ACTION_VIEW": ("MERMA", "accion_correctiva.ver"),
    "LOSSES_ALERT_VIEW": ("MERMA", "alertas.ver"),
    "LOSSES_ANALYTICS_VIEW": ("MERMA", "analisis.ver"),
    "LOSSES_SETTINGS_VIEW": ("MERMA", "configuracion.ver"),
    "LOSSES_REPORT": ("MERMA", "reportar"), "LOSSES_EDIT_DRAFT": ("MERMA", "borrador.editar"),
    "LOSSES_SUBMIT": ("MERMA", "enviar"), "LOSSES_REVIEW": ("MERMA", "revisar"),
    "LOSSES_APPROVE": ("MERMA", "aprobar"), "LOSSES_REJECT": ("MERMA", "rechazar"),
    "LOSSES_POST_INVENTORY": ("MERMA", "inventario.aplicar"),
    "LOSSES_REVERSE_INVENTORY": ("MERMA", "inventario.reversar"),
    "LOSSES_VALUE_LOSS": ("MERMA", "valorizar"), "LOSSES_CLOSE": ("MERMA", "cerrar"),
    "LOSSES_REOPEN": ("MERMA", "reabrir"),
    "LOSSES_APPROVE_OVER_LIMIT": ("MERMA", "aprobar_sobre_limite"),
    "LOSSES_PLAN_DISPOSAL": ("MERMA", "disposicion.planear"),
    "LOSSES_AUTHORIZE_DISPOSAL": ("MERMA", "disposicion.autorizar"),
    "LOSSES_COMPLETE_DISPOSAL": ("MERMA", "disposicion.completar"),
    "LOSSES_RECORD_RECOVERY": ("MERMA", "recuperacion.registrar"),
    "LOSSES_APPROVE_RECOVERY": ("MERMA", "recuperacion.aprobar"),
    "LOSSES_QUALITY_REJECT": ("MERMA", "calidad.rechazar"),
    "LOSSES_QUALITY_CONDEMN": ("MERMA", "calidad.condenar"),
    "LOSSES_TRANSFER_LINK": ("MERMA", "transferencia.vincular"),
    "LOSSES_MANAGE_CLAIMS": ("MERMA", "reclamaciones.gestionar"),
    "LOSSES_OPEN_INVESTIGATION": ("MERMA", "investigacion.abrir"),
    "LOSSES_INVESTIGATE": ("MERMA", "investigacion.investigar"),
    "LOSSES_CONCLUDE_INVESTIGATION": ("MERMA", "investigacion.concluir"),
    "LOSSES_MANAGE_ROOT_CAUSE": ("MERMA", "causa_raiz.gestionar"),
    "LOSSES_CREATE_CORRECTIVE_ACTION": ("MERMA", "accion_correctiva.crear"),
    "LOSSES_VERIFY_CORRECTIVE_ACTION": ("MERMA", "accion_correctiva.verificar"),
    "LOSSES_MANAGE_CLASSIFICATIONS": ("MERMA", "clasificaciones.gestionar"),
    "LOSSES_MANAGE_REASONS": ("MERMA", "motivos.gestionar"),
    "LOSSES_MANAGE_POLICIES": ("MERMA", "politicas.gestionar"),
    "LOSSES_MANAGE_NOTIFICATIONS": ("MERMA", "notificaciones.gestionar"),
    # ── Proveedores ─────────────────────────────────────────────────────────
    "SUPPLIERS_VIEW": ("PROVEEDORES", "ver"), "SUPPLIERS_CREATE": ("PROVEEDORES", "crear"),
    "SUPPLIERS_EDIT": ("PROVEEDORES", "editar"), "SUPPLIERS_SUBMIT": ("PROVEEDORES", "enviar"),
    "SUPPLIERS_APPROVE": ("PROVEEDORES", "aprobar"),
    "SUPPLIERS_ACTIVATE": ("PROVEEDORES", "activar"),
    "SUPPLIERS_SUSPEND": ("PROVEEDORES", "suspender"),
    "SUPPLIERS_DEACTIVATE": ("PROVEEDORES", "baja"),
    "SUPPLIERS_BLOCK": ("PROVEEDORES", "bloquear"),
    "SUPPLIERS_UNBLOCK": ("PROVEEDORES", "desbloquear"),
    "SUPPLIERS_VIEW_FINANCIAL": ("PROVEEDORES", "finanzas.ver"),
    "SUPPLIERS_EDIT_TERMS": ("PROVEEDORES", "condiciones.editar"),
    "SUPPLIERS_VIEW_BANK": ("PROVEEDORES", "banco.ver"),
    "SUPPLIERS_EDIT_BANK": ("PROVEEDORES", "banco.editar"),
    "SUPPLIERS_VERIFY_BANK": ("PROVEEDORES", "banco.verificar"),
    "SUPPLIERS_VIEW_DOCUMENTS": ("PROVEEDORES", "documentos.ver"),
    "SUPPLIERS_UPLOAD_DOCUMENTS": ("PROVEEDORES", "documentos.cargar"),
    "SUPPLIERS_EVALUATE": ("PROVEEDORES", "evaluar"),
    "SUPPLIERS_EXPORT": ("PROVEEDORES", "exportar"),
    "SUPPLIERS_VIEW_AUDIT": ("PROVEEDORES", "auditoria.ver"),
    # ── Transferencias ──────────────────────────────────────────────────────
    "TRANSFERS_ACCESS": ("TRANSFERENCIAS", "acceso"),
    "TRANSFERS_DASHBOARD_VIEW": ("TRANSFERENCIAS", "tablero.ver"),
    "TRANSFERS_VIEW_OWN_BRANCH": ("TRANSFERENCIAS", "ver.sucursal_propia"),
    "TRANSFERS_VIEW_ASSIGNED_BRANCHES": ("TRANSFERENCIAS", "ver.sucursales_asignadas"),
    "TRANSFERS_VIEW_ALL_BRANCHES": ("TRANSFERENCIAS", "ver.todas_sucursales"),
    "TRANSFERS_EXPORT": ("TRANSFERENCIAS", "exportar"),
    "TRANSFERS_AUDIT_VIEW": ("TRANSFERENCIAS", "auditoria.ver"),
    "TRANSFERS_REQUEST_VIEW": ("TRANSFERENCIAS", "solicitud.ver"),
    "TRANSFERS_REQUEST_CREATE": ("TRANSFERENCIAS", "solicitud.crear"),
    "TRANSFERS_REQUEST_EDIT": ("TRANSFERENCIAS", "solicitud.editar"),
    "TRANSFERS_REQUEST_SUBMIT": ("TRANSFERENCIAS", "solicitud.enviar"),
    "TRANSFERS_REQUEST_CANCEL": ("TRANSFERENCIAS", "solicitud.cancelar"),
    "TRANSFERS_APPROVE": ("TRANSFERENCIAS", "aprobar"),
    "TRANSFERS_REJECT": ("TRANSFERENCIAS", "rechazar"),
    "TRANSFERS_PARTIAL_APPROVE": ("TRANSFERENCIAS", "aprobar_parcial"),
    "TRANSFERS_OVERRIDE_LIMIT": ("TRANSFERENCIAS", "exceder_limite"),
    "TRANSFERS_RESERVE": ("TRANSFERENCIAS", "reservar"),
    "TRANSFERS_ALLOCATE": ("TRANSFERENCIAS", "asignar"),
    "TRANSFERS_PICK": ("TRANSFERENCIAS", "surtir"),
    "TRANSFERS_PICK_OVERRIDE_LOT": ("TRANSFERENCIAS", "surtir.cambiar_lote"),
    "TRANSFERS_PICK_CONFIRM": ("TRANSFERENCIAS", "surtir.confirmar"),
    "TRANSFERS_DISPATCH_VIEW": ("TRANSFERENCIAS", "despacho.ver"),
    "TRANSFERS_DISPATCH": ("TRANSFERENCIAS", "despachar"),
    "TRANSFERS_PARTIAL_DISPATCH": ("TRANSFERENCIAS", "despachar_parcial"),
    "TRANSFERS_CANCEL_SHIPMENT": ("TRANSFERENCIAS", "embarque.cancelar"),
    "TRANSFERS_RECEIVE_VIEW": ("TRANSFERENCIAS", "recepcion.ver"),
    "TRANSFERS_RECEIVE": ("TRANSFERENCIAS", "recibir"),
    "TRANSFERS_PARTIAL_RECEIVE": ("TRANSFERENCIAS", "recibir_parcial"),
    "TRANSFERS_BLIND_RECEIVE": ("TRANSFERENCIAS", "recibir_a_ciegas"),
    "TRANSFERS_RECEIVE_OVER_TOLERANCE": ("TRANSFERENCIAS", "recibir_sobre_tolerancia"),
    "TRANSFERS_MANUAL_WEIGHT_OVERRIDE": ("TRANSFERENCIAS", "peso.capturar_manual"),
    "TRANSFERS_DIFFERENCE_VIEW": ("TRANSFERENCIAS", "diferencia.ver"),
    "TRANSFERS_DIFFERENCE_REVIEW": ("TRANSFERENCIAS", "diferencia.revisar"),
    "TRANSFERS_DIFFERENCE_RESOLVE": ("TRANSFERENCIAS", "diferencia.resolver"),
    "TRANSFERS_DIFFERENCE_ACCEPT": ("TRANSFERENCIAS", "diferencia.aceptar"),
    "TRANSFERS_DIFFERENCE_REJECT": ("TRANSFERENCIAS", "diferencia.rechazar"),
    "TRANSFERS_RETURN_CREATE": ("TRANSFERENCIAS", "devolucion.crear"),
    "TRANSFERS_RETURN_APPROVE": ("TRANSFERENCIAS", "devolucion.aprobar"),
    "TRANSFERS_RETURN_DISPATCH": ("TRANSFERENCIAS", "devolucion.despachar"),
    "TRANSFERS_REVERSE": ("TRANSFERENCIAS", "reversar"),
    "TRANSFERS_PRINT": ("TRANSFERENCIAS", "imprimir"),
    "TRANSFERS_REPRINT": ("TRANSFERENCIAS", "reimprimir"),
    "TRANSFERS_SETTINGS_VIEW": ("TRANSFERENCIAS", "configuracion.ver"),
    "TRANSFERS_SETTINGS_MANAGE": ("TRANSFERENCIAS", "configuracion.gestionar"),
    "TRANSFERS_NOTIFICATIONS_MANAGE": ("TRANSFERENCIAS", "notificaciones.gestionar"),
    "TRANSFERS_WHATSAPP_ALERTS_MANAGE": ("TRANSFERENCIAS", "whatsapp.gestionar"),
}

#: Tabla → columnas que identifican al titular de la concesión (además del código).
_GRANT_TABLES = {
    "rol_permisos": ("rol_id",),
    "usuario_permisos": ("usuario_id",),
    "usuario_sucursal_permisos": ("usuario_id", "sucursal_id"),
}

_UNIQUE_INDEXES = {
    "usuario_permisos": ("ux_usuario_permisos_codigo", ("usuario_id", "modulo", "accion")),
    "usuario_sucursal_permisos": ("ux_usuario_sucursal_permisos_codigo",
                                  ("usuario_id", "sucursal_id", "modulo", "accion")),
}


def _table(conn, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (name,)).fetchone() is not None


def _flat_code(modulo, accion) -> str | None:
    """El código plano que representa una fila, si lo es. `split_permission`
    guarda un código sin punto como `('', código)`; se acepta también el código
    entero en `modulo` o concatenado, por si una escritura directa lo hizo así."""
    modulo = str(modulo or "").strip()
    accion = str(accion or "").strip()
    for candidato in (accion, modulo, f"{modulo}_{accion}" if modulo and accion else ""):
        if candidato.upper() in FLAT_CODE_TRANSLATION:
            return candidato.upper()
    return None


def _translate_flat_codes(conn) -> int:
    traducidas = 0
    for table, owner_cols in _GRANT_TABLES.items():
        if not _table(conn, table):
            continue
        cols = ", ".join(owner_cols)
        filas = conn.execute(f"SELECT id, {cols}, modulo, accion FROM {table}").fetchall()
        for fila in filas:
            row_id, owner = fila[0], tuple(fila[1:1 + len(owner_cols)])
            plano = _flat_code(fila[-2], fila[-1])
            if plano is None:
                continue
            modulo, accion = FLAT_CODE_TRANSLATION[plano]
            where_owner = " AND ".join(f"{c}=?" for c in owner_cols)
            ya = conn.execute(
                f"SELECT 1 FROM {table} WHERE {where_owner} AND modulo=? AND accion=? AND id<>?",
                (*owner, modulo, accion, row_id)).fetchone()
            if ya:
                # El titular ya tiene el código nuevo: la fila plana sobra.
                conn.execute(f"DELETE FROM {table} WHERE id=?", (row_id,))
            else:
                conn.execute(f"UPDATE {table} SET modulo=?, accion=? WHERE id=?",
                             (modulo, accion, row_id))
            traducidas += 1
    return traducidas


def _dedupe_and_index(conn) -> int:
    eliminadas = 0
    for table, (index, key_cols) in _UNIQUE_INDEXES.items():
        if not _table(conn, table):
            continue
        conn.execute(f"UPDATE {table} SET modulo=upper(trim(modulo)), accion=lower(trim(accion))")
        owner = [c for c in key_cols if c not in ("modulo", "accion")]
        cols = ", ".join(key_cols)
        grupos = conn.execute(
            f"SELECT {cols}, COUNT(*) FROM {table} GROUP BY {cols} HAVING COUNT(*) > 1"
        ).fetchall()
        for grupo in grupos:
            clave = tuple(grupo[:len(key_cols)])
            where = " AND ".join(f"{c}=?" for c in key_cols)
            filas = conn.execute(
                f"SELECT id, COALESCE(permitido, 1) FROM {table} WHERE {where}"
                " ORDER BY COALESCE(permitido, 1) ASC, id ASC", clave).fetchall()
            # NEGAR (permitido=0) ordena primero: es la fila que se conserva.
            for row_id, _permitido in filas[1:]:
                conn.execute(f"DELETE FROM {table} WHERE id=?", (row_id,))
                eliminadas += 1
            logger.warning("347: %s duplicado para %s; se conserva %s",
                           table, dict(zip(owner, clave)), "NEGAR" if filas[0][1] == 0
                           else "CONCEDER")
        conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {index} ON {table} ({cols})")
    return eliminadas


def _grant_versions(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS security_grant_versions (
            scope      TEXT NOT NULL PRIMARY KEY,
            version    INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        )
    """)
    conn.execute("INSERT OR IGNORE INTO security_grant_versions (scope, version) VALUES ('global', 0)")


def run(conn) -> None:
    traducidas = _translate_flat_codes(conn)
    eliminadas = _dedupe_and_index(conn)
    _grant_versions(conn)
    logger.info("347: %d concesiones con código plano traducidas, %d excepciones duplicadas "
                "eliminadas; versión de concesiones lista", traducidas, eliminadas)
