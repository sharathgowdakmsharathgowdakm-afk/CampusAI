"""
Phase 2: Complete and Safe Backup Utility for CampusAI
Uses SQLite's official online backup API (sqlite3.Connection.backup)
Verifies:
1. Destination SQLite backup is queryable.
2. Every table's row count matches the live database exactly.
3. PRAGMA integrity_check passes on the backup.
4. Preserves face_encodings/ and uploads/ file assets into timestamped backup directory.
5. Generates a comprehensive backup manifest.
"""

import os
import sys
import sqlite3
import shutil
import json
import hashlib
from datetime import datetime

# Ensure stdout and stderr handle utf-8 safely on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DB = os.path.join(BASE_DIR, 'instance', 'attendance.db')
BACKUPS_DIR = os.path.join(BASE_DIR, 'backups')

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def perform_backup():
    print("=" * 65)
    print("CAMPUSAI: PHASE 2 DATABASE & ASSETS BACKUP")
    print("=" * 65)

    if not os.path.exists(SRC_DB):
        print(f"FATAL: Source database does not exist at {SRC_DB}")
        sys.exit(1)

    os.makedirs(BACKUPS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # 1. Target backup database path
    dest_db = os.path.join(BACKUPS_DIR, f'attendance_pre_postgresql_migration_{timestamp}.db')
    dest_db_canonical = os.path.join(BACKUPS_DIR, 'attendance_pre_postgresql_migration.db')

    print(f"Source Database: {SRC_DB} ({os.path.getsize(SRC_DB):,} bytes)")
    print(f"Target Backup  : {dest_db}")

    # 2. Use SQLite online backup API
    print("\n[1/4] Running SQLite safe online backup API...")
    try:
        # Open source in read-only mode
        src_conn = sqlite3.connect(f"file:{os.path.abspath(SRC_DB)}?mode=ro", uri=True)
        dest_conn = sqlite3.connect(dest_db)

        # Execute backup
        src_conn.backup(dest_conn, pages=100)
        dest_conn.close()
        src_conn.close()
        print("  [OK] SQLite online backup API completed successfully.")
    except Exception as e:
        print(f"  [FAIL] SQLite backup failed: {e}")
        if os.path.exists(dest_db):
            os.remove(dest_db)
        sys.exit(1)

    # 3. Verify the backup database
    print("\n[2/4] Verifying backup database integrity and records...")
    src_conn = sqlite3.connect(f"file:{os.path.abspath(SRC_DB)}?mode=ro", uri=True)
    bck_conn = sqlite3.connect(f"file:{os.path.abspath(dest_db)}?mode=ro", uri=True)
    src_cur = src_conn.cursor()
    bck_cur = bck_conn.cursor()

    # Integrity check
    bck_cur.execute("PRAGMA integrity_check;")
    integrity = bck_cur.fetchone()[0]
    if integrity != "ok":
        print(f"  [FAIL] Backup failed integrity check: {integrity}")
        sys.exit(1)
    print("  [OK] PRAGMA integrity_check passed: ok")

    # Table comparison
    src_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
    src_tables = [r[0] for r in src_cur.fetchall()]
    bck_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
    bck_tables = [r[0] for r in bck_cur.fetchall()]

    if src_tables != bck_tables:
        print(f"  [FAIL] Table mismatch! Source: {len(src_tables)}, Backup: {len(bck_tables)}")
        sys.exit(1)

    table_manifest = {}
    total_rows = 0
    mismatch = False

    for t in src_tables:
        src_cur.execute(f'SELECT COUNT(*) FROM "{t}";')
        s_cnt = src_cur.fetchone()[0]
        bck_cur.execute(f'SELECT COUNT(*) FROM "{t}";')
        b_cnt = bck_cur.fetchone()[0]

        table_manifest[t] = s_cnt
        total_rows += s_cnt

        if s_cnt != b_cnt:
            print(f"  [FAIL] Row mismatch in '{t}': Source={s_cnt}, Backup={b_cnt}")
            mismatch = True

    src_conn.close()
    bck_conn.close()

    if mismatch:
        print("  [FAIL] Verification failed due to row count mismatches!")
        sys.exit(1)

    print(f"  [OK] All {len(src_tables)} tables verified! Total rows: {total_rows}")

    # Copy to canonical name
    shutil.copy2(dest_db, dest_db_canonical)
    print(f"  [OK] Canonical backup updated: {dest_db_canonical}")

    # 4. Backup file assets (face_encodings and uploads)
    print("\n[3/4] Backing up file-based application assets...")
    assets_backup_dir = os.path.join(BACKUPS_DIR, f'assets_backup_{timestamp}')
    os.makedirs(assets_backup_dir, exist_ok=True)

    fe_src = os.path.join(BASE_DIR, 'face_encodings')
    fe_dest = os.path.join(assets_backup_dir, 'face_encodings')
    if os.path.exists(fe_src):
        shutil.copytree(fe_src, fe_dest, dirs_exist_ok=True)
        num_fe = len([f for r, d, fs in os.walk(fe_dest) for f in fs])
        print(f"  [OK] Copied {num_fe} files from face_encodings/ to {fe_dest}")

    up_src = os.path.join(BASE_DIR, 'uploads')
    up_dest = os.path.join(assets_backup_dir, 'uploads')
    if os.path.exists(up_src):
        shutil.copytree(up_src, up_dest, dirs_exist_ok=True)
        num_up = len([f for r, d, fs in os.walk(up_dest) for f in fs])
        print(f"  [OK] Copied {num_up} files from uploads/ to {up_dest}")

    # 5. Write Manifest
    print("\n[4/4] Writing backup manifest...")
    manifest = {
        "timestamp": timestamp,
        "backup_db_file": os.path.basename(dest_db),
        "backup_canonical_db_file": os.path.basename(dest_db_canonical),
        "db_sha256": file_sha256(dest_db),
        "total_tables": len(src_tables),
        "total_rows": total_rows,
        "tables": table_manifest,
        "assets_backup_dir": os.path.basename(assets_backup_dir),
        "status": "VERIFIED_SUCCESS"
    }

    manifest_path = os.path.join(BACKUPS_DIR, f'backup_manifest_{timestamp}.json')
    with open(manifest_path, 'w', encoding='utf-8') as mf:
        json.dump(manifest, mf, indent=2)

    # Also canonical manifest
    with open(os.path.join(BACKUPS_DIR, 'backup_manifest_latest.json'), 'w', encoding='utf-8') as mf:
        json.dump(manifest, mf, indent=2)

    print(f"  [OK] Backup manifest written to {manifest_path}")
    print("\n" + "=" * 65)
    print("BACKUP COMPLETED & VERIFIED 100% SUCCESSFULLY")
    print("Original instance/attendance.db is completely untouched and preserved.")
    print("=" * 65)

if __name__ == '__main__':
    perform_backup()
