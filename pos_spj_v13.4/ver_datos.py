import sqlite3 

db = r"C:\Users\Diego Rodriguez\Downloads\pos_spj_v13.4\pos_spj_v13.4\spj_pos_database.db"
tabla = "whatsapp_numeros"

conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

try:
    for row in cur.execute(f"SELECT * FROM {tabla} LIMIT 20"):
        print(dict(row))
except Exception as e:
    print("ERROR:", e)

conn.close()