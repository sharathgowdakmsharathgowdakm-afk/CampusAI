import sqlite3
import os

db_path = os.path.join('instance', 'attendance.db')
print("Checking database at:", os.path.abspath(db_path))

if not os.path.exists(db_path):
    print("Database file does not exist at that path!")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check current table columns
    cursor.execute("PRAGMA table_info(face_encoding)")
    columns = [row[1] for row in cursor.fetchall()]
    print("Columns before migration:", columns)
    
    if 'encoding_data' not in columns:
        print("Adding column encoding_data...")
        try:
            cursor.execute("ALTER TABLE face_encoding ADD COLUMN encoding_data TEXT")
            conn.commit()
            print("Successfully added encoding_data column via sqlite3!")
        except Exception as e:
            print("Error adding column:", e)
    else:
        print("encoding_data column already exists.")
        
    # Check again
    cursor.execute("PRAGMA table_info(face_encoding)")
    columns_after = [row[1] for row in cursor.fetchall()]
    print("Columns after migration:", columns_after)
    
    conn.close()
