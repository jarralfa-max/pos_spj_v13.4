"""301 — Retira claves de `configuraciones` que nadie lee (2026-10-04).

Re-auditoría de Configuración sobre una copia de la base real: 12 de las 23
claves no tienen ningún lector en `backend/`, `frontend/`, `migrations/` (salvo
las que las siembran) ni en el microservicio `whatsapp_service/`:

- `sync_url`, `sync_api_key`, `sync_interval_seg`, `sync_batch_size`,
  `sync_enabled` — sembradas por 048/054 para el motor `sync/`, borrado.
- `wa_escalacion_min_1..3`, `wa_escalacion_tel_gerente`,
  `wa_msg_escalacion_gerente`, `wa_msg_respuesta_auto` — sembradas por 047
  para la escalación de pedidos del módulo de WhatsApp legacy, borrado.
- `app_version` — sembrada por 047; la versión vive en
  `backend/shared/app_version.py`.

Una clave sin lector es un parámetro que el administrador podría "cambiar" sin
que nada cambie. 047/048/054 las siguen sembrando en una base nueva; esta
migración corre después y la deja limpia. Idempotente.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("spj.migrations.301")

DEAD_KEYS = (
    "sync_url", "sync_api_key", "sync_interval_seg", "sync_batch_size", "sync_enabled",
    "wa_escalacion_min_1", "wa_escalacion_min_2", "wa_escalacion_min_3",
    "wa_escalacion_tel_gerente", "wa_msg_escalacion_gerente", "wa_msg_respuesta_auto",
    "app_version",
)


def run(conn) -> None:
    marks = ",".join("?" for _ in DEAD_KEYS)
    deleted = conn.execute(f"DELETE FROM configuraciones WHERE clave IN ({marks})", DEAD_KEYS).rowcount
    conn.commit()
    logger.info("301: %s claves sin lector retiradas de configuraciones.", deleted)


up = run
