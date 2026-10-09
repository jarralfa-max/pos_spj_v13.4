"""312 — Permisos para probar dispositivos y para dar excepciones a un usuario
(2026-10-08).

- `DISPOSITIVOS.probar`: Configuración → Dispositivos estrena «Probar conexión»
  e «Imprimir página de prueba» (antes no había forma de comprobar desde la
  aplicación que una impresora dada de alta respondía). Ya estaba en el
  catálogo sin que nadie lo exigiera. Lo reciben el dueño y el gerente, que ya
  administra dispositivos (302).
- `CONFIGURACION.usuario.permisos`: dar o quitar permisos a UN usuario además
  de los de su rol. Sólo el dueño, igual que `rol.permisos` (304): es un
  permiso que controla a los demás. Los administradores lo tienen por `*`.

Un rol que no exista se omite. Idempotente.
"""

from __future__ import annotations

import logging

from backend.shared.ids import new_uuid

logger = logging.getLogger("spj.migrations.312")

GRANTS = (
    ("system_owner", "DISPOSITIVOS", "probar"),
    ("gerente", "DISPOSITIVOS", "probar"),
    ("system_owner", "CONFIGURACION", "usuario.permisos"),
)


def run(conn) -> None:
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rol_permisos'"
                    ).fetchone() is None:
        logger.info("312: sin rol_permisos; nada que sembrar.")
        return
    concedidos = 0
    for rol, modulo, accion in GRANTS:
        fila = conn.execute("SELECT id FROM roles WHERE lower(trim(nombre))=?", (rol,)).fetchone()
        if fila is None:
            continue
        cur = conn.execute(
            "INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion, permitido)"
            " VALUES (?,?,?,?,1)", (new_uuid(), str(fila[0]), modulo, accion))
        concedidos += max(cur.rowcount or 0, 0)
    conn.commit()
    logger.info("312: %s permisos concedidos.", concedidos)


up = run
