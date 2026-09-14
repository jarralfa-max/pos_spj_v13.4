"""Tabla `audit_logs` para pruebas que no montan el esquema canónico completo.

`audit_logs` la crea sólo la migración m000. Los casos de uso de Pedidos/Reparto
escriben ahí en la MISMA transacción que su cambio, así que una prueba montada
sólo con `create_orders_delivery_schema` necesita la tabla. En vez de copiar su
DDL al backend —el esquema de Pedidos dice que sólo una migración ejecuta DDL—, la
crea este ayudante de pruebas, y `test_orders_delivery_audit_trail.py` comprueba
que sus columnas son las de m000: si m000 cambia, esa prueba falla.
"""
from __future__ import annotations


def create_audit_logs_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id            TEXT NOT NULL PRIMARY KEY,
            accion        TEXT NOT NULL,
            modulo        TEXT NOT NULL,
            entidad       TEXT,
            entidad_id    TEXT,
            usuario       TEXT NOT NULL DEFAULT 'Sistema',
            sucursal_id   TEXT,
            valor_antes   TEXT,
            valor_despues TEXT,
            detalles      TEXT,
            ip            TEXT,
            fecha         DATETIME DEFAULT (datetime('now'))
        )
        """
    )
