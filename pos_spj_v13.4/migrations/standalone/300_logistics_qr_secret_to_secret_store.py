"""300 — El secreto de firma de QR de Logística sale de `configuraciones` (2026-10-04).

`logistics.qr_signing_secret` vivía en texto plano en la tabla genérica de
configuración (§46 lo prohíbe). Desde esta versión lo lee y lo crea el almacén
de secretos (`qr_signing_secret(secret_store)`).

Qué hace con la fila existente:
- Si NO hay etiquetas de contenedor impresas, la borra: el siguiente arranque
  genera un secreto nuevo en el almacén y no hay ninguna etiqueta que invalidar.
- Si SÍ las hay, copia el valor al almacén antes de borrarla, para que esas
  etiquetas sigan validando. Si el almacén no lo acepta, la migración falla:
  borrar la fila sin copiarla invalidaría en silencio todas las etiquetas.

Idempotente: sin fila, no hace nada.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.300")

_KEY = "logistics.qr_signing_secret"


def _printed_labels(conn) -> int:
    try:
        return int(conn.execute("SELECT COUNT(*) FROM logistics_container_labels").fetchone()[0])
    except Exception:  # noqa: BLE001 - sin tabla no hay etiquetas
        return 0


def run(conn, secret_store=None) -> None:
    row = conn.execute("SELECT valor FROM configuraciones WHERE clave=?", (_KEY,)).fetchone()
    if row is None:
        logger.info("300: no hay secreto de QR en configuraciones.")
        return
    labels = _printed_labels(conn)
    if labels:
        if secret_store is None:
            from backend.security.secrets.default_secret_store import build_default_secret_store
            secret_store = build_default_secret_store()
        secret_store.set_secret(_KEY, str(row[0]))
        logger.info("300: secreto de QR copiado al almacén (%s etiquetas impresas).", labels)
    else:
        logger.info("300: sin etiquetas impresas; el secreto de QR se regenera en el almacén.")
    conn.execute("DELETE FROM configuraciones WHERE clave=?", (_KEY,))
    conn.commit()


up = run
