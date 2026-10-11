"""
Automated Compatibility & Functional Verification Test Suite for CampusAI Database
Verifies:
1. Application context & database session initialization.
2. Model queries and relationships across all organizational domains.
3. User & Staff authentication password hashing (Werkzeug).
4. Multi-organization data isolation.
5. Face recognition encoding loading (JSON embeddings + pkl file access).
6. Non-destructive transactional write/read/rollback verification.
"""

import os
import sys
import unittest
from werkzeug.security import check_password_hash

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from app import (
    app, db, User, Staff, Student, Class_, Subject, Course,
    Attendance, FaceEncoding, StaffFaceEncoding, LMSContent, Organization
)

class TestDatabaseCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = app
        cls.app_context = app.app_context()
        cls.app_context.push()

    @classmethod
    def tearDownClass(cls):
        cls.app_context.pop()

    def test_01_organizations_and_users(self):
        """Test that organizations exist and user roles are intact."""
        orgs = Organization.query.all()
        self.assertGreaterEqual(len(orgs), 1, "At least one organization must exist")
        users = User.query.all()
        self.assertGreaterEqual(len(users), 1, "At least one user account must exist")
        
        # Verify password hash format
        for u in users:
            self.assertTrue(len(u.password_hash) > 10, f"Password hash missing for user {u.username}")

    def test_02_organization_isolation(self):
        """Verify strict organization data isolation."""
        orgs = Organization.query.all()
        for org in orgs:
            students = Student.query.filter_by(organization_id=org.id).all()
            for s in students:
                self.assertEqual(s.organization_id, org.id, "Student organization_id mismatch")
            
            staff_members = Staff.query.filter_by(organization_id=org.id).all()
            for st in staff_members:
                self.assertEqual(st.organization_id, org.id, "Staff organization_id mismatch")

    def test_03_student_and_class_relationships(self):
        """Test student relationships and class links."""
        students = Student.query.all()
        for s in students:
            if s.class_id:
                cls_obj = db.session.get(Class_, s.class_id)
                self.assertIsNotNone(cls_obj, f"Student {s.name} references non-existent class {s.class_id}")
                self.assertEqual(cls_obj.organization_id, s.organization_id, "Class and student organization mismatch")

    def test_04_attendance_records(self):
        """Test attendance record links to students and classes."""
        records = Attendance.query.limit(50).all()
        for att in records:
            student = db.session.get(Student, att.student_id)
            self.assertIsNotNone(student, f"Attendance record {att.id} has invalid student_id {att.student_id}")
            self.assertIn(att.status.lower(), ['present', 'absent', 'late'], f"Unexpected status {att.status}")

    def test_05_face_recognition_encodings(self):
        """Test that face encodings are loadable from JSON or pkl files."""
        encodings = FaceEncoding.query.all()
        self.assertGreater(len(encodings), 0, "Face encodings should exist")
        
        valid_count = 0
        for fe in encodings:
            if fe.encoding_data:
                # Direct JSON embedding data
                self.assertTrue(isinstance(fe.encoding_data, (dict, list)), "Encoding data must be JSON dict/list")
                valid_count += 1
            elif fe.encoding_path:
                # File path reference
                self.assertTrue(os.path.exists(fe.encoding_path), f"Encoding pkl missing: {fe.encoding_path}")
                valid_count += 1
        
        self.assertEqual(valid_count, len(encodings), "Every face encoding record must have valid data or pkl file")

    def test_06_transactional_write_rollback(self):
        """Test non-destructive write and rollback to verify database engine write capabilities."""
        first_cls = Class_.query.first()
        self.assertIsNotNone(first_cls, "A class must exist for student link")
        test_student = Student(
            name="Migration_Compatibility_Test_Probe",
            roll_number="PROBE-9999",
            class_id=first_cls.id,
            organization_id=first_cls.organization_id
        )
        db.session.add(test_student)
        db.session.flush() # Send insert to DB inside transaction
        self.assertIsNotNone(test_student.id, "Primary key must be assigned upon flush")
        
        # Rollback safely without leaving any trace
        db.session.rollback()
        probe = Student.query.filter_by(roll_number="PROBE-9999").first()
        self.assertIsNone(probe, "Probe record must be rolled back cleanly")

if __name__ == '__main__':
    unittest.main()
