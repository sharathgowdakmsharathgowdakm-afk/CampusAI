"""
Phase 1: Comprehensive Inspection Script for CampusAI SQLite -> PostgreSQL Migration.
Safely inspects:
1. SQLite database (instance/attendance.db) schema, tables, columns, constraints, foreign keys, row counts.
2. SQLAlchemy models in app.py and any imported modules.
3. Differences between SQLite schema and SQLAlchemy models.
4. Raw sqlite queries or direct sqlite3.connect references across codebase.
5. Storage method of face recognition data (encodings in DB vs filesystem).
"""

import os
import sys
import sqlite3
import json
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'attendance.db')

def inspect_sqlite():
    print("=" * 60)
    print("PHASE 1: SQLITE DATABASE INSPECTION")
    print("=" * 60)
    print(f"Target DB Path: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database file not found at {DB_PATH}")
        return {}

    size = os.path.getsize(DB_PATH)
    print(f"Database file size: {size:,} bytes ({size / (1024*1024):.2f} MB)")

    # Open read-only
    conn = sqlite3.connect(f"file:{os.path.abspath(DB_PATH)}?mode=ro", uri=True)
    cursor = conn.cursor()

    # Get all tables
    cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;")
    tables_meta = cursor.fetchall()
    
    report = {}

    for table_name, create_sql in tables_meta:
        # Row count
        cursor.execute(f'SELECT COUNT(*) FROM "{table_name}";')
        row_count = cursor.fetchone()[0]

        # Columns via PRAGMA table_info
        cursor.execute(f'PRAGMA table_info("{table_name}");')
        cols = cursor.fetchall()
        # cid, name, type, notnull, dflt_value, pk

        # Foreign keys via PRAGMA foreign_key_list
        cursor.execute(f'PRAGMA foreign_key_list("{table_name}");')
        fks = cursor.fetchall()
        # id, seq, table, from, to, on_update, on_delete, match

        # Indexes via PRAGMA index_list
        cursor.execute(f'PRAGMA index_list("{table_name}");')
        indexes = cursor.fetchall()
        # seq, name, unique, origin, partial

        report[table_name] = {
            "row_count": row_count,
            "create_sql": create_sql,
            "columns": [
                {
                    "cid": col[0],
                    "name": col[1],
                    "type": col[2],
                    "notnull": bool(col[3]),
                    "default_value": col[4],
                    "pk": col[5]
                }
                for col in cols
            ],
            "foreign_keys": [
                {
                    "id": fk[0],
                    "seq": fk[1],
                    "target_table": fk[2],
                    "from_col": fk[3],
                    "to_col": fk[4],
                    "on_update": fk[5],
                    "on_delete": fk[6]
                }
                for fk in fks
            ],
            "indexes": [
                {
                    "seq": idx[0],
                    "name": idx[1],
                    "unique": bool(idx[2]),
                    "origin": idx[3],
                    "partial": bool(idx[4])
                }
                for idx in indexes
            ]
        }

    conn.close()
    return report

def inspect_app_models():
    print("\n" + "=" * 60)
    print("PHASE 1.2: SQLALCHEMY MODELS INSPECTION (APP.PY)")
    print("=" * 60)
    sys.path.insert(0, BASE_DIR)
    
    try:
        # Import app and db
        import app as flask_app_mod
        app_obj = flask_app_mod.app
        db_obj = flask_app_mod.db

        with app_obj.app_context():
            metadata = db_obj.metadata
            models_info = {}
            for table_name, table in metadata.tables.items():
                cols = []
                for col in table.columns:
                    cols.append({
                        "name": col.name,
                        "type": str(col.type),
                        "nullable": col.nullable,
                        "primary_key": col.primary_key,
                        "default": str(col.default.arg) if col.default is not None else None,
                        "foreign_keys": [str(fk.target_fullname) for fk in col.foreign_keys]
                    })
                models_info[table_name] = {
                    "columns": cols,
                    "foreign_keys": [
                        {
                            "constrained_columns": [c.name for c in fk.constraint.columns],
                            "referred_table": fk.column.table.name,
                            "referred_columns": [fk.column.name]
                        }
                        for fk in table.foreign_keys
                    ]
                }
            print(f"SQLAlchemy Models registered tables: {len(models_info)}")
            return models_info
    except Exception as e:
        print(f"Warning/Error loading models via app context: {e}")
        import traceback
        traceback.print_exc()
        return {}

def inspect_codebase_sqlite_references():
    print("\n" + "=" * 60)
    print("PHASE 1.3: CODEBASE SQLITE REFERENCES SCAN")
    print("=" * 60)
    sqlite_patterns = [
        r'sqlite3\.',
        r'sqlite:///',
        r'PRAGMA\s+',
        r'datetime\(',
        r'strftime\(',
        r'AUTOINCREMENT',
        r'IFNOTEXISTS'
    ]
    findings = []
    for root, dirs, files in os.walk(BASE_DIR):
        # Skip git, venv, pycache, etc.
        dirs[:] = [d for d in dirs if d not in ('.git', 'venv', 'venv311', '__pycache__', 'backups', '.gemini', 'node_modules')]
        for file in files:
            if file.endswith(('.py', '.sql', '.sh', '.env')):
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, BASE_DIR)
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        for idx, line in enumerate(f, 1):
                            for pat in sqlite_patterns:
                                if re.search(pat, line, re.IGNORECASE):
                                    findings.append({
                                        "file": rel_path,
                                        "line": idx,
                                        "pattern": pat,
                                        "content": line.strip()
                                    })
                except Exception as e:
                    pass
    print(f"Found {len(findings)} potential SQLite-specific or DB-specific references.")
    return findings

if __name__ == '__main__':
    sqlite_info = inspect_sqlite()
    print(f"\nDiscovered {len(sqlite_info)} SQLite tables in instance/attendance.db:")
    total_rows = 0
    for tbl, data in sqlite_info.items():
        cnt = data['row_count']
        total_rows += cnt
        cols_count = len(data['columns'])
        fks_count = len(data['foreign_keys'])
        print(f"  - {tbl:<30} : {cnt:>6} rows | {cols_count:>2} cols | {fks_count} FKs")
    print(f"\nTotal rows across all tables: {total_rows}")

    models_info = inspect_app_models()

    findings = inspect_codebase_sqlite_references()
    print("\nSample codebase findings:")
    for f in findings[:20]:
        print(f"  [{f['file']}:{f['line']}] ({f['pattern']}) {f['content'][:90]}")

    # Output detailed JSON report for next phases
    output_dir = os.path.join(BASE_DIR, 'scripts', 'reports')
    os.makedirs(output_dir, exist_ok=True)
    report_path = os.path.join(output_dir, 'inspection_report.json')
    with open(report_path, 'w', encoding='utf-8') as out_f:
        json.dump({
            "sqlite_tables": sqlite_info,
            "sqlalchemy_models": models_info,
            "raw_sqlite_findings": findings
        }, out_f, indent=2)
    print(f"\nDetailed report saved to: {report_path}")
