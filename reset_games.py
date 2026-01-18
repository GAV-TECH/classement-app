import sqlite3

DB_PATH = "database.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("DELETE FROM scores")
conn.commit()
conn.close()

print("✅ Tous les scores ont été réinitialisés")

