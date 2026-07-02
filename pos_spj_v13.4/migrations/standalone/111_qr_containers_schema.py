"""Migración 111 — esquema de QR/contenedores (compras).

Mueve a migraciones el schema que antes creaba la UI en
``modulos/compras_pro.py::_ensure_qr_schema`` (regla: solo ``migrations/`` modifica
schema). Idempotente. Las PK enteras se preservan tal cual; su conversión a UUID
``TEXT`` corresponde al corte global de identidad (Fase 2.5 / migración 200).
"""

import logging

logger = logging.getLogger("spj.migrations")


def run(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS contenedores (
            id              TEXT PRIMARY KEY,
            codigo          TEXT UNIQUE NOT NULL,
            tipo            TEXT NOT NULL DEFAULT 'caja',
            descripcion     TEXT,
            sucursal_destino INTEGER,
            proveedor_id    TEXT,
            comprador       TEXT,
            folio_factura   TEXT,
            fecha_factura   TEXT,
            metodo_pago     TEXT,
            forma_pago      TEXT,
            plazo_dias      INTEGER DEFAULT 0,
            vence_pago      TEXT,
            total           REAL DEFAULT 0,
            estado          TEXT DEFAULT 'generado',
            fecha_creado    TEXT DEFAULT CURRENT_TIMESTAMP,
            fecha_asignado  TEXT,
            fecha_recibido  TEXT,
            usuario_creado  TEXT,
            usuario_asign   TEXT,
            usuario_recibe  TEXT,
            recibido_por    TEXT,
            observaciones   TEXT,
            compra_id       TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS contenedor_productos (
            id              TEXT PRIMARY KEY,
            contenedor_id   TEXT NOT NULL,
            producto_id     TEXT NOT NULL,
            cantidad        REAL NOT NULL DEFAULT 0,
            costo_unitario  REAL NOT NULL DEFAULT 0,
            cantidad_recibida REAL DEFAULT NULL,
            observaciones   TEXT,
            FOREIGN KEY(contenedor_id) REFERENCES contenedores(id) ON DELETE CASCADE
        )
        """
    )
    # Columnas añadidas incrementalmente (idempotente — ignora si ya existen).
    for col_sql in (
        "ALTER TABLE contenedores ADD COLUMN comprador TEXT",
        "ALTER TABLE contenedores ADD COLUMN observaciones TEXT",
        "ALTER TABLE contenedores ADD COLUMN recibido_por TEXT",
        "ALTER TABLE contenedores ADD COLUMN sucursal_destino INTEGER",
        "ALTER TABLE contenedor_productos ADD COLUMN observaciones TEXT",
        "ALTER TABLE contenedores ADD COLUMN parent_id TEXT REFERENCES contenedores(id)",
        "ALTER TABLE contenedores ADD COLUMN seq_num INTEGER",
    ):
        try:
            conn.execute(col_sql)
        except Exception:
            pass
    try:
        conn.commit()
    except Exception:
        pass
    logger.info("Migración 111 (QR/contenedores schema) completada.")
