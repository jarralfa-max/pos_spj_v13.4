# migrations/standalone/081_wa_queue_backoff.py
"""
Agrega columna proxima_revision a whatsapp_queue para backoff exponencial.
Backoff: 60s * 2^intentos (máx ~16 min).
"""


def run(conn):
    # Agregar columna solo si no existe
    try:
        conn.execute(
            "ALTER TABLE whatsapp_queue ADD COLUMN proxima_revision TEXT")
    except Exception:
        pass  # Ya existe

    # Inicializar proxima_revision = fecha para mensajes pendientes sin valor
    conn.execute("""
        UPDATE whatsapp_queue
        SET proxima_revision = fecha
        WHERE proxima_revision IS NULL AND estado = 'pendiente'
    """)

    # Índice para el worker (evitar full scan en cada ciclo)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_wa_queue_revision
        ON whatsapp_queue(estado, proxima_revision)
    """)

    conn.commit()
