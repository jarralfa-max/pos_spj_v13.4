"""
debug_db_state.py — muestra las tablas existentes en la DB.

Uso:
    python scripts/debug_db_state.py
    python scripts/debug_db_state.py pos_spj.db
    python scripts/debug_db_state.py /tmp/test.db
"""
import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else "spj_pos_database.db"

conn = sqlite3.connect(db_path)
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] for r in cur.fetchall()]
conn.close()

print(f"=== TABLAS en '{db_path}' ===")
for t in tables:
    print(f"  {t}")
print(f"\nTOTAL: {len(tables)} tablas")
