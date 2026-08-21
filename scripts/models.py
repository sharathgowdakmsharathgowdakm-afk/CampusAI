from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Float, Date, Time, Boolean
from sqlalchemy.orm import relationship
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# ==================== USER & ORGANIZATION MODELS ====================

class User(db.Model):
    """Admin user for organization"""
    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password = Column(String(200), nullable=False)
    org_type = Column(String(50), nullable=False)  # school, college, institution
    created_at = Column(DateTime, default=datetime.utcnow)
    
    organization = relationship('Organization', uselist=False, backref='user')

class Organization(db.Model):
    """Organization (School/College/Institution)"""
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    type = Column(String(50), nullable=False)  # school, college, institution
    logo = Column(String(300))
    description = Column(Text)
    address = Column(String(300))
    phone = Column(String(20))
    email = Column(String(120))
    created_by = Column(Integer, ForeignKey('user.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    classes = relationship('Class_', backref='organization', lazy=True, cascade='all, delete-orphan')
    students = relationship('Student', backref='organization', lazy=True, cascade='all, delete-orphan')
    attendance = relationship('Attendance', backref='organization', lazy=True, cascade='all, delete-orphan')
    courses = relationship('Course', backref='organization', lazy=True, cascade='all, delete-orphan')
    departments = relationship('Department', backref='organization', lazy=True, cascade='all, delete-orphan')

# ==================== SCHOOL MODELS ====================

class Class_(db.Model):
    """Class/Section"""
    __tablename__ = 'class'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    academic_year = Column(String(20), nullable=False)
    organization_id = Column(Integer, ForeignKey('organization.id'), nullable=False)
    course_id = Column(Integer, ForeignKey('course.id'), nullable=True)
    study_year = Column(String(50), nullable=True)
    branch = Column(String(100), nullable=True)
    semester = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    students = relationship('Student', backref='class_', lazy=True, cascade='all, delete-orphan')
    attendance = relationship('Attendance', backref='class_', lazy=True, cascade='all, delete-orphan')

class Student(db.Model):
    """Student model"""
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    roll_number = Column(String(50), nullable=False)
    phone = Column(String(20), nullable=False)
    email = Column(String(120))
    class_id = Column(Integer, ForeignKey('class.id'), nullable=False)
    organization_id = Column(Integer, ForeignKey('organization.id'), nullable=False)
    password = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    attendance = relationship('Attendance', backref='student', lazy=True, cascade='all, delete-orphan')
    face_encodings = relationship('FaceEncoding', backref='student', lazy=True, cascade='all, delete-orphan')
    subject_attendance = relationship('SubjectAttendance', backref='student', lazy=True, cascade='all, delete-orphan')

class Attendance(db.Model):
    """Attendance record"""
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey('student.id'), nullable=False)
    class_id = Column(Integer, ForeignKey('class.id'), nullable=False)
    organization_id = Column(Integer, ForeignKey('organization.id'), nullable=False)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    status = Column(String(20), default='present')  # present, absent, leave
    day = Column(String(20))  # Monday, Tuesday, etc.
    week = Column(Integer)  # Week number
    month = Column(Integer)  # Month number
    year = Column(Integer)  # Year
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class FaceEncoding(db.Model):
    """Stored face encodings for face recognition"""
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey('student.id'), nullable=False)
    encoding_path = Column(String(300), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# ==================== COLLEGE & INSTITUTION MODELS ====================

class Department(db.Model):
    """Department (for College/Institution)"""
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    organization_id = Column(Integer, ForeignKey('organization.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    courses = relationship('Course', backref='department', lazy=True, cascade='all, delete-orphan')

class Course(db.Model):
    """Course (for College/Institution)"""
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    code = Column(String(50))
    organization_id = Column(Integer, ForeignKey('organization.id'), nullable=False)
    department_id = Column(Integer, ForeignKey('department.id'))
    duration_years = Column(Integer, default=4)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    subjects = relationship('Subject', backref='course', lazy=True, cascade='all, delete-orphan')
    classes = relationship('Class_', backref='course', lazy=True, cascade='all, delete-orphan')
    study_years = relationship('StudyYear', backref='course', lazy=True, cascade='all, delete-orphan')

class StudyYear(db.Model):
    """Study Year (for College/Institution)"""
    __tablename__ = 'study_year'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    course_id = Column(Integer, ForeignKey('course.id'), nullable=False)
    organization_id = Column(Integer, ForeignKey('organization.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Branch(db.Model):
    """Branch (for Institution)"""
    __tablename__ = 'branch'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    course_id = Column(Integer, ForeignKey('course.id'), nullable=False)
    organization_id = Column(Integer, ForeignKey('organization.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Semester(db.Model):
    """Semester (for Institution)"""
    __tablename__ = 'semester'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    course_id = Column(Integer, ForeignKey('course.id'), nullable=False)
    organization_id = Column(Integer, ForeignKey('organization.id'), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Subject(db.Model):
    """Subject (for College/Institution)"""
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    code = Column(String(50))
    course_id = Column(Integer, ForeignKey('course.id'), nullable=False)
    semester = Column(Integer)
    total_classes = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    subject_attendance = relationship('SubjectAttendance', backref='subject', lazy=True, cascade='all, delete-orphan')

class SubjectAttendance(db.Model):
    """Subject-wise attendance"""
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey('student.id'), nullable=False)
    subject_id = Column(Integer, ForeignKey('subject.id'), nullable=False)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    status = Column(String(20), default='present')  # present, absent, leave
    created_at = Column(DateTime, default=datetime.utcnow)

# ==================== UTILITY MODELS ====================

class OTPVerification(db.Model):
    """OTP verification for password reset"""
    id = Column(Integer, primary_key=True)
    email = Column(String(120), unique=True, nullable=False)
    otp = Column(String(6), nullable=False)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class LoginAttempt(db.Model):
    """Track login attempts for security"""
    id = Column(Integer, primary_key=True)
    username = Column(String(100), nullable=False)
    success = Column(Boolean, default=False)
    ip_address = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
