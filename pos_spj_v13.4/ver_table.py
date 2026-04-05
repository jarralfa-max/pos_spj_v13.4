import sqlite3 

conn = sqlite3.connect("spj_pos_database.db")
cursor = conn.cursor()

tabla = "whatsapp_numeros"

cursor.execute(f"PRAGMA table_info({tabla})")

for col in cursor.fetchall():
    print(col)

conn.close()