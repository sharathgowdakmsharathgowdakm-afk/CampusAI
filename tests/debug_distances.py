"""Compute intra-student distances to determine the right dlib tolerance."""
import sqlite3
import json
import os
import pickle
import numpy as np

db_path = os.path.join('instance', 'attendance.db')
conn = sqlite3.connect(db_path)
c = conn.cursor()

def load_encoding(enc_id, data_str, path):
    """Load a 128-d encoding from either JSON data or PKL file."""
    if data_str:
        try:
            arr = json.loads(data_str)
            if isinstance(arr, list) and len(arr) == 128:
                return np.array(arr, dtype=np.float64)
        except:
            pass
    if path and os.path.exists(path):
        try:
            with open(path, 'rb') as f:
                arr = pickle.load(f)
            if isinstance(arr, np.ndarray) and arr.shape == (128,):
                return arr.astype(np.float64)
        except:
            pass
    return None

# Load all 128-d encodings per student
c.execute("""
    SELECT s.id, s.name, s.class_id, fe.id, fe.encoding_data, fe.encoding_path
    FROM student s
    JOIN face_encoding fe ON fe.student_id = s.id
    ORDER BY s.id, fe.id
""")
rows = c.fetchall()

student_encs = {}
for sid, name, cid, feid, data, path in rows:
    enc = load_encoding(feid, data, path)
    if enc is not None:
        if sid not in student_encs:
            student_encs[sid] = {'name': name, 'class_id': cid, 'encs': []}
        student_encs[sid]['encs'].append(enc)

print("=== Intra-Student Distance Statistics ===")
print("(Self-consistency: how different are multiple encodings of the SAME person?)\n")

for sid, info in sorted(student_encs.items()):
    encs = info['encs']
    if len(encs) < 2:
        print(f"  Student {sid} ({info['name']}, Class {info['class_id']}): {len(encs)} encoding(s) — skipped")
        continue
    
    dists = []
    for i in range(len(encs)):
        for j in range(i+1, len(encs)):
            d = float(np.linalg.norm(encs[i] - encs[j]))
            dists.append(d)
    
    avg_d = np.mean(dists)
    max_d = np.max(dists)
    min_d = np.min(dists)
    print(f"  Student {sid} ({info['name']}, Class {info['class_id']}): {len(encs)} encodings, "
          f"Intra-dist: avg={avg_d:.4f}, min={min_d:.4f}, max={max_d:.4f}")

# Now compute cross-student distances for Class 1 (first encoding only)
print("\n=== Cross-Student Distances (Class 1, using mean encoding) ===")
class1_students = {sid: info for sid, info in student_encs.items() if info['class_id'] == 1}

# Use mean encoding for each student
class1_mean = {}
for sid, info in sorted(class1_students.items()):
    mean_enc = np.mean(info['encs'], axis=0)
    class1_mean[sid] = (info['name'], mean_enc)

sids = sorted(class1_mean.keys())
for i, sid_a in enumerate(sids[:8]):  # limit to first 8
    for sid_b in sids[i+1:i+9]:
        name_a = class1_mean[sid_a][0]
        name_b = class1_mean[sid_b][0]
        d = float(np.linalg.norm(class1_mean[sid_a][1] - class1_mean[sid_b][1]))
        print(f"  {name_a} (S{sid_a}) vs {name_b} (S{sid_b}): distance={d:.4f}")

conn.close()
