"""
Migration 076 — recepciones: add peso_total_kg column
The column is referenced by _cargar_historial_qr() in recepcion_qr_widget.py
(COALESCE(r.peso_total_kg,0) AS peso_rec) but was never added to recepciones —
it only existed on the paquetes table.
"""


def run(conn):
    try:
        conn.execute(
            "ALTER TABLE recepciones ADD COLUMN peso_total_kg REAL DEFAULT 0"
        )
    except Exception:
        pass  # column already exists
    conn.commit()
