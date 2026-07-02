"""
Migration 073 — temp_purchase_drafts
Persistent cart draft per user+branch.
One active draft per user per branch; JSON blob replaces the global
~/.spj_compra_borrador.json file so drafts survive restarts and are
isolated per operator and location.
"""


def run(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS temp_purchase_drafts (
            id          TEXT PRIMARY KEY,
            usuario     TEXT NOT NULL,
            sucursal_id TEXT NOT NULL,
            draft_data  TEXT NOT NULL,
            updated_at  TEXT DEFAULT (datetime('now')),
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uix_draft_user_branch
            ON temp_purchase_drafts(usuario, sucursal_id)
    """)
    conn.commit()
