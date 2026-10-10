import sqlite3
import shutil
from datetime import datetime

db_path = 'instance/attendance.db'

# Backup first
backup_path = f'instance/attendance_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
shutil.copy2(db_path, backup_path)
print(f'Backup created: {backup_path}')

conn = sqlite3.connect(db_path)
c = conn.cursor()

# Migrate: recreate subject table with nullable course_id
c.executescript("""
    PRAGMA foreign_keys=OFF;

    CREATE TABLE subject_migrated (
        id INTEGER NOT NULL,
        name VARCHAR(100) NOT NULL,
        course_id INTEGER,
        study_year VARCHAR(50),
        organization_id INTEGER NOT NULL,
        created_at DATETIME,
        PRIMARY KEY (id),
        FOREIGN KEY(course_id) REFERENCES course (id),
        FOREIGN KEY(organization_id) REFERENCES organization (id)
    );

    INSERT INTO subject_migrated (id, name, course_id, study_year, organization_id, created_at)
    SELECT id, name, course_id, study_year, organization_id, created_at FROM subject;

    DROP TABLE subject;
    ALTER TABLE subject_migrated RENAME TO subject;

    PRAGMA foreign_keys=ON;
""")

conn.commit()

# Verify
c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='subject'")
row = c.fetchone()
print('New subject schema:')
print(row[0])

conn.close()
print('Migration complete! course_id is now nullable.')
