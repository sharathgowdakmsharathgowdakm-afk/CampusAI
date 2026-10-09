import sqlite3
import json
import os
import numpy as np

db_path = os.path.join('instance', 'attendance.db')
print(f"Database: {db_path} ({os.path.getsize(db_path)} bytes)")
conn = sqlite3.connect(db_path)
c = conn.cursor()

# Tables
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print(f"Tables: {tables}")

# Students
c.execute("SELECT id, name, class_id, organization_id FROM student ORDER BY class_id, id")
students = c.fetchall()
print(f"\n--- Students ({len(students)}) ---")
for s in students:
    print(f"  ID={s[0]}, Name={s[1]}, Class={s[2]}, Org={s[3]}")

# Encodings overview
c.execute("SELECT id, student_id, encoding_path, encoding_data FROM face_encoding ORDER BY student_id, id")
encodings = c.fetchall()
print(f"\n--- Face Encodings ({len(encodings)}) ---")
for enc in encodings:
    enc_id, sid, path, data = enc
    dim = "no_data"
    if data:
        try:
            arr = json.loads(data)
            dim = len(arr) if isinstance(arr, list) else "unknown"
        except:
            dim = "parse_error"
    path_info = path if path else "no_path"
    path_exists = os.path.exists(path) if path else False
    print(f"  EncID={enc_id}, StudentID={sid}, Dim={dim}, Path={path_info}, PathExists={path_exists}")

# Detailed look at class 1 encodings
print("\n--- Class-wise Encoding Breakdown ---")
for class_id in [1, 3, 5]:
    c.execute("""
        SELECT s.id, s.name, fe.id as feid, fe.encoding_data, fe.encoding_path
        FROM student s
        LEFT JOIN face_encoding fe ON fe.student_id = s.id
        WHERE s.class_id = ?
        ORDER BY s.id, fe.id
    """, (class_id,))
    rows = c.fetchall()
    print(f"\n  Class {class_id}:")
    for row in rows:
        sid, name, feid, data, path = row
        if feid is None:
            print(f"    Student {sid} ({name}): NO ENCODINGS")
            continue
        if data:
            try:
                arr = json.loads(data)
                vec = np.array(arr)
                dim = len(arr)
                norm = float(np.linalg.norm(vec))
                print(f"    Student {sid} ({name}), EncID={feid}, Dim={dim}, Norm={norm:.4f}, Range=[{vec.min():.4f}, {vec.max():.4f}]")
            except Exception as e:
                print(f"    Student {sid} ({name}), EncID={feid}, PARSE ERROR: {e}")
        elif path and os.path.exists(path):
            import pickle
            with open(path, 'rb') as f:
                arr = pickle.load(f)
            if isinstance(arr, np.ndarray):
                print(f"    Student {sid} ({name}), EncID={feid}, PKL Dim={arr.shape}, Norm={np.linalg.norm(arr):.4f}")
            else:
                print(f"    Student {sid} ({name}), EncID={feid}, PKL type={type(arr)}")
        elif path:
            print(f"    Student {sid} ({name}), EncID={feid}, PATH NOT FOUND: {path}")
        else:
            print(f"    Student {sid} ({name}), EncID={feid}, NO DATA, NO PATH")

conn.close()
