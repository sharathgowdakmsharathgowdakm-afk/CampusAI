from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_talisman import Talisman
from flask_wtf.csrf import CSRFProtect
from flask_jwt_extended import JWTManager
from werkzeug.security import generate_password_hash, check_password_hash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os
import numpy as np
import pickle
import random
try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    face_recognition = None
    FACE_RECOGNITION_AVAILABLE = False

try:
    import face_api
    from face_api import get_pipeline, process_classroom_attendance, register_single_student_face
    FACE_API_AVAILABLE = True
except ImportError:
    face_api = None
    get_pipeline = None
    process_classroom_attendance = None
    register_single_student_face = None
    FACE_API_AVAILABLE = False
from io import BytesIO
import smtplib
from email.message import EmailMessage
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

# India Standard Time (IST)
IST = ZoneInfo("Asia/Kolkata")

def india_now():
    return datetime.now(IST).replace(tzinfo=None)


app = Flask(__name__)
import sys
if __name__ == '__main__':
    sys.modules['app'] = sys.modules[__name__]


secret_key = os.environ.get('SECRET_KEY')
flask_env = os.environ.get('FLASK_ENV', 'development')

if flask_env == 'production':
    if not secret_key or secret_key == 'your-secret-key-here' or len(secret_key) < 32:
        raise ValueError("A strong SECRET_KEY (at least 32 characters) must be set in environment variables for production environments.")
    app.config['SECRET_KEY'] = secret_key
    # Enforce HTTPS and secure headers in production
    Talisman(app, content_security_policy=None)
    app.config['SESSION_COOKIE_SECURE'] = True
else:
    app.config['SECRET_KEY'] = secret_key or 'dev-fallback-secret-key-for-local-testing'
    Talisman(app, content_security_policy=None, force_https=False, session_cookie_secure=False)
    app.config['SESSION_COOKIE_SECURE'] = False

app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['TEMPLATES_AUTO_RELOAD'] = True

csrf = CSRFProtect(app)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["10000 per day", "2000 per hour"],
    storage_uri="memory://"
)

# Support production Postgres, MySQL, or SQLite locally
database_url = os.environ.get('DATABASE_URL', 'sqlite:///attendance.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
elif database_url.startswith("mysql://"):
    database_url = database_url.replace("mysql://", "mysql+pymysql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
app.config['JWT_SECRET_KEY'] = secret_key or 'jwt-secret-key-fallback'

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db = SQLAlchemy(app)
jwt = JWTManager(app)

from routes.api import api_bp
from routes.campus import campus_bp
from routes.campus_api import campus_api_bp

app.register_blueprint(api_bp)
app.register_blueprint(campus_bp)
app.register_blueprint(campus_api_bp)
csrf.exempt(api_bp)
csrf.exempt(campus_api_bp)
csrf.exempt(campus_bp)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('face_encodings', exist_ok=True)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    org_type = db.Column(db.String(20), nullable=False)  # school, college, institution
    role = db.Column(db.String(50), default='admin')
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Organization(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # school, college, institution
    logo_path = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    users = db.relationship('User', backref='organization', lazy=True)
    classes = db.relationship('Class_', backref='organization', lazy=True)
    students = db.relationship('Student', backref='organization', lazy=True)
    courses = db.relationship('Course', backref='organization', lazy=True)
    grading_schemes = db.relationship('GradingScheme', backref='organization', lazy=True)

# Grading scheme models
class GradingScheme(db.Model):
    __tablename__ = 'grading_scheme'
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    max_marks = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    ranges = db.relationship('GradeRange', backref='scheme', cascade='all, delete-orphan', lazy=True)

class GradeRange(db.Model):
    __tablename__ = 'grade_range'
    id = db.Column(db.Integer, primary_key=True)
    scheme_id = db.Column(db.Integer, db.ForeignKey('grading_scheme.id'), nullable=False)
    grade = db.Column(db.String(5), nullable=False)          # e.g., 'A+', 'A', 'B+'
    grade_point = db.Column(db.Integer, nullable=False)     # 5,4,3,2,1
    min_pct = db.Column(db.Float, nullable=False)           # inclusive lower bound
    max_pct = db.Column(db.Float, nullable=False)           # inclusive upper bound
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Course(db.Model):
    __tablename__ = 'course'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    classes = db.relationship('Class_', backref='course', lazy=True)
    subjects = db.relationship('Subject', backref='course', lazy=True)
    study_years = db.relationship('StudyYear', backref='course', lazy=True)

class StudyYear(db.Model):
    __tablename__ = 'study_year'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Branch(db.Model):
    __tablename__ = 'branch'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Semester(db.Model):
    __tablename__ = 'semester'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Subject(db.Model):
    __tablename__ = 'subject'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    study_year = db.Column(db.String(50))
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Class_(db.Model):
    __tablename__ = 'class'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    academic_year = db.Column(db.String(20), nullable=False)
    study_year = db.Column(db.String(50), nullable=True)
    branch = db.Column(db.String(100), nullable=True)
    semester = db.Column(db.String(100), nullable=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=True)
    class_teacher = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    students = db.relationship('Student', backref='class_', lazy=True)
    attendances = db.relationship('Attendance', backref='class_', lazy=True)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(80), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    roll_number = db.Column(db.String(20), nullable=False)
    phone = db.Column(db.String(15))
    password = db.Column(db.String(200))
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    attendances = db.relationship('Attendance', backref='student', lazy=True)
    face_encodings = db.relationship('FaceEncoding', backref='student', lazy=True)

    @property
    def face_encodings_count(self):
        """Returns the count of registered face encodings for this student."""
        return len(self.face_encodings) if self.face_encodings else 0

    @property
    def has_registered_face(self):
        """True if the student has at least one registered face encoding."""
        return self.face_encodings_count > 0

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=True)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    _status = db.Column('status', db.String(10), nullable=False)  # present, absent
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    subject = db.relationship('Subject', backref='attendances', lazy=True)
    
    @property
    def status(self):
        # Return stored status directly; time-based overrides removed
        return self._status

    @status.setter
    def status(self, value):
        self._status = value

    @property
    def day(self):
        return self.date.strftime('%A')

class FaceEncoding(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    encoding_path = db.Column(db.String(200), nullable=True)
    encoding_data = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Staff(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    org_email = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), default='staff')  # admin, hod, staff
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    organization = db.relationship('Organization', backref='staffs', lazy=True)
    face_encodings = db.relationship('StaffFaceEncoding', backref='staff', lazy=True, cascade='all, delete-orphan')
    attendances = db.relationship('StaffAttendance', backref='staff', lazy=True, cascade='all, delete-orphan')

class StaffFaceEncoding(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    encoding_path = db.Column(db.String(200), nullable=True)
    encoding_data = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class StaffAttendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='present')  # present, late
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    location_name = db.Column(db.String(255), nullable=True)
    accuracy_meters = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    organization = db.relationship('Organization', backref=db.backref('staff_attendances', lazy=True))

    @property
    def day(self):
        return self.date.strftime('%A')

    @property
    def timestamp(self):
        return self.created_at or datetime.utcnow()

    @property
    def accuracy(self):
        return self.accuracy_meters

    @property
    def location_label(self):
        return self.location_name

class OTPVerification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    otp = db.Column(db.String(6), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# ============================================================
# NEW CAMPUS PLATFORM MODELS (non-breaking additions)
# ============================================================

class Assignment(db.Model):
    __tablename__ = 'assignment'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    deadline = db.Column(db.DateTime)
    file_path = db.Column(db.String(300))
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=True)
    max_marks = db.Column(db.Float, default=100.0)
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    submissions = db.relationship('AssignmentSubmission', backref='assignment', lazy=True)

class AssignmentSubmission(db.Model):
    __tablename__ = 'assignment_submission'
    id = db.Column(db.Integer, primary_key=True)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignment.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    file_path = db.Column(db.String(300))
    text_content = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    marks = db.Column(db.Float)
    feedback = db.Column(db.Text)
    status = db.Column(db.String(20), default='submitted')  # submitted, graded, late
    student = db.relationship('Student', backref='submissions', lazy=True)

class Timetable(db.Model):
    __tablename__ = 'timetable'
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=True)
    subject_name = db.Column(db.String(100))
    day_of_week = db.Column(db.String(10), nullable=False)  # Monday, Tuesday, etc.
    start_time = db.Column(db.String(10), nullable=False)  # HH:MM
    end_time = db.Column(db.String(10), nullable=False)
    room = db.Column(db.String(50))
    faculty = db.Column(db.String(100))
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Exam(db.Model):
    __tablename__ = 'exam'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    exam_type = db.Column(db.String(50), default='internal')  # internal, semester, unit_test
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=True)
    subject_name = db.Column(db.String(100))
    date = db.Column(db.Date)
    max_marks = db.Column(db.Float, default=100.0)
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    marks = db.relationship('InternalMark', backref='exam', lazy=True)

class InternalMark(db.Model):
    __tablename__ = 'internal_mark'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), nullable=False)
    marks_obtained = db.Column(db.Float)
    grade = db.Column(db.String(5))
    remarks = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    student = db.relationship('Student', backref='marks', lazy=True)

class Notification(db.Model):
    __tablename__ = 'notification'
    id = db.Column(db.Integer, primary_key=True)
    org_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    user_type = db.Column(db.String(20))  # student, staff, parent, all
    user_id = db.Column(db.Integer)  # specific user, or null for broadcast
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notif_type = db.Column(db.String(50), default='info')  # info, warning, danger, success
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class LMSContent(db.Model):
    __tablename__ = 'lms_content'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    content_type = db.Column(db.String(20), nullable=False)  # video, pdf, ppt, link, recorded
    file_path = db.Column(db.String(300))
    external_url = db.Column(db.String(500))
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    duration = db.Column(db.String(20))  # e.g. 45:00
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Quiz(db.Model):
    __tablename__ = 'quiz'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    questions_json = db.Column(db.Text)  # JSON string of questions
    duration_minutes = db.Column(db.Integer, default=30)
    max_marks = db.Column(db.Float, default=10.0)
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    quiz_submissions = db.relationship('QuizSubmission', backref='quiz', lazy=True)

class QuizSubmission(db.Model):
    __tablename__ = 'quiz_submission'
    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quiz.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    answers_json = db.Column(db.Text)
    score = db.Column(db.Float)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

class Parent(db.Model):
    __tablename__ = 'parent'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(200), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    student = db.relationship('Student', backref='parent', uselist=False, lazy=True)

class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    user_type = db.Column(db.String(20))  # admin, staff, student, parent
    username = db.Column(db.String(100))
    action = db.Column(db.String(200), nullable=False)
    ip_address = db.Column(db.String(50))
    org_id = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class ChatMessage(db.Model):
    __tablename__ = 'chat_message'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # user, bot
    message = db.Column(db.Text, nullable=False)
    org_id = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class AcademicEvent(db.Model):
    __tablename__ = 'academic_event'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    event_type = db.Column(db.String(50), default='Academic')  # Academic, Examination, Holiday, Co-Curricular, Meeting, Other
    status = db.Column(db.String(50), default='Upcoming')     # Upcoming, Ongoing, Completed
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=True)
    study_year = db.Column(db.String(50), nullable=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FeeStructure(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=True) 
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=True)
    fee_type = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    due_date = db.Column(db.Date, nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class LeaveApplication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=True)
    staff_id = db.Column(db.Integer, db.ForeignKey('staff.id'), nullable=True)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='Pending') # Pending, Approved, Rejected
    applied_on = db.Column(db.DateTime, default=datetime.utcnow)
    
    student = db.relationship('Student', backref=db.backref('leave_applications', lazy=True))
    staff = db.relationship('Staff', backref=db.backref('leave_applications', lazy=True))


# Template Filters
@app.template_filter('strftime')
def _jinja2_filter_datetime(date, fmt='%Y-%m-%d'):
    if not date:
        return ''
    if date == 'now':
        date = india_now()
    try:
        return date.strftime(fmt)
    except Exception:
        return ''

# Decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session and 'staff_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def staff_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_staff') or not session.get('staff_id'):
            flash('Please log in as staff to access this page.', 'danger')
            return redirect(url_for('staff_login'))
        return f(*args, **kwargs)
    return decorated_function

def org_required(org_types):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'org_type' not in session or session['org_type'] not in org_types:
                flash('Unauthorized access', 'danger')
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Routes
@app.route('/')
def splash():
    return render_template('splash.html')

@app.route('/uploads/<path:filename>')
def serve_uploads(filename):
    filename = filename.replace('\\', '/')

    # Check the current app uploads folder first
    app_uploads = os.path.abspath(app.config['UPLOAD_FOLDER'])
    requested_file = os.path.join(app_uploads, filename)

    if os.path.isfile(requested_file):
        return send_from_directory(app_uploads, filename)

    # Also support older files stored outside the CampusAI folder
    parent_uploads = os.path.abspath(
        os.path.join(app.root_path, '..', 'uploads')
    )
    requested_file = os.path.join(parent_uploads, filename)

    if os.path.isfile(requested_file):
        return send_from_directory(parent_uploads, filename)

    return "File not found", 404

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if request.method == 'POST':
        org_type = request.form.get('org_type')
        username = (request.form.get('username') or '').strip()
        password = (request.form.get('password') or '').strip()
        role = (request.form.get('role') or 'admin').strip().lower()

        if not all([org_type, username, password]):
            flash('All fields are required', 'danger')
            return redirect(url_for('login'))

        # Enforce that HOD is ONLY for college and institution
        if role == 'hod' and org_type not in ['college', 'institution']:
            flash('HOD role is only available for College and Institutions.', 'warning')
            return redirect(url_for('login'))

        # Authentication based on role
        if role == 'hod':
            # Check Staff table for HOD
            staff = Staff.query.join(Organization).filter(
                (Organization.type == org_type) &
                ((Staff.email == username) | (Staff.phone == username) | (Staff.name == username))
            ).first()
            if not staff:
                staff = Staff.query.filter(
                    (Staff.email == username) | (Staff.phone == username) | (Staff.name == username)
                ).first()

            if staff and check_password_hash(staff.password_hash, password):
                if staff.organization.type not in ['college', 'institution']:
                    flash('HOD role is only available for College and Institutions.', 'warning')
                    return redirect(url_for('login'))
                session.clear()
                session['staff_id'] = staff.id
                session['user_id'] = staff.id
                session['username'] = staff.name
                session['org_type'] = staff.organization.type
                session['org_id'] = staff.organization_id
                session['org_name'] = staff.organization.name
                session['role'] = 'hod'
                session['is_staff'] = True
                session['is_hod'] = True
                if getattr(staff, 'role', None) != 'hod':
                    staff.role = 'hod'
                    db.session.commit()
                flash(f'Welcome back, HOD {staff.name}!', 'success')
                if staff.organization.type == 'college':
                    return redirect(url_for('college_dashboard'))
                elif staff.organization.type == 'institution':
                    return redirect(url_for('institution_dashboard'))
                return redirect(url_for('staff_dashboard'))
            else:
                flash('Invalid credentials for HOD login.', 'danger')
                return redirect(url_for('login'))

        elif role == 'staff':
            # Check Staff table
            staff = Staff.query.join(Organization).filter(
                (Organization.type == org_type) &
                ((Staff.email == username) | (Staff.phone == username) | (Staff.name == username))
            ).first()
            if not staff:
                staff = Staff.query.filter(
                    (Staff.email == username) | (Staff.phone == username) | (Staff.name == username)
                ).first()

            if staff and check_password_hash(staff.password_hash, password):
                session.clear()
                session['staff_id'] = staff.id
                session['username'] = staff.name
                session['org_type'] = staff.organization.type
                session['org_id'] = staff.organization_id
                session['org_name'] = staff.organization.name
                session['role'] = 'staff'
                session['is_staff'] = True
                flash(f'Welcome, {staff.name}!', 'success')
                return redirect(url_for('staff_dashboard'))
            else:
                flash('Invalid credentials for Staff login.', 'danger')
                return redirect(url_for('login'))

        else:  # Admin login (default)
            user = User.query.filter_by(username=username, org_type=org_type).first()
            if not user:
                user = User.query.filter_by(email=username, org_type=org_type).first()
            if not user:
                user = User.query.filter((User.username == username) | (User.email == username)).first()

            if user and check_password_hash(user.password_hash, password):
                session.clear()
                session['user_id'] = user.id
                session['username'] = user.username
                session['org_type'] = user.org_type
                session['org_id'] = user.organization_id
                session['org_name'] = user.organization.name
                session['role'] = 'admin'
                session['is_admin'] = True
                flash(f'Welcome, Administrator {user.username}!', 'success')
                return redirect(url_for('campus.assistant'))

            # Fallback: check if staff with role 'admin'
            staff = Staff.query.filter((Staff.email == username) | (Staff.phone == username)).first()
            if staff and check_password_hash(staff.password_hash, password) and getattr(staff, 'role', None) == 'admin':
                session.clear()
                session['staff_id'] = staff.id
                session['user_id'] = staff.id
                session['username'] = staff.name
                session['org_type'] = staff.organization.type
                session['org_id'] = staff.organization_id
                session['org_name'] = staff.organization.name
                session['role'] = 'admin'
                session['is_staff'] = True
                session['is_admin'] = True
                flash(f'Welcome, Admin {staff.name}!', 'success')
                return redirect(url_for('campus.assistant'))

            flash('Invalid credentials', 'danger')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        org_name = request.form.get('org_name')
        org_type = request.form.get('org_type')
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        if not all([org_name, org_type, username, email, password]):
            flash('All fields are required', 'danger')
            return redirect(url_for('register'))

        # Create organization
        org = Organization(name=org_name, type=org_type)
        db.session.add(org)
        db.session.commit()

        # Create user
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            org_type=org_type,
            organization_id=org.id
        )
        db.session.add(user)
        db.session.commit()

        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

# School Routes
@app.route('/school/dashboard')
@org_required(['school'])
def school_dashboard():
    org_id = session.get('org_id')
    classes = Class_.query.filter_by(organization_id=org_id).all()
    total_classes = len(classes)
    total_students = Student.query.filter_by(organization_id=org_id).count()
    today_attendance = Attendance.query.filter_by(date=india_now().date()).join(Student).filter_by(organization_id=org_id).count()

    return render_template('school/dashboard.html',
                         classes=classes,
                         total_classes=total_classes,
                         total_students=total_students,
                         today_attendance=today_attendance)

@app.route('/school/academic-calendar', methods=['GET', 'POST'])
@org_required(['school'])
def school_academic_calendar():
    org_id = session.get('org_id')
    if request.method == 'POST':
        title = request.form.get('title')
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        event_type = request.form.get('event_type', 'Academic')
        status = request.form.get('status', 'Upcoming')
        description = request.form.get('description', '')

        if not title or not start_date_str:
            flash('Event title and start date are required.', 'danger')
            return redirect(url_for('school_academic_calendar'))

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
            new_event = AcademicEvent(
                title=title,
                description=description,
                start_date=start_date,
                end_date=end_date,
                event_type=event_type,
                status=status,
                organization_id=org_id
            )
            db.session.add(new_event)
            db.session.commit()
            flash('Academic event added successfully!', 'success')
        except Exception as e:
            flash(f'Error saving event: {str(e)}', 'danger')
        return redirect(url_for('school_academic_calendar'))

    events = AcademicEvent.query.filter_by(organization_id=org_id).order_by(AcademicEvent.start_date.asc()).all()
    return render_template('academic_calendar.html', events=events, org_type='school')

@app.route('/school/academic-calendar/delete/<int:event_id>', methods=['POST', 'GET'])
@org_required(['school'])
def school_delete_academic_event(event_id):
    org_id = session.get('org_id')
    event = AcademicEvent.query.filter_by(id=event_id, organization_id=org_id).first_or_404()
    db.session.delete(event)
    db.session.commit()
    flash('Event deleted successfully.', 'success')
    return redirect(url_for('school_academic_calendar'))



# Analytics Endpoint for Dashboards
@app.route('/analytics-data')
def analytics_data():
    if 'org_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    org_id = session['org_id']
    
    # Last 7 days attendance trend
    today = india_now().date()
    labels = []
    data = []
    
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        count = Attendance.query.join(Student).filter(
            Student.organization_id == org_id,
            Attendance.date == d,
            Attendance._status == 'present'
        ).count()
        labels.append(d.strftime('%a'))
        data.append(count)
        
    return jsonify({
        'labels': labels,
        'attendance_data': data
    })

# SMS/Email Notification Placeholder
@app.route('/notify-absentees', methods=['POST'])
def notify_absentees():
    if 'org_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
        
    data = request.get_json()
    class_id = data.get('class_id')
    date_str = data.get('date')
    
    # Mock SMS/Email dispatch logic (e.g., Twilio / SendGrid)
    # students = Student.query.filter_by(class_id=class_id).all()
    # absentees = [s for s in students if not Attendance.query.filter_by(student_id=s.id, date=date_obj).first()]
    # for a in absentees:
    #     send_sms(a.phone, f"Your ward {a.name} is absent today.")
    
    return jsonify({'success': 'Notifications sent successfully (Simulated)'}), 200

@app.route('/school/classes')
@org_required(['school'])
def school_classes():
    classes = Class_.query.filter_by(organization_id=session.get('org_id')).all()
    for c in classes:
        c.student_count = len(c.students)
    return render_template('school/classes.html', classes=classes)

@app.route('/school/add-class', methods=['GET', 'POST'])
@org_required(['school'])
def school_add_class():
    if request.method == 'POST':
        class_name = request.form.get('class_name')
        academic_year = request.form.get('academic_year')
        class_teacher = request.form.get('class_teacher')

        if not all([class_name, academic_year]):
            flash('All fields are required', 'danger')
            return redirect(url_for('school_add_class'))

        class_ = Class_(
            name=class_name,
            academic_year=academic_year,
            class_teacher=class_teacher,
            organization_id=session.get('org_id')
        )
        db.session.add(class_)
        db.session.commit()

        flash('Class added successfully!', 'success')
        return redirect(url_for('school_dashboard'))

    return render_template('school/add_class.html')

@app.route('/school/add-student', methods=['GET', 'POST'])
@org_required(['school'])
def school_add_student():
    classes = Class_.query.filter_by(organization_id=session.get('org_id')).all()

    if request.method == 'POST':
        name = request.form.get('name')
        roll_number = request.form.get('roll_number')
        phone = request.form.get('phone')
        class_id = request.form.get('class_id')

        if not all([name, roll_number, class_id]):
            flash('Name, roll number and class are required', 'danger')
            return redirect(url_for('school_add_student'))

        student = Student(
            name=name,
            roll_number=roll_number,
            phone=phone,
            organization_id=session.get('org_id'),
            class_id=int(class_id)
        )
        db.session.add(student)
        db.session.commit()

        flash('Student added successfully!', 'success')
        return redirect(url_for('school_dashboard'))

    return render_template('school/add_student.html', classes=classes)

# --- Face Registration API (session-auth, JSON) ---
@app.route('/school/api/student/<int:student_id>/face-status')
@org_required(['school'])
def school_api_face_status(student_id):
    """Return whether the student already has face encodings stored."""
    count = FaceEncoding.query.filter_by(student_id=student_id).count()
    return jsonify({'has_face': count > 0, 'encoding_count': count})



# ─────────────────────────────────────────────────────────────────────────────
# LEGACY DLIB ATTENDANCE (fallback when onnxruntime / face_api not available)
# Uses face_recognition (dlib HOG + 128-d encoding) for PythonAnywhere compat.
# ─────────────────────────────────────────────────────────────────────────────

def legacy_process_classroom_attendance(image_path, db_session, organization_id,
                                        class_id, subject_id=None, detection_range="50m", student_count=0, **kwargs):
    """
    Fallback attendance engine using face_recognition (dlib 128-d HOG).
    Returns the exact dict format expected by mark_attendance.js.
    Used when onnxruntime / SCRFD+ArcFace engine is unavailable (e.g. on PythonAnywhere).
    """
    import time
    t_start = time.perf_counter()
    today = india_now().date()
    now_dt = india_now()

    # Load all 128-d encodings for students in this class / org
    students = Student.query.filter_by(
        class_id=int(class_id), organization_id=int(organization_id)
    ).all()
    student_map = {s.id: s for s in students}

    known_encodings = []  # list of np.array (128,)
    known_student_ids = []  # parallel list of student_id

    for student in students:
        enc_records = FaceEncoding.query.filter_by(student_id=student.id).all()
        for rec in enc_records:
            enc_data = rec.encoding_data
            if enc_data and isinstance(enc_data, list) and len(enc_data) == 128:
                known_encodings.append(np.array(enc_data, dtype=np.float64))
                known_student_ids.append(student.id)
            elif rec.encoding_path and os.path.exists(rec.encoding_path):
                try:
                    with open(rec.encoding_path, 'rb') as pf:
                        loaded = pickle.load(pf)
                    if isinstance(loaded, np.ndarray) and loaded.shape == (128,):
                        known_encodings.append(loaded.astype(np.float64))
                        known_student_ids.append(student.id)
                except Exception:
                    pass

    if not known_encodings:
        return {
            'error': 'No registered face encodings found for this class. Please register students\' faces first.',
            'faces_detected': 0,
            'recognized': [],
            'recognized_count': 0,
            'unknown_faces': 0,
            'rejected_faces': [],
            'rejected_count': 0,
            'duplicate_removed': 0,
            'attendance_marked': 0,
            'detection_range': detection_range,
            'distance_meters': 50,
            'annotated_image': None,
            'stats': {'total_faces': 0, 'recognized': 0, 'unrecognized': 0},
            'engine': 'legacy_dlib',
            'timings': {'total_sec': round(time.perf_counter() - t_start, 2)}
        }

    if not FACE_RECOGNITION_AVAILABLE:
        return {
            'error': 'Face recognition library (face_recognition / dlib) is not installed on this server.',
            'faces_detected': 0,
            'recognized': [],
            'recognized_count': 0,
            'unknown_faces': 0,
            'rejected_faces': [],
            'rejected_count': 0,
            'duplicate_removed': 0,
            'attendance_marked': 0,
            'detection_range': detection_range,
            'distance_meters': 50,
            'annotated_image': None,
            'stats': {'total_faces': 0, 'recognized': 0, 'unrecognized': 0},
            'engine': 'none',
            'timings': {'total_sec': round(time.perf_counter() - t_start, 2)}
        }

    # Detect faces in classroom image
    try:
        img = face_recognition.load_image_file(image_path)
        # number_of_times_to_upsample=1 (default) or 2 (for smaller faces in groups)
        # We use 1 to keep it consistent with registration crops.
        face_locations = face_recognition.face_locations(img, model='hog')
        face_encs = face_recognition.face_encodings(img, face_locations)
    except Exception as e:
        return {
            'error': f'Image processing failed: {str(e)}',
            'faces_detected': 0,
            'recognized': [],
            'recognized_count': 0,
            'unknown_faces': 0,
            'rejected_faces': [],
            'rejected_count': 0,
            'duplicate_removed': 0,
            'attendance_marked': 0,
            'detection_range': detection_range,
            'distance_meters': 50,
            'annotated_image': None,
            'stats': {'total_faces': 0, 'recognized': 0, 'unrecognized': 0},
            'engine': 'legacy_dlib',
            'timings': {'total_sec': round(time.perf_counter() - t_start, 2)}
        }

    tolerance = 0.48  # Compatible with existing num_jitters=1 registrations
    candidate_matches = []

    for f_idx, face_enc in enumerate(face_encs):
        distances = face_recognition.face_distance(known_encodings, face_enc)
        if len(distances) == 0:
            continue
        best_idx = int(np.argmin(distances))
        best_dist = float(distances[best_idx])
        if best_dist <= tolerance:
            candidate_matches.append((best_dist, f_idx, known_student_ids[best_idx]))

    # Sort candidates by best distance ascending (closest, highest-confidence match first)
    candidate_matches.sort(key=lambda x: x[0])

    assigned_students = set()
    face_to_student = {}  # f_idx -> (student_id, best_dist)

    for best_dist, f_idx, student_id in candidate_matches:
        if student_id not in assigned_students and f_idx not in face_to_student:
            assigned_students.add(student_id)
            face_to_student[f_idx] = (student_id, best_dist)

    recognized = []

    for f_idx, (student_id, best_dist) in face_to_student.items():
        student = student_map.get(student_id)
        if not student:
            continue

        # Write attendance record
        existing = Attendance.query.filter_by(
            student_id=student_id,
            class_id=int(class_id),
            date=today
        ).first()
        if not existing:
            att = Attendance(
                student_id=student_id,
                class_id=int(class_id),
                subject_id=subject_id,
                date=today,
                time=now_dt.time(),
                status='present'
            )
            db_session.add(att)
            status_str = 'present'
        else:
            status_str = 'already present' if existing.status == 'present' else existing.status

        confidence_pct = round(max(0.0, (1.0 - best_dist)) * 100, 1)
        recognized.append({
            'student_id': student_id,
            'name': student.name,
            'roll_number': getattr(student, 'roll_number', ''),
            'status': status_str,
            'confidence': confidence_pct,
            'similarity': round(1.0 - best_dist, 3),
            'distance': round(best_dist, 4),
            'model_type': 'dlib_128d',
            'engine': 'legacy_dlib'
        })

    try:
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        print(f"[LEGACY ATT] DB commit error: {e}")

    # Generate annotated image with bounding boxes
    annotated_b64 = None
    try:
        import cv2
        import base64
        # img is RGB from face_recognition.load_image_file
        annotated_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        h, w = annotated_bgr.shape[:2]
        base_dim = max(h, w)
        font_scale = max(0.4, min(0.85, base_dim / 1400.0))
        line_thick = max(1, int(round(base_dim / 600.0)))

        for f_idx, (top, right, bottom, left) in enumerate(face_locations):
            if f_idx in face_to_student:
                s_id, dist = face_to_student[f_idx]
                student = student_map.get(s_id)
                s_name = student.name if student else f"Student #{s_id}"
                conf = round(max(0.0, (1.0 - dist)) * 100, 1)
                color = (46, 204, 113)  # Bright Green in BGR
                badge_color = (39, 174, 96)
                label = f"{s_name} ({conf}%)"
            else:
                color = (0, 165, 255)  # Orange in BGR
                badge_color = (0, 140, 230)
                label = "? Unknown"

            cv2.rectangle(annotated_bgr, (left, top), (right, bottom), color, line_thick)
            t_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)[0]
            badge_y1 = max(0, top - t_size[1] - 8)
            cv2.rectangle(annotated_bgr, (left, badge_y1), (left + t_size[0] + 10, top), badge_color, -1)
            cv2.putText(annotated_bgr, label, (left + 5, top - 4), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1, cv2.LINE_AA)

        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 88]
        _, buf = cv2.imencode('.jpg', annotated_bgr, encode_param)
        annotated_b64 = f"data:image/jpeg;base64,{base64.b64encode(buf).decode('utf-8')}"
    except Exception as e:
        print(f"[LEGACY ATT] Annotation error: {e}")

    total_faces = len(face_locations)
    unknown_faces = max(0, total_faces - len(recognized))
    total_time = round(time.perf_counter() - t_start, 2)

    return {
        'success': f'Attendance marked for {len(recognized)} students',
        'faces_detected': total_faces,
        'recognized': recognized,
        'recognized_count': len(recognized),
        'unknown_faces': unknown_faces,
        'rejected_faces': [],
        'rejected_count': 0,
        'duplicate_removed': max(0, len(candidate_matches) - len(assigned_students)),
        'attendance_marked': len(recognized),
        'detection_range': detection_range,
        'distance_meters': 50,
        'annotated_image': annotated_b64,
        'stats': {
            'total_faces': total_faces,
            'recognized': len(recognized),
            'unrecognized': unknown_faces
        },
        'engine': 'legacy_dlib',
        'timings': {
            'total_sec': total_time
        }
    }


def legacy_process_student_face_registration(student_id, organization_id, images_b64=None, files=None):
    """
    Fallback Student Face Registration using face_recognition (dlib 128-d).
    Active on environments without onnxruntime / SCRFD+ArcFace.
    """
    if not FACE_RECOGNITION_AVAILABLE:
        return {'success': False, 'error': 'Face recognition library is not installed on this server.'}, 503

    if not student_id:
        return {'success': False, 'error': 'Student not selected'}, 400

    student = db.session.get(Student, int(student_id))
    if not student:
        return {'success': False, 'error': 'Student not found'}, 404

    if student.organization_id != int(organization_id):
        return {'success': False, 'error': 'Unauthorized: Student does not belong to active organization'}, 403

    import io
    from PIL import Image

    images_to_process = []
    if images_b64:
        import base64
        for b64 in images_b64:
            if b64:
                try:
                    if ',' in b64:
                        b64 = b64.split(',', 1)[1]
                    raw = base64.b64decode(b64)
                    images_to_process.append(raw)
                except Exception:
                    pass

    if files:
        for f in files:
            if f and f.filename != '':
                if allowed_file(f.filename):
                    content = f.read()
                    if content:
                        images_to_process.append(content)

    if not images_to_process:
        return {'success': False, 'error': 'No facial image provided. Please capture or upload a photo.'}, 400

    success_count = 0
    errors = []

    for idx, raw_bytes in enumerate(images_to_process[:5]):
        try:
            pil_img = Image.open(io.BytesIO(raw_bytes)).convert('RGB')
            np_img = np.array(pil_img)
            # Try HOG (fast, always available); CNN would need extra model not present
            locations = face_recognition.face_locations(np_img, model='hog')

            if len(locations) == 0:
                errors.append(f"Image {idx+1}: No usable face detected. Please upload a clearer, well-lit photo.")
                continue

            if len(locations) > 1:
                errors.append(f"Image {idx+1}: Multiple faces detected. Please upload a photo with only this student.")
                continue

            # num_jitters=3: average 3 perturbed versions for robustness without timeout
            # (num_jitters=10 would exceed PythonAnywhere's 30s request limit for 5 photos)
            encs = face_recognition.face_encodings(np_img, locations, num_jitters=3)
            if not encs:
                errors.append(f"Image {idx+1}: Could not compute face encoding.")
                continue

            record = FaceEncoding(
                student_id=student.id,
                encoding_path="",
                encoding_data=encs[0].tolist(),
                created_at=datetime.utcnow()
            )
            db.session.add(record)
            success_count += 1
        except Exception as e:
            errors.append(f"Image {idx+1}: {str(e)}")

    if success_count > 0:
        try:
            db.session.commit()
            return {
                'success': True,
                'message': f"Successfully registered {success_count} face sample(s) for {student.name}."
            }, 200  # Always return (dict, code) tuple so routes can unpack correctly
        except Exception as e:
            db.session.rollback()
            return {'success': False, 'error': f"Database error: {str(e)}"}, 500
    else:
        err_msg = "; ".join(errors) if errors else "Face registration failed."
        return {'success': False, 'error': err_msg}, 400


def process_student_face_registration(student_id, organization_id, images_b64=None, files=None):
    """
    Unified Student Face Registration using SCRFD (detection) + Face Quality Filter + ArcFace (512-d embedding).
    Enforces requirements:
    - Exactly one usable face per image
    - Rejects multiple faces: "Multiple faces detected. Please upload an image containing only this student."
    - Rejects 0 faces: "No usable face detected. Please upload a clearer image."
    - Rejects low quality: "Face quality check failed: [reason]. Please upload a clearer image."
    - Saves 512-d normalized ArcFace embedding to FaceEncoding table
    - Scoped strictly to student and organization
    - Invalidates organization embedding cache
    """
    if not FACE_API_AVAILABLE:
        return legacy_process_student_face_registration(student_id, organization_id, images_b64=images_b64, files=files)

    from face_api.pipeline import get_pipeline, decode_image
    from face_api import config
    pipeline = get_pipeline()

    if not student_id:
        return {'success': False, 'error': 'Student not selected'}, 400

    student = db.session.get(Student, int(student_id))
    if not student:
        return {'success': False, 'error': 'Student not found'}, 404

    if student.organization_id != int(organization_id):
        return {'success': False, 'error': 'Unauthorized: Student does not belong to active organization'}, 403

    images_to_process = []
    if images_b64:
        for b64 in images_b64:
            if b64:
                images_to_process.append(b64)

    if files:
        for f in files:
            if f and f.filename != '':
                if allowed_file(f.filename):
                    content = f.read()
                    if content:
                        images_to_process.append(content)

    if not images_to_process:
        return {'success': False, 'error': 'No facial image provided. Please capture or upload a photo.'}, 400

    success_count = 0
    errors = []

    for idx, img_source in enumerate(images_to_process[:5]):
        try:
            img = decode_image(img_source)
            faces = pipeline.detector.detect(img, threshold=config.FACE_DETECTION_THRESHOLD)

            if len(faces) == 0:
                errors.append(f"Image {idx+1}: No usable face detected. Please upload a clearer image.")
                continue

            if len(faces) > 1:
                errors.append(f"Image {idx+1}: Multiple faces detected. Please upload an image containing only this student.")
                continue

            face = faces[0]
            q_res = pipeline.quality_filter.evaluate(img, face)
            if not q_res.is_valid:
                errors.append(f"Image {idx+1}: Face quality check failed ({q_res.reason}). Please upload a clearer image.")
                continue

            # Extract 512-d normalized ArcFace embedding
            embedding = pipeline.recognizer.extract_embedding(img, face.landmarks)
            record = FaceEncoding(
                student_id=student.id,
                encoding_path="",
                encoding_data=embedding.tolist(),
                created_at=datetime.utcnow()
            )
            db.session.add(record)
            success_count += 1
        except Exception as e:
            errors.append(f"Image {idx+1}: {str(e)}")

    if success_count == 0:
        err_text = errors[0] if len(errors) == 1 else "No faces could be registered: " + "; ".join(errors)
        return {'success': False, 'error': err_text, 'errors': errors}, 400

    db.session.commit()
    pipeline.embedding_store.invalidate_cache(organization_id=int(organization_id))

    msg = f"{success_count} biometric ArcFace face sample(s) registered successfully for {student.name}."
    if errors:
        msg += " (Notes: " + "; ".join(errors) + ")"

    return {
        'success': True,
        'message': msg,
        'registered_count': success_count,
        'student_name': student.name,
        'roll_number': student.roll_number
    }, 200


@app.route('/school/api/register-face', methods=['POST'])
@csrf.exempt
@org_required(['school'])
def school_api_register_face():
    """Accept JSON with student_id and images_base64 (list of data-URI strings).
    Process each image using SCRFD + ArcFace, and store 512-d embeddings."""
    data = request.get_json(force=True) if request.is_json else (request.form or {})
    student_id = data.get('student_id')
    images_b64 = data.get('images_base64', [])
    if not images_b64 and data.get('image_base64'):
        images_b64 = [data['image_base64']]
    resp, code = process_student_face_registration(student_id, session.get('org_id'), images_b64=images_b64)
    return jsonify(resp), code


@app.route('/school/face-register', methods=['GET', 'POST'])
@org_required(['school'])
def school_face_register():
    classes = Class_.query.filter_by(organization_id=session.get('org_id')).all()
    students = Student.query.filter_by(organization_id=session.get('org_id')).all()

    if request.method == 'GET':
        return render_template('school/face_register.html', classes=classes, students=students)

    student_id = request.form.get('student_id', '') or (request.json.get('student_id') if request.is_json else '')
    images_b64 = request.json.get('images_base64') if request.is_json else []
    files = request.files.getlist('face_images') if 'face_images' in request.files else []

    resp, code = process_student_face_registration(student_id, session.get('org_id'), images_b64=images_b64, files=files)
    return jsonify(resp), code

# ─────────────────────────────────────────────────────────────
# DISTANCE-ADAPTIVE FACE DETECTION
def process_face_detection_with_range(image_path, detection_range='50m', student_count=0):
    """
    Intelligent Distance-Adaptive Face Detection using SCRFD + ArcFace:
    - 50 Meters: Standard classroom detection (640x640 SCRFD)
    - 100 Meters: Extended crowd deep scan mode (1280x1280 SCRFD)
    Requires FACE_API_AVAILABLE (onnxruntime + ONNX models).
    """
    if not FACE_API_AVAILABLE:
        raise RuntimeError('Face recognition engine (onnxruntime) is not available on this server.')

    from face_api import config as fa_config, decode_image as fa_decode_image
    pipeline = get_pipeline()
    range_str = str(detection_range or '').lower().strip()
    if '100' in range_str or range_str in ['crowd', 'extended', 'large'] or student_count > 15:
        resolved_meters = 100
        input_size = fa_config.DEEP_SCAN_INPUT_SIZE
    else:
        resolved_meters = 50
        input_size = fa_config.DETECTION_INPUT_SIZE

    img = fa_decode_image(image_path)
    faces = pipeline.detector.detect(img, input_size=input_size)

    valid_faces = []
    for f in faces:
        q = pipeline.quality_filter.evaluate(img, f)
        if q.is_valid:
            valid_faces.append(f)

    if valid_faces:
        landmarks = [f.landmarks for f in valid_faces]
        embeddings = pipeline.recognizer.extract_embeddings_batch(img, landmarks)
    else:
        embeddings = np.empty((0, fa_config.EMBEDDING_DIM), dtype=np.float32)

    return {
        'face_locations': [f.bbox for f in valid_faces],
        'face_encodings': embeddings,
        'resolved_meters': resolved_meters,
        'range_label': f"{resolved_meters} Meters ({'Extended Crowd Mode' if resolved_meters == 100 else 'Standard Room'})",
        'tolerance': fa_config.FACE_RECOGNITION_THRESHOLD
    }


@app.route('/api/class-students-count/<int:class_id>', methods=['GET'])
def get_class_students_count(class_id):
    count = Student.query.filter_by(class_id=class_id).count()
    recommended_range = '100m' if count > 15 else '50m'
    return jsonify({
        'class_id': class_id,
        'student_count': count,
        'recommended_range': recommended_range,
        'reason': f"Class has {count} students. {'100m Long-Distance mode recommended for crowd coverage.' if count > 15 else '50m Standard distance is optimal.'}"
    })


@app.route('/school/mark-attendance', methods=['GET', 'POST'])
@csrf.exempt
@org_required(['school'])
def school_mark_attendance():
    classes = Class_.query.filter_by(
        organization_id=session.get('org_id')
    ).all()

    if request.method == 'POST':
        class_id = request.form.get('class_id', '') or (request.json.get('class_id') if request.is_json else '')
        if not class_id:
            return jsonify({'error': 'Class not selected'}), 400

        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp_attendance.jpg')
        image_saved = False

        if 'attendance_image' in request.files:
            file = request.files['attendance_image']
            if file and file.filename != '':
                file.save(temp_path)
                image_saved = True

        if not image_saved:
            b64_data = request.form.get('image_base64') or (request.json.get('image_base64') if request.is_json else None)
            if b64_data:
                import base64
                if ',' in b64_data:
                    b64_data = b64_data.split(',')[1]
                with open(temp_path, 'wb') as f:
                    f.write(base64.b64decode(b64_data))
                image_saved = True

        if not image_saved:
            return jsonify({'error': 'No image provided. Please capture or upload a classroom photo.'}), 400

        try:
            detection_range = request.form.get('detection_range', '50m') or (request.json.get('detection_range') if request.is_json else '50m')
            students = Student.query.filter_by(class_id=int(class_id)).all()
            student_count = len(students)

            if FACE_API_AVAILABLE:
                att_result = process_classroom_attendance(
                    image_input=temp_path,
                    db_session=db.session,
                    organization_id=int(session.get('org_id')),
                    class_id=int(class_id),
                    subject_id=None,
                    detection_range=detection_range,
                    student_count=student_count
                )
            else:
                att_result = legacy_process_classroom_attendance(
                    image_path=temp_path,
                    db_session=db.session,
                    organization_id=int(session.get('org_id')),
                    class_id=int(class_id),
                    subject_id=None,
                    detection_range=detection_range,
                    student_count=student_count
                )

            if 'error' in att_result and not att_result.get('recognized'):
                return jsonify(att_result), 400

            # --- SMS Notification for Absent Students ---
            today = india_now().date()
            class_info = db.session.get(Class_, int(class_id))
            class_name = class_info.name if class_info else ''
            recognized_ids = {s.get('student_id') for s in att_result.get('recognized', []) if s.get('student_id')}
            absent_students = []
            for student in students:
                if student.id not in recognized_ids:
                    absent_students.append(student)
                    try:
                        from scripts.sms_helper import send_absent_sms
                        send_absent_sms(
                            student_name=student.name,
                            roll_number=student.roll_number,
                            phone=student.phone or '',
                            class_name=class_name,
                            absence_date=today,
                            student_email=student.email or ''
                        )
                    except Exception as sms_err:
                        print(f"[SMS ERROR] Could not send for {student.name}: {sms_err}")

            att_result['absent_count'] = len(absent_students)
            return jsonify(att_result)

        except Exception as e:
            import traceback
            print(f"ERROR in school_mark_attendance: {e}")
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500

    return render_template('school/mark_attendance.html', classes=classes)

@app.route('/school/attendance-records')
@org_required(['school'])
def school_attendance_records():
    classes = Class_.query.filter_by(organization_id=session.get('org_id')).all()
    class_id = request.args.get('class_id')
    date_str = request.args.get('date')
    month_str = request.args.get('month')

    query = Attendance.query.join(Class_).filter(Class_.organization_id == int(session.get('org_id')))
    if class_id:
        query = query.filter(Attendance.class_id == class_id)
    date_obj = None
    if date_str:
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            query = query.filter(Attendance.date == date_obj)
        except ValueError:
            pass
    if month_str:
        try:
            from calendar import monthrange
            from datetime import date
            y_val, m_val = map(int, month_str.split('-'))
            _, last_day = monthrange(y_val, m_val)
            query = query.filter(Attendance.date.between(date(y_val, m_val, 1), date(y_val, m_val, last_day)))
        except Exception:
            pass

    # If class_id and date_str are both provided, show ALL students of that class (including virtual absent ones)
    if class_id and date_obj:
        students = Student.query.filter_by(class_id=int(class_id)).all()
        present_records = Attendance.query.filter_by(class_id=int(class_id), date=date_obj).all()
        present_student_ids = {r.student_id: r for r in present_records}
        
        records = []
        for s in students:
            if s.id in present_student_ids:
                records.append(present_student_ids[s.id])
            else:
                from types import SimpleNamespace
                absent_rec = SimpleNamespace(
                    id=None,
                    date=date_obj,
                    day=date_obj.strftime('%A'),
                    time=None,
                    status='absent',
                    student=s,
                    class_=s.class_,
                    subject=None
                )
                records.append(absent_rec)
    else:
        records = query.order_by(Attendance.date.desc(), Attendance.time.desc()).all()
        
    print(f"DEBUG: Found {len(records)} attendance records for Org ID: {session.get('org_id')}")
    return render_template('school/attendance_records.html', records=records, classes=classes, selected_class=class_id, selected_date=date_str, selected_month=month_str)

@app.route('/school/reports', methods=['GET', 'POST'])
@org_required(['school'])
def school_reports():
    if request.method == 'POST':
        report_type = request.form.get('report_type', 'student')
        student_id = request.form.get('student_id')
        class_id = request.form.get('class_id')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'],
                                     fontSize=16, spaceAfter=20)
        normal_style = styles['Normal']
        
        present_style = ParagraphStyle(
            'PresentStyle',
            parent=normal_style,
            textColor=colors.HexColor('#2e7d32'),
            fontName='Helvetica-Bold',
            alignment=1
        )
        absent_style = ParagraphStyle(
            'AbsentStyle',
            parent=normal_style,
            textColor=colors.HexColor('#c62828'),
            fontName='Helvetica-Bold',
            alignment=1
        )
        
        if report_type == 'class':
            elements.append(Paragraph("Class Attendance Report", title_style))
            if class_id:
                class_ = Class_.query.get(int(class_id))
                elements.append(Paragraph(f"Class: {class_.name}", normal_style))
                if start_date and end_date:
                    elements.append(Paragraph(f"Period: {start_date} to {end_date}", normal_style))
                elements.append(Spacer(1, 0.2*inch))
                
                # Fetch class students
                students = Student.query.filter_by(class_id=int(class_id)).order_by(Student.roll_number, Student.name).all()
                
                # Fetch present records
                att_query = Attendance.query.filter_by(class_id=int(class_id))
                if start_date and end_date:
                    att_query = att_query.filter(Attendance.date.between(start_date, end_date))
                present_attendances = att_query.all()
                
                # Get unique sessions (date, subject_id)
                sessions = sorted(list(set((att.date, att.subject_id) for att in present_attendances)), key=lambda x: (x[0], x[1] or 0), reverse=True)
                
                present_table_data = [['S.No', 'Date', 'Roll No', 'Student Name', 'Subject', 'Status']]
                absent_table_data = [['S.No', 'Date', 'Roll No', 'Student Name', 'Subject', 'Status']]
                
                pres_sno = 1
                abs_sno = 1
                
                for session_date, subj_id in sessions:
                    session_present = [att for att in present_attendances if att.date == session_date and att.subject_id == subj_id]
                    present_map = {att.student_id: att for att in session_present}
                    
                    subj_name = '-'
                    if subj_id:
                        subj_obj = Subject.query.get(subj_id)
                        if subj_obj:
                            subj_name = subj_obj.name
                            
                    for s in students:
                        if s.id in present_map:
                            present_table_data.append([
                                str(pres_sno),
                                str(session_date),
                                s.roll_number,
                                s.name,
                                subj_name,
                                Paragraph('Present', present_style)
                            ])
                            pres_sno += 1
                        else:
                            absent_table_data.append([
                                str(abs_sno),
                                str(session_date),
                                s.roll_number,
                                s.name,
                                subj_name,
                                Paragraph('Absent', absent_style)
                            ])
                            abs_sno += 1
                            
                has_records = False
                
                # Add Absent Students List
                if len(absent_table_data) > 1:
                    elements.append(Paragraph("Absent Students List (S.No wise)", ParagraphStyle('SubTitleAbs', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#c62828'), spaceAfter=10)))
                    abs_table = Table(absent_table_data)
                    abs_table.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#c62828')),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0,0), (-1,0), 10),
                        ('BOTTOMPADDING', (0,0), (-1,0), 8),
                        ('TOPPADDING', (0,0), (-1,0), 8),
                        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#bdc3c7')),
                        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#fff5f5')])
                    ]))
                    elements.append(abs_table)
                    has_records = True
                    
                # Add Present Students List
                if len(present_table_data) > 1:
                    if has_records:
                        elements.append(Spacer(1, 0.3*inch))
                    elements.append(Paragraph("Present Students List (S.No wise)", ParagraphStyle('SubTitlePres', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#2e7d32'), spaceAfter=10)))
                    pres_table = Table(present_table_data)
                    pres_table.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2e7d32')),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0,0), (-1,0), 10),
                        ('BOTTOMPADDING', (0,0), (-1,0), 8),
                        ('TOPPADDING', (0,0), (-1,0), 8),
                        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#bdc3c7')),
                        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f5fff5')])
                    ]))
                    elements.append(pres_table)
                    has_records = True
                    
                if not has_records:
                    elements.append(Paragraph("No attendance records found.", normal_style))
        else:
            elements.append(Paragraph("Student Attendance Report", title_style))
            if student_id:
                student = Student.query.get(int(student_id))
                elements.append(Paragraph(f"Student: {student.name}", normal_style))
                elements.append(Paragraph(f"Roll Number: {student.roll_number}", normal_style))
                if start_date and end_date:
                    elements.append(Paragraph(f"Period: {start_date} to {end_date}", normal_style))
                elements.append(Spacer(1, 0.2*inch))
                
                # Header row for main table
                data = [['Date', 'Time', 'Subject', 'Status']]
                
                # Get the class sessions for the student's class
                att_query = Attendance.query.filter_by(class_id=student.class_id)
                if start_date and end_date:
                    att_query = att_query.filter(Attendance.date.between(start_date, end_date))
                class_attendances = att_query.all()
                
                sessions = sorted(list(set((att.date, att.subject_id) for att in class_attendances)), key=lambda x: (x[0], x[1] or 0), reverse=True)
                student_present_map = {(att.date, att.subject_id): att for att in class_attendances if att.student_id == student.id}
                
                for session_date, subj_id in sessions:
                    subj_name = '-'
                    if subj_id:
                        subj_obj = Subject.query.get(subj_id)
                        if subj_obj:
                            subj_name = subj_obj.name
                            
                    if (session_date, subj_id) in student_present_map:
                        att = student_present_map[(session_date, subj_id)]
                        data.append([
                            str(session_date),
                            att.time.strftime('%H:%M:%S') if att.time else '-',
                            subj_name,
                            Paragraph('Present', present_style)
                        ])
                    else:
                        data.append([
                            str(session_date),
                            '-',
                            subj_name,
                            Paragraph('Absent', absent_style)
                        ])

                if len(data) > 1:
                    table = Table(data)
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1a252f')),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0,0), (-1,0), 11),
                        ('BOTTOMPADDING', (0,0), (-1,0), 8),
                        ('TOPPADDING', (0,0), (-1,0), 8),
                        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#bdc3c7')),
                        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8f9fa')])
                    ]))
                    elements.append(table)
                else:
                    elements.append(Paragraph("No attendance records found.", normal_style))

        doc.build(elements)
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name='attendance_report.pdf',
                         mimetype='application/pdf')
    
    students = Student.query.filter_by(organization_id=session.get('org_id')).all()
    classes = Class_.query.filter_by(organization_id=session.get('org_id')).all()
    return render_template('school/reports.html', students=students, classes=classes)

@app.route('/school/students')
@org_required(['school'])
def school_students():
    class_id = request.args.get('class_id')
    query = Student.query.filter_by(organization_id=session.get('org_id'))
    if class_id:
        query = query.filter_by(class_id=class_id)
    students = query.all()
    return render_template('school/students.html', students=students)

# ─────────────────────────────────────────────
# COLLEGE ROUTES
# ─────────────────────────────────────────────

@app.route('/college/dashboard')
@org_required(['college'])
def college_dashboard():
    org_id = session.get('org_id')
    courses = Course.query.filter_by(organization_id=org_id).all()
    
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    change = request.args.get('change')
    
    # If user explicitly requested to change course/year, clear session cache
    if change == '1':
        session.pop('college_course_id', None)
        session.pop('college_year', None)
        return render_template('college/select_course.html', courses=courses)
        
    # If not in query params, restore from session if available
    if not course_id and 'college_course_id' in session:
        course_id = str(session.get('college_course_id'))
    if not year and 'college_year' in session:
        year = session.get('college_year')
        
    if not course_id or course_id == 'None':
        return render_template('college/select_course.html', courses=courses)
        
    try:
        course = Course.query.filter_by(id=int(course_id), organization_id=org_id).first()
    except (ValueError, TypeError):
        flash("Invalid course selection.", "danger")
        return render_template('college/select_course.html', courses=courses)
        
    if not course:
        session.pop('college_course_id', None)
        session.pop('college_year', None)
        flash("Selected course not found. Please select a course.", "info")
        return render_template('college/select_course.html', courses=courses)
    
    # Save active course
    session['college_course_id'] = course.id
    
    if not year or year == 'None':
        study_years_records = StudyYear.query.filter_by(organization_id=org_id, course_id=course.id).all()
        db_years = [y.name for y in study_years_records]
        
        # Include legacy years from classes/subjects just in case
        classes = Class_.query.filter_by(organization_id=org_id, course_id=course.id).all()
        subjects = Subject.query.filter_by(organization_id=org_id, course_id=course.id).all()
        class_years = [c.study_year for c in classes if c.study_year]
        subj_years = [s.study_year for s in subjects if s.study_year]
        
        years = sorted(list(set(db_years + class_years + subj_years)))
        return render_template('college/select_year.html', course=course, years=years, study_years=study_years_records)
        
    # Save active year
    session['college_year'] = year
    
    classes = Class_.query.filter_by(organization_id=org_id, course_id=course.id, study_year=year).all()
    total_classes = len(classes)
    class_ids = [c.id for c in classes]
    total_students = Student.query.filter(Student.class_id.in_(class_ids)).count() if class_ids else 0
    today_attendance = Attendance.query.filter_by(date=india_now().date()).filter(Attendance.class_id.in_(class_ids)).count() if class_ids else 0
    
    return render_template('college/dashboard.html',
                           total_classes=total_classes,
                           total_students=total_students,
                           today_attendance=today_attendance,
                           course=course,
                           year=year,
                           course_id=course.id)

@app.route('/college/academic-calendar', methods=['GET', 'POST'])
@org_required(['college'])
def college_academic_calendar():
    org_id = session.get('org_id')
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    if request.method == 'POST':
        title = request.form.get('title')
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        event_type = request.form.get('event_type', 'Academic')
        status = request.form.get('status', 'Upcoming')
        description = request.form.get('description', '')

        if not title or not start_date_str:
            flash('Event title and start date are required.', 'danger')
            return redirect(url_for('college_academic_calendar', course_id=course_id, year=year))

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
            new_event = AcademicEvent(
                title=title,
                description=description,
                start_date=start_date,
                end_date=end_date,
                event_type=event_type,
                status=status,
                course_id=int(course_id) if course_id and course_id != 'None' else None,
                study_year=year if year and year != 'None' else None,
                organization_id=org_id
            )
            db.session.add(new_event)
            db.session.commit()
            flash('Academic event added successfully!', 'success')
        except Exception as e:
            flash(f'Error saving event: {str(e)}', 'danger')
        return redirect(url_for('college_academic_calendar', course_id=course_id, year=year))

    events = AcademicEvent.query.filter_by(organization_id=org_id).order_by(AcademicEvent.start_date.asc()).all()
    return render_template('academic_calendar.html', events=events, org_type='college', course_id=course_id, year=year)

@app.route('/college/academic-calendar/delete/<int:event_id>', methods=['POST', 'GET'])
@org_required(['college'])
def college_delete_academic_event(event_id):
    org_id = session.get('org_id')
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    event = AcademicEvent.query.filter_by(id=event_id, organization_id=org_id).first_or_404()
    db.session.delete(event)
    db.session.commit()
    flash('Event deleted successfully.', 'success')
    return redirect(url_for('college_academic_calendar', course_id=course_id, year=year))






@app.route('/college/add-year', methods=['GET', 'POST'])
@org_required(['college'])
def college_add_year():
    course_id = request.args.get('course_id')
    if request.method == 'POST':
        year_name = request.form.get('year_name')
        if not year_name:
            flash('Year name is required', 'danger')
            return redirect(url_for('college_add_year', course_id=course_id))
            
        existing = StudyYear.query.filter_by(name=year_name, course_id=int(course_id), organization_id=session.get('org_id')).first()
        if not existing:
            study_year = StudyYear(name=year_name, course_id=int(course_id), organization_id=session.get('org_id'))
            db.session.add(study_year)
            db.session.commit()
            
        return redirect(url_for('college_dashboard', course_id=course_id, year=year_name))
    return render_template('college/add_year.html', course_id=course_id)
@app.route('/college/add-course', methods=['GET', 'POST'])
@org_required(['college'])
def college_add_course():
    if request.method == 'POST':
        name = request.form.get('course_name')
        if not name:
            flash('Course name is required', 'danger')
            return redirect(url_for('college_add_course'))
        course = Course(name=name, organization_id=session.get('org_id'))
        db.session.add(course)
        db.session.commit()
        flash('Course added successfully!', 'success')
        return redirect(url_for('college_dashboard'))
    return render_template('college/add_course.html')

@app.route('/college/courses')
@org_required(['college'])
def college_courses():
    courses = Course.query.filter_by(organization_id=session.get('org_id')).all()
    return render_template('college/courses.html', courses=courses)

@app.route('/college/subjects')
@org_required(['college'])
def college_subjects():
    subjects = Subject.query.filter_by(organization_id=session.get('org_id')).all()
    return render_template('college/subjects.html', subjects=subjects)

@app.route('/college/add-subject', methods=['GET', 'POST'])
@org_required(['college'])
def college_add_subject():
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    if request.method == 'POST':
        name = request.form.get('subject_name')
        if not name or not course_id:
            flash('Subject name and course are required', 'danger')
            return redirect(url_for('college_add_subject', course_id=course_id, year=year))
        subject = Subject(name=name, course_id=int(course_id), study_year=year, organization_id=session.get('org_id'))
        db.session.add(subject)
        db.session.commit()
        flash('Subject added successfully!', 'success')
        return redirect(url_for('college_dashboard', course_id=course_id, year=year))
    return render_template('college/add_subject.html', course_id=course_id, year=year)
@app.route('/college/classes')
@org_required(['college'])
def college_classes():
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    query = Class_.query.filter_by(organization_id=session.get('org_id'))
    if course_id:
        query = query.filter_by(course_id=course_id)
    if year:
        query = query.filter_by(study_year=year)
    classes = query.all()
    for c in classes:
        c.student_count = len(c.students)
    return render_template('college/classes.html', classes=classes, course_id=course_id, year=year)

@app.route('/college/add-class', methods=['GET', 'POST'])
@org_required(['college'])
def college_add_class():
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    if course_id == 'None': course_id = None
    if year == 'None': year = None
    courses = Course.query.filter_by(organization_id=session.get('org_id')).all()
    
    if request.method == 'POST':
        class_name = request.form.get('class_name')
        course_id_post = request.form.get('course_id')
        study_year = request.form.get('study_year')
        
        if not all([class_name, study_year, course_id_post]):
            flash('All fields are required', 'danger')
            return redirect(url_for('college_add_class', course_id=course_id, year=year))
            
        class_ = Class_(name=class_name, academic_year='2023-2024', study_year=study_year,
                        organization_id=session.get('org_id'), course_id=int(course_id_post))
        db.session.add(class_)
        db.session.commit()
        flash('Class added successfully!', 'success')
        return redirect(url_for('college_dashboard', course_id=course_id_post, year=study_year))
        
    return render_template('college/add_class.html', courses=courses, selected_course=course_id, selected_year=year)

@app.route('/college/students')
@org_required(['college'])
def college_students():
    class_id = request.args.get('class_id')
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    
    query = Student.query.join(Class_).filter(Student.organization_id == session.get('org_id'))
    if class_id:
        query = query.filter(Student.class_id == class_id)
    if course_id:
        query = query.filter(Class_.course_id == course_id)
    if year:
        query = query.filter(Class_.study_year == year)
        
    students = query.all()
    return render_template('college/students.html', students=students, course_id=course_id, year=year)

@app.route('/college/add-student', methods=['GET', 'POST'])
@org_required(['college'])
def college_add_student():
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    
    query = Class_.query.filter_by(organization_id=session.get('org_id'))
    if course_id: query = query.filter_by(course_id=course_id)
    if year: query = query.filter_by(study_year=year)
    classes = query.all()
    if request.method == 'POST':
        name = request.form.get('name')
        roll_number = request.form.get('roll_number')
        phone = request.form.get('phone')
        class_id = request.form.get('class_id')
        if not all([name, roll_number, class_id]):
            flash('Name, roll number and class are required', 'danger')
            return redirect(url_for('college_add_student'))
        student = Student(name=name, roll_number=roll_number, phone=phone,
                          organization_id=session.get('org_id'), class_id=int(class_id))
        db.session.add(student)
        db.session.commit()
        flash('Student added successfully!', 'success')
        return redirect(url_for('college_dashboard'))
    return render_template('college/add_student.html', classes=classes)

@app.route('/college/face-register', methods=['GET', 'POST'])
@org_required(['college'])
def college_face_register():
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    
    cls_query = Class_.query.filter_by(organization_id=session.get('org_id'))
    if course_id: cls_query = cls_query.filter_by(course_id=course_id)
    if year: cls_query = cls_query.filter_by(study_year=year)
    classes = cls_query.all()
    class_ids = [c.id for c in classes]
    
    if class_ids:
        students = Student.query.filter(Student.class_id.in_(class_ids)).all()
    else:
        students = []
    if request.method == 'POST':
        student_id = request.form.get('student_id', '') or (request.json.get('student_id') if request.is_json else '')
        images_b64 = request.json.get('images_base64') if request.is_json else []
        files = request.files.getlist('face_images') if 'face_images' in request.files else []
        resp, code = process_student_face_registration(student_id, session.get('org_id'), images_b64=images_b64, files=files)
        return jsonify(resp), code
    return render_template('college/face_register.html', students=students, classes=classes)

@app.route('/college/mark-attendance', methods=['GET', 'POST'])
@csrf.exempt
@org_required(['college'])
def college_mark_attendance():
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    
    query = Class_.query.filter_by(organization_id=session.get('org_id'))
    if course_id: query = query.filter_by(course_id=course_id)
    if year: query = query.filter_by(study_year=year)
    classes = query.all()
    
    subj_query = Subject.query.filter_by(organization_id=session.get('org_id'))
    if course_id: subj_query = subj_query.filter_by(course_id=course_id)
    if year: subj_query = subj_query.filter_by(study_year=year)
    subjects = subj_query.all()
    if request.method == 'POST':
        class_id = request.form.get('class_id', '') or (request.json.get('class_id') if request.is_json else '')
        subject_id = request.form.get('subject_id', '') or request.form.get('subject_name', '') or (request.json.get('subject_id') or request.json.get('subject_name') if request.is_json else '')
        if not class_id:
            return jsonify({'error': 'Class not selected'}), 400
        
        subj_id_int = None
        if subject_id:
            if str(subject_id).isdigit():
                subj_id_int = int(subject_id)
            else:
                s_obj = Subject.query.filter_by(name=str(subject_id), organization_id=session.get('org_id')).first()
                if s_obj:
                    subj_id_int = s_obj.id

        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp_attendance.jpg')
        image_saved = False

        if 'attendance_image' in request.files:
            file = request.files['attendance_image']
            if file and file.filename != '':
                file.save(temp_path)
                image_saved = True

        if not image_saved:
            b64_data = request.form.get('image_base64') or (request.json.get('image_base64') if request.is_json else None)
            if b64_data:
                import base64
                if ',' in b64_data:
                    b64_data = b64_data.split(',')[1]
                with open(temp_path, 'wb') as f:
                    f.write(base64.b64decode(b64_data))
                image_saved = True

        if not image_saved:
            return jsonify({'error': 'No image provided. Please capture or upload a classroom photo.'}), 400

        try:
            detection_range = request.form.get('detection_range', '50m') or (request.json.get('detection_range') if request.is_json else '50m')
            students = Student.query.filter_by(class_id=int(class_id)).all()
            student_count = len(students)

            if FACE_API_AVAILABLE:
                att_result = process_classroom_attendance(
                    image_input=temp_path,
                    db_session=db.session,
                    organization_id=int(session.get('org_id')),
                    class_id=int(class_id),
                    subject_id=subj_id_int,
                    detection_range=detection_range,
                    student_count=student_count
                )
            else:
                att_result = legacy_process_classroom_attendance(
                    image_path=temp_path,
                    db_session=db.session,
                    organization_id=int(session.get('org_id')),
                    class_id=int(class_id),
                    subject_id=subj_id_int,
                    detection_range=detection_range,
                    student_count=student_count
                )

            if 'error' in att_result and not att_result.get('recognized'):
                return jsonify(att_result), 400

            # --- SMS Notification for Absent Students ---
            today = india_now().date()
            class_info = db.session.get(Class_, int(class_id))
            class_name = class_info.name if class_info else ''
            recognized_ids = {s.get('student_id') for s in att_result.get('recognized', []) if s.get('student_id')}
            absent_students = []
            for student in students:
                if student.id not in recognized_ids:
                    absent_students.append(student)
                    try:
                        from scripts.sms_helper import send_absent_sms
                        send_absent_sms(
                            student_name=student.name,
                            roll_number=student.roll_number,
                            phone=student.phone or '',
                            class_name=class_name,
                            absence_date=today,
                            student_email=student.email or ''
                        )
                    except Exception as sms_err:
                        print(f"[SMS ERROR] Could not send for {student.name}: {sms_err}")

            att_result['absent_count'] = len(absent_students)
            return jsonify(att_result)

        except Exception as e:
            import traceback
            print(f"ERROR in college_mark_attendance: {e}")
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500

    return render_template('college/mark_attendance.html', classes=classes, subjects=subjects, course_id=course_id, year=year)

@app.route('/college/attendance-records')
@org_required(['college'])
def college_attendance_records():
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    
    cls_query = Class_.query.filter_by(organization_id=session.get('org_id'))
    if course_id: cls_query = cls_query.filter_by(course_id=course_id)
    if year: cls_query = cls_query.filter_by(study_year=year)
    classes = cls_query.all()
    class_id = request.args.get('class_id')
    date_str = request.args.get('date')
    month_str = request.args.get('month')

    query = Attendance.query.join(Class_).filter(Class_.organization_id == int(session.get('org_id')))
    if class_id:
        query = query.filter(Attendance.class_id == class_id)
    date_obj = None
    if date_str:
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            query = query.filter(Attendance.date == date_obj)
        except ValueError:
            pass
    if month_str:
        try:
            from calendar import monthrange
            from datetime import date
            y_val, m_val = map(int, month_str.split('-'))
            _, last_day = monthrange(y_val, m_val)
            query = query.filter(Attendance.date.between(date(y_val, m_val, 1), date(y_val, m_val, last_day)))
        except Exception:
            pass

    # If class_id and date_str are both provided, show ALL students of that class (including virtual absent ones)
    if class_id and date_obj:
        students = Student.query.filter_by(class_id=int(class_id)).all()
        
        # Find all unique subjects for which attendance was taken for this class on this date
        subjects_taken = db.session.query(Attendance.subject_id).filter_by(class_id=int(class_id), date=date_obj).distinct().all()
        subjects_taken = [s[0] for s in subjects_taken]
        
        if not subjects_taken:
            subjects_taken = [None]
            
        records = []
        for subj_id in subjects_taken:
            present_records = Attendance.query.filter_by(class_id=int(class_id), date=date_obj, subject_id=subj_id).all()
            present_student_ids = {r.student_id: r for r in present_records}
            
            for s in students:
                if s.id in present_student_ids:
                    records.append(present_student_ids[s.id])
                else:
                    from types import SimpleNamespace
                    subj = Subject.query.get(subj_id) if subj_id else None
                    absent_rec = SimpleNamespace(
                        id=None,
                        date=date_obj,
                        day=date_obj.strftime('%A'),
                        time=None,
                        status='absent',
                        student=s,
                        class_=s.class_,
                        subject=subj
                    )
                    records.append(absent_rec)
    else:
        records = query.order_by(Attendance.date.desc(), Attendance.time.desc()).all()
        
    return render_template('college/attendance_records.html', records=records, classes=classes, selected_class=class_id, selected_date=date_str, selected_month=month_str)

@app.route('/college/reports', methods=['GET', 'POST'])
@org_required(['college'])
def college_reports():
    if request.method == 'POST':
        report_type = request.form.get('report_type', 'student')
        student_id = request.form.get('student_id')
        class_id = request.form.get('class_id')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'],
                                     fontSize=16, spaceAfter=20)
        normal_style = styles['Normal']
        
        present_style = ParagraphStyle(
            'PresentStyle',
            parent=normal_style,
            textColor=colors.HexColor('#2e7d32'),
            fontName='Helvetica-Bold',
            alignment=1
        )
        absent_style = ParagraphStyle(
            'AbsentStyle',
            parent=normal_style,
            textColor=colors.HexColor('#c62828'),
            fontName='Helvetica-Bold',
            alignment=1
        )
        
        if report_type == 'class':
            elements.append(Paragraph("Class Attendance Report", title_style))
            if class_id:
                class_ = Class_.query.get(int(class_id))
                elements.append(Paragraph(f"Class: {class_.name}", normal_style))
                if start_date and end_date:
                    elements.append(Paragraph(f"Period: {start_date} to {end_date}", normal_style))
                elements.append(Spacer(1, 0.2*inch))
                
                # Fetch class students
                students = Student.query.filter_by(class_id=int(class_id)).order_by(Student.roll_number, Student.name).all()
                
                # Fetch present records
                att_query = Attendance.query.filter_by(class_id=int(class_id))
                if start_date and end_date:
                    att_query = att_query.filter(Attendance.date.between(start_date, end_date))
                present_attendances = att_query.all()
                
                # Get unique sessions (date, subject_id)
                sessions = sorted(list(set((att.date, att.subject_id) for att in present_attendances)), key=lambda x: (x[0], x[1] or 0), reverse=True)
                
                present_table_data = [['S.No', 'Date', 'Roll No', 'Student Name', 'Subject', 'Status']]
                absent_table_data = [['S.No', 'Date', 'Roll No', 'Student Name', 'Subject', 'Status']]
                
                pres_sno = 1
                abs_sno = 1
                
                for session_date, subj_id in sessions:
                    session_present = [att for att in present_attendances if att.date == session_date and att.subject_id == subj_id]
                    present_map = {att.student_id: att for att in session_present}
                    
                    subj_name = '-'
                    if subj_id:
                        subj_obj = Subject.query.get(subj_id)
                        if subj_obj:
                            subj_name = subj_obj.name
                            
                    for s in students:
                        if s.id in present_map:
                            present_table_data.append([
                                str(pres_sno),
                                str(session_date),
                                s.roll_number,
                                s.name,
                                subj_name,
                                Paragraph('Present', present_style)
                            ])
                            pres_sno += 1
                        else:
                            absent_table_data.append([
                                str(abs_sno),
                                str(session_date),
                                s.roll_number,
                                s.name,
                                subj_name,
                                Paragraph('Absent', absent_style)
                            ])
                            abs_sno += 1
                            
                has_records = False
                
                # Add Absent Students List
                if len(absent_table_data) > 1:
                    elements.append(Paragraph("Absent Students List (S.No wise)", ParagraphStyle('SubTitleAbs', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#c62828'), spaceAfter=10)))
                    abs_table = Table(absent_table_data)
                    abs_table.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#c62828')),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0,0), (-1,0), 10),
                        ('BOTTOMPADDING', (0,0), (-1,0), 8),
                        ('TOPPADDING', (0,0), (-1,0), 8),
                        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#bdc3c7')),
                        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#fff5f5')])
                    ]))
                    elements.append(abs_table)
                    has_records = True
                    
                # Add Present Students List
                if len(present_table_data) > 1:
                    if has_records:
                        elements.append(Spacer(1, 0.3*inch))
                    elements.append(Paragraph("Present Students List (S.No wise)", ParagraphStyle('SubTitlePres', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#2e7d32'), spaceAfter=10)))
                    pres_table = Table(present_table_data)
                    pres_table.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2e7d32')),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0,0), (-1,0), 10),
                        ('BOTTOMPADDING', (0,0), (-1,0), 8),
                        ('TOPPADDING', (0,0), (-1,0), 8),
                        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#bdc3c7')),
                        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f5fff5')])
                    ]))
                    elements.append(pres_table)
                    has_records = True
                    
                if not has_records:
                    elements.append(Paragraph("No attendance records found.", normal_style))
        else:
            elements.append(Paragraph("Student Attendance Report", title_style))
            if student_id:
                student = Student.query.get(int(student_id))
                elements.append(Paragraph(f"Student: {student.name}", normal_style))
                elements.append(Paragraph(f"Roll Number: {student.roll_number}", normal_style))
                if start_date and end_date:
                    elements.append(Paragraph(f"Period: {start_date} to {end_date}", normal_style))
                elements.append(Spacer(1, 0.2*inch))
                
                # Header row for main table
                data = [['Date', 'Time', 'Subject', 'Status']]
                
                # Get the class sessions for the student's class
                att_query = Attendance.query.filter_by(class_id=student.class_id)
                if start_date and end_date:
                    att_query = att_query.filter(Attendance.date.between(start_date, end_date))
                class_attendances = att_query.all()
                
                sessions = sorted(list(set((att.date, att.subject_id) for att in class_attendances)), key=lambda x: (x[0], x[1] or 0), reverse=True)
                student_present_map = {(att.date, att.subject_id): att for att in class_attendances if att.student_id == student.id}
                
                for session_date, subj_id in sessions:
                    subj_name = '-'
                    if subj_id:
                        subj_obj = Subject.query.get(subj_id)
                        if subj_obj:
                            subj_name = subj_obj.name
                            
                    if (session_date, subj_id) in student_present_map:
                        att = student_present_map[(session_date, subj_id)]
                        data.append([
                            str(session_date),
                            att.time.strftime('%H:%M:%S') if att.time else '-',
                            subj_name,
                            Paragraph('Present', present_style)
                        ])
                    else:
                        data.append([
                            str(session_date),
                            '-',
                            subj_name,
                            Paragraph('Absent', absent_style)
                        ])

                if len(data) > 1:
                    table = Table(data)
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1a252f')),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0,0), (-1,0), 11),
                        ('BOTTOMPADDING', (0,0), (-1,0), 8),
                        ('TOPPADDING', (0,0), (-1,0), 8),
                        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#bdc3c7')),
                        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8f9fa')])
                    ]))
                    elements.append(table)
                else:
                    elements.append(Paragraph("No attendance records found.", normal_style))

        doc.build(elements)
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name='attendance_report.pdf',
                         mimetype='application/pdf')
    
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    cls_query = Class_.query.filter_by(organization_id=session.get('org_id'))
    if course_id: cls_query = cls_query.filter_by(course_id=course_id)
    if year: cls_query = cls_query.filter_by(study_year=year)
    classes = cls_query.all()
    class_ids = [c.id for c in classes]
    if class_ids:
        students = Student.query.filter(Student.class_id.in_(class_ids)).all()
    else:
        students = []
    return render_template('college/reports.html', students=students, classes=classes)
    
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    cls_query = Class_.query.filter_by(organization_id=session.get('org_id'))
    if course_id: cls_query = cls_query.filter_by(course_id=course_id)
    if year: cls_query = cls_query.filter_by(study_year=year)
    classes = cls_query.all()
    class_ids = [c.id for c in classes]
    if class_ids:
        students = Student.query.filter(Student.class_id.in_(class_ids)).all()
    else:
        students = []
    return render_template('college/reports.html', students=students, classes=classes)

# ─────────────────────────────────────────────
# INSTITUTION ROUTES
# ─────────────────────────────────────────────

@app.route('/institution/dashboard')
@org_required(['institution'])
def institution_dashboard():
    org_id = session.get('org_id')
    courses = Course.query.filter_by(organization_id=org_id).all()
    
    course_id = request.args.get('course_id')
    branch = request.args.get('branch')
    year = request.args.get('year')
    sem = request.args.get('sem')
    
    if not course_id or course_id == 'None':
        return render_template('institution/select_course.html', courses=courses)
        
    try:
        course = Course.query.get(int(course_id))
    except (ValueError, TypeError):
        flash("Invalid course selection.", "danger")
        return redirect(url_for('institution_dashboard'))
        
    if not course:
        flash("Course not found.", "danger")
        return redirect(url_for('institution_dashboard'))
    
    if not branch or branch == 'None':
        branches = Branch.query.filter_by(organization_id=org_id, course_id=course_id).all()
        return render_template('institution/select_branch.html', course=course, branches=branches)
        
    if not year or year == 'None':
        years = StudyYear.query.filter_by(organization_id=org_id, course_id=course_id).all()
        return render_template('institution/select_year.html', course=course, branch=branch, years=years)
        
    if not sem or sem == 'None':
        sems = Semester.query.filter_by(organization_id=org_id, course_id=course_id).all()
        return render_template('institution/select_sem.html', course=course, branch=branch, year=year, sems=sems)
        
    classes = Class_.query.filter_by(organization_id=org_id, course_id=course_id, branch=branch, study_year=year, semester=sem).all()
    total_classes = len(classes)
    class_ids = [c.id for c in classes]
    total_students = Student.query.filter(Student.class_id.in_(class_ids)).count() if class_ids else 0
    today_attendance = Attendance.query.filter_by(date=india_now().date()).filter(Attendance.class_id.in_(class_ids)).count() if class_ids else 0
    
    return render_template('institution/dashboard.html',
                           total_classes=total_classes,
                           total_students=total_students,
                           today_attendance=today_attendance,
                           course=course,
                           branch=branch,
                           year=year,
                           sem=sem,
                           course_id=course_id)

@app.route('/institution/academic-calendar', methods=['GET', 'POST'])
@org_required(['institution'])
def institution_academic_calendar():
    org_id = session.get('org_id')
    course_id = request.args.get('course_id')
    branch = request.args.get('branch')
    year = request.args.get('year')
    sem = request.args.get('sem')
    if request.method == 'POST':
        title = request.form.get('title')
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        event_type = request.form.get('event_type', 'Academic')
        status = request.form.get('status', 'Upcoming')
        description = request.form.get('description', '')

        if not title or not start_date_str:
            flash('Event title and start date are required.', 'danger')
            return redirect(url_for('institution_academic_calendar', course_id=course_id, branch=branch, year=year, sem=sem))

        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None
            new_event = AcademicEvent(
                title=title,
                description=description,
                start_date=start_date,
                end_date=end_date,
                event_type=event_type,
                status=status,
                course_id=int(course_id) if course_id and course_id != 'None' else None,
                study_year=year if year and year != 'None' else None,
                organization_id=org_id
            )
            db.session.add(new_event)
            db.session.commit()
            flash('Academic event added successfully!', 'success')
        except Exception as e:
            flash(f'Error saving event: {str(e)}', 'danger')
        return redirect(url_for('institution_academic_calendar', course_id=course_id, branch=branch, year=year, sem=sem))

    events = AcademicEvent.query.filter_by(organization_id=org_id).order_by(AcademicEvent.start_date.asc()).all()
    return render_template('academic_calendar.html', events=events, org_type='institution', course_id=course_id, branch=branch, year=year, sem=sem)

@app.route('/institution/academic-calendar/delete/<int:event_id>', methods=['POST', 'GET'])
@org_required(['institution'])
def institution_delete_academic_event(event_id):
    org_id = session.get('org_id')
    course_id = request.args.get('course_id')
    branch = request.args.get('branch')
    year = request.args.get('year')
    sem = request.args.get('sem')
    event = AcademicEvent.query.filter_by(id=event_id, organization_id=org_id).first_or_404()
    db.session.delete(event)
    db.session.commit()
    flash('Event deleted successfully.', 'success')
    return redirect(url_for('institution_academic_calendar', course_id=course_id, branch=branch, year=year, sem=sem))






@app.route('/institution/add-branch', methods=['GET', 'POST'])
@org_required(['institution'])
def institution_add_branch():
    course_id = request.args.get('course_id')
    if request.method == 'POST':
        branch_name = request.form.get('branch_name')
        if not branch_name:
            flash('Branch name is required', 'danger')
            return redirect(url_for('institution_add_branch', course_id=course_id))
        branch = Branch(name=branch_name, course_id=int(course_id), organization_id=session.get('org_id'))
        db.session.add(branch)
        db.session.commit()
        return redirect(url_for('institution_dashboard', course_id=course_id, branch=branch_name))
    return render_template('institution/add_branch.html', course_id=course_id)

@app.route('/institution/add-year', methods=['GET', 'POST'])
@org_required(['institution'])
def institution_add_year():
    course_id = request.args.get('course_id')
    branch = request.args.get('branch')
    if request.method == 'POST':
        year_name = request.form.get('year_name')
        if not year_name:
            flash('Year name is required', 'danger')
            return redirect(url_for('institution_add_year', course_id=course_id, branch=branch))
        year = StudyYear(name=year_name, course_id=int(course_id), organization_id=session.get('org_id'))
        db.session.add(year)
        db.session.commit()
        return redirect(url_for('institution_dashboard', course_id=course_id, branch=branch, year=year_name))
    return render_template('institution/add_year.html', course_id=course_id, branch=branch)

@app.route('/institution/add-sem', methods=['GET', 'POST'])
@org_required(['institution'])
def institution_add_sem():
    course_id = request.args.get('course_id')
    branch = request.args.get('branch')
    year = request.args.get('year')
    if request.method == 'POST':
        sem_name = request.form.get('sem_name')
        if not sem_name:
            flash('Semester name is required', 'danger')
            return redirect(url_for('institution_add_sem', course_id=course_id, branch=branch, year=year))
        sem = Semester(name=sem_name, course_id=int(course_id), organization_id=session.get('org_id'))
        db.session.add(sem)
        db.session.commit()
        return redirect(url_for('institution_dashboard', course_id=course_id, branch=branch, year=year, sem=sem_name))
    return render_template('institution/add_sem.html', course_id=course_id, branch=branch, year=year)
@app.route('/institution/add-course', methods=['GET', 'POST'])
@org_required(['institution'])
def institution_add_course():
    if request.method == 'POST':
        name = request.form.get('course_name')
        if not name:
            flash('Course name is required', 'danger')
            return redirect(url_for('institution_add_course'))
        course = Course(name=name, organization_id=session.get('org_id'))
        db.session.add(course)
        db.session.commit()
        flash('Course added successfully!', 'success')
        return redirect(url_for('institution_dashboard'))
    return render_template('institution/add_course.html')

@app.route('/institution/add-subject', methods=['GET', 'POST'])
@org_required(['institution'])
def institution_add_subject():
    course_id = request.args.get('course_id')
    branch = request.args.get('branch')
    year = request.args.get('year')
    sem = request.args.get('sem')
    if request.method == 'POST':
        name = request.form.get('subject_name')
        if not name or not course_id:
            flash('Subject name and course are required', 'danger')
            return redirect(url_for('institution_add_subject', course_id=course_id, branch=branch, year=year, sem=sem))
        subject = Subject(name=name, course_id=int(course_id), study_year=year, organization_id=session.get('org_id'))
        db.session.add(subject)
        db.session.commit()
        flash('Subject added successfully!', 'success')
        return redirect(url_for('institution_dashboard', course_id=course_id, branch=branch, year=year, sem=sem))
    return render_template('institution/add_subject.html', course_id=course_id, branch=branch, year=year, sem=sem)
@app.route('/institution/classes')
@org_required(['institution'])
def institution_classes():
    course_id = request.args.get('course_id')
    branch = request.args.get('branch')
    year = request.args.get('year')
    sem = request.args.get('sem')
    query = Class_.query.filter_by(organization_id=session.get('org_id'))
    if course_id:
        query = query.filter_by(course_id=course_id)
    if branch:
        query = query.filter_by(branch=branch)
    if year:
        query = query.filter_by(study_year=year)
    if sem:
        query = query.filter_by(semester=sem)
    classes = query.all()
    for c in classes:
        c.student_count = len(c.students)
    return render_template('institution/classes.html', classes=classes, course_id=course_id, branch=branch, year=year, sem=sem)

@app.route('/institution/add-class', methods=['GET', 'POST'])
@org_required(['institution'])
def institution_add_class():
    course_id = request.args.get('course_id')
    branch = request.args.get('branch')
    year = request.args.get('year')
    sem = request.args.get('sem')
    if course_id == 'None': course_id = None
    if branch == 'None': branch = None
    if year == 'None': year = None
    if sem == 'None': sem = None
    courses = Course.query.filter_by(organization_id=session.get('org_id')).all()
    
    if request.method == 'POST':
        class_name = request.form.get('class_name')
        course_id_post = request.form.get('course_id')
        branch_post = request.form.get('branch')
        study_year = request.form.get('study_year')
        sem_post = request.form.get('sem')
        
        if not all([class_name, study_year, course_id_post]):
            flash('All fields are required', 'danger')
            return redirect(url_for('institution_add_class', course_id=course_id, branch=branch, year=year, sem=sem))
            
        class_ = Class_(name=class_name, academic_year='2023-2024', study_year=study_year, branch=branch_post, semester=sem_post,
                        organization_id=session.get('org_id'), course_id=int(course_id_post))
        db.session.add(class_)
        db.session.commit()
        flash('Class added successfully!', 'success')
        return redirect(url_for('institution_dashboard', course_id=course_id_post, branch=branch_post, year=study_year, sem=sem_post))
        
    return render_template('institution/add_class.html', courses=courses, selected_course=course_id, selected_branch=branch, selected_year=year, selected_sem=sem)

@app.route('/institution/students')
@org_required(['institution'])
def institution_students():
    class_id = request.args.get('class_id')
    course_id = request.args.get('course_id')
    branch = request.args.get('branch')
    year = request.args.get('year')
    sem = request.args.get('sem')
    
    query = Student.query.join(Class_).filter(Student.organization_id == session.get('org_id'))
    if class_id:
        query = query.filter(Student.class_id == class_id)
    if course_id:
        query = query.filter(Class_.course_id == course_id)
    if branch:
        query = query.filter(Class_.branch == branch)
    if year:
        query = query.filter(Class_.study_year == year)
    if sem:
        query = query.filter(Class_.semester == sem)
        
    students = query.all()
    return render_template('institution/students.html', students=students, course_id=course_id, branch=branch, year=year, sem=sem)

@app.route('/institution/add-student', methods=['GET', 'POST'])
@org_required(['institution'])
def institution_add_student():
    course_id = request.args.get('course_id')
    branch = request.args.get('branch')
    year = request.args.get('year')
    sem = request.args.get('sem')
    
    query = Class_.query.filter_by(organization_id=session.get('org_id'))
    if course_id: query = query.filter_by(course_id=course_id)
    if branch: query = query.filter_by(branch=branch)
    if year: query = query.filter_by(study_year=year)
    if sem: query = query.filter_by(semester=sem)
    classes = query.all()
    if request.method == 'POST':
        name = request.form.get('name')
        roll_number = request.form.get('roll_number')
        phone = request.form.get('phone')
        class_id = request.form.get('class_id')
        if not all([name, roll_number, class_id]):
            flash('Name, roll number and class are required', 'danger')
            return redirect(url_for('institution_add_student'))
        student = Student(name=name, roll_number=roll_number, phone=phone,
                          organization_id=session.get('org_id'), class_id=int(class_id))
        db.session.add(student)
        db.session.commit()
        flash('Student added successfully!', 'success')
        return redirect(url_for('institution_dashboard'))
    return render_template('institution/add_student.html', classes=classes)

@app.route('/institution/face-register', methods=['GET', 'POST'])
@org_required(['institution'])
def institution_face_register():
    course_id = request.args.get('course_id')
    branch = request.args.get('branch')
    year = request.args.get('year')
    sem = request.args.get('sem')
    
    cls_query = Class_.query.filter_by(organization_id=session.get('org_id'))
    if course_id: cls_query = cls_query.filter_by(course_id=course_id)
    if branch: cls_query = cls_query.filter_by(branch=branch)
    if year: cls_query = cls_query.filter_by(study_year=year)
    if sem: cls_query = cls_query.filter_by(semester=sem)
    classes = cls_query.all()
    class_ids = [c.id for c in classes]
    
    if class_ids:
        students = Student.query.filter(Student.class_id.in_(class_ids)).all()
    else:
        students = []
    if request.method == 'POST':
        student_id = request.form.get('student_id', '')
        if not student_id:
            return jsonify({'error': 'Student not selected'}), 400
            
        files = request.files.getlist('face_images')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': 'No file selected'}), 400

        success_count, msg, err = process_student_face_registration(int(student_id), files)
        if err:
            return jsonify({'error': err}), 400
        return jsonify({'success': f'{success_count} face encodings registered successfully using ArcFace'})
    return render_template('institution/face_register.html', students=students, classes=classes)

@app.route('/institution/mark-attendance', methods=['GET', 'POST'])
@csrf.exempt
@org_required(['institution'])
def institution_mark_attendance():
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    
    query = Class_.query.filter_by(organization_id=session.get('org_id'))
    if course_id: query = query.filter_by(course_id=course_id)
    if year: query = query.filter_by(study_year=year)
    classes = query.all()
    
    subj_query = Subject.query.filter_by(organization_id=session.get('org_id'))
    if course_id: subj_query = subj_query.filter_by(course_id=course_id)
    if year: subj_query = subj_query.filter_by(study_year=year)
    subjects = subj_query.all()
    if request.method == 'POST':
        class_id = request.form.get('class_id', '') or (request.json.get('class_id') if request.is_json else '')
        subject_id = request.form.get('subject_id', '') or request.form.get('subject_name', '') or (request.json.get('subject_id') or request.json.get('subject_name') if request.is_json else '')
        if not class_id:
            return jsonify({'error': 'Class not selected'}), 400
        
        subj_id_int = None
        if subject_id:
            if str(subject_id).isdigit():
                subj_id_int = int(subject_id)
            else:
                s_obj = Subject.query.filter_by(name=str(subject_id), organization_id=session.get('org_id')).first()
                if s_obj:
                    subj_id_int = s_obj.id

        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], 'temp_attendance.jpg')
        image_saved = False

        if 'attendance_image' in request.files:
            file = request.files['attendance_image']
            if file and file.filename != '':
                file.save(temp_path)
                image_saved = True

        if not image_saved:
            b64_data = request.form.get('image_base64') or (request.json.get('image_base64') if request.is_json else None)
            if b64_data:
                import base64
                if ',' in b64_data:
                    b64_data = b64_data.split(',')[1]
                with open(temp_path, 'wb') as f:
                    f.write(base64.b64decode(b64_data))
                image_saved = True

        if not image_saved:
            return jsonify({'error': 'No image provided. Please capture or upload a classroom photo.'}), 400

        try:
            detection_range = request.form.get('detection_range', '50m') or (request.json.get('detection_range') if request.is_json else '50m')
            students = Student.query.filter_by(class_id=int(class_id)).all()
            student_count = len(students)

            if FACE_API_AVAILABLE:
                att_result = process_classroom_attendance(
                    image_input=temp_path,
                    db_session=db.session,
                    organization_id=int(session.get('org_id')),
                    class_id=int(class_id),
                    subject_id=subj_id_int,
                    detection_range=detection_range,
                    student_count=student_count
                )
            else:
                att_result = legacy_process_classroom_attendance(
                    image_path=temp_path,
                    db_session=db.session,
                    organization_id=int(session.get('org_id')),
                    class_id=int(class_id),
                    subject_id=subj_id_int,
                    detection_range=detection_range,
                    student_count=student_count
                )

            if 'error' in att_result and not att_result.get('recognized'):
                return jsonify(att_result), 400

            recognized_students = att_result.get('recognized', [])
            stats = att_result.get('stats', {})

            # --- SMS Notification for Absent Students ---
            today = india_now().date()
            class_info = Class_.query.get(int(class_id))
            class_name = class_info.name if class_info else ''
            recognized_roll_numbers = {s['roll_number'] for s in recognized_students}
            for student in students:
                if student.roll_number not in recognized_roll_numbers:
                    try:
                        from scripts.sms_helper import send_absent_sms
                        send_absent_sms(
                            student_name=student.name,
                            roll_number=student.roll_number,
                            phone=student.phone or '',
                            class_name=class_name,
                            absence_date=today,
                            student_email=student.email or ''
                        )
                    except Exception as sms_err:
                        print(f"[SMS ERROR] Could not send for {student.name}: {sms_err}")

            return jsonify({
                'success': f'Attendance marked for {len(recognized_students)} students',
                'recognized': recognized_students,
                'unknown': att_result.get('unknown', []),
                'stats': stats,
                'annotated_image': att_result.get('annotated_image'),
                'detection_range': att_result.get('detection_range', detection_range),
                'distance_meters': att_result.get('distance_meters', 50),
                'total_faces_detected': stats.get('detected', 0),
                'faces_detected': stats.get('detected', 0),
                'unknown_faces': stats.get('unknown', 0)
            })
        except Exception as e:
            import traceback
            print(f"ERROR in institution_mark_attendance: {e}")
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500

    return render_template('institution/mark_attendance.html', classes=classes, subjects=subjects, course_id=course_id, year=year)

@app.route('/institution/attendance-records')
@org_required(['institution'])
def institution_attendance_records():
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    
    cls_query = Class_.query.filter_by(organization_id=session.get('org_id'))
    if course_id: cls_query = cls_query.filter_by(course_id=course_id)
    if year: cls_query = cls_query.filter_by(study_year=year)
    classes = cls_query.all()
    class_id = request.args.get('class_id')
    date_str = request.args.get('date')
    month_str = request.args.get('month')

    query = Attendance.query.join(Class_).filter(Class_.organization_id == int(session.get('org_id')))
    if class_id:
        query = query.filter(Attendance.class_id == class_id)
    date_obj = None
    if date_str:
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            query = query.filter(Attendance.date == date_obj)
        except ValueError:
            pass
    if month_str:
        try:
            from calendar import monthrange
            from datetime import date
            y_val, m_val = map(int, month_str.split('-'))
            _, last_day = monthrange(y_val, m_val)
            query = query.filter(Attendance.date.between(date(y_val, m_val, 1), date(y_val, m_val, last_day)))
        except Exception:
            pass

    # If class_id and date_str are both provided, show ALL students of that class (including virtual absent ones)
    if class_id and date_obj:
        students = Student.query.filter_by(class_id=int(class_id)).all()
        
        # Find all unique subjects for which attendance was taken for this class on this date
        subjects_taken = db.session.query(Attendance.subject_id).filter_by(class_id=int(class_id), date=date_obj).distinct().all()
        subjects_taken = [s[0] for s in subjects_taken]
        
        if not subjects_taken:
            subjects_taken = [None]
            
        records = []
        for subj_id in subjects_taken:
            present_records = Attendance.query.filter_by(class_id=int(class_id), date=date_obj, subject_id=subj_id).all()
            present_student_ids = {r.student_id: r for r in present_records}
            
            for s in students:
                if s.id in present_student_ids:
                    records.append(present_student_ids[s.id])
                else:
                    from types import SimpleNamespace
                    subj = Subject.query.get(subj_id) if subj_id else None
                    absent_rec = SimpleNamespace(
                        id=None,
                        date=date_obj,
                        day=date_obj.strftime('%A'),
                        time=None,
                        status='absent',
                        student=s,
                        class_=s.class_,
                        subject=subj
                    )
                    records.append(absent_rec)
    else:
        records = query.order_by(Attendance.date.desc(), Attendance.time.desc()).all()
        
    return render_template('institution/attendance_records.html', records=records, classes=classes, selected_class=class_id, selected_date=date_str, selected_month=month_str)

@app.route('/institution/reports', methods=['GET', 'POST'])
@org_required(['institution'])
def institution_reports():
    if request.method == 'POST':
        report_type = request.form.get('report_type', 'student')
        student_id = request.form.get('student_id')
        class_id = request.form.get('class_id')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'],
                                     fontSize=16, spaceAfter=20)
        normal_style = styles['Normal']
        
        present_style = ParagraphStyle(
            'PresentStyle',
            parent=normal_style,
            textColor=colors.HexColor('#2e7d32'),
            fontName='Helvetica-Bold',
            alignment=1
        )
        absent_style = ParagraphStyle(
            'AbsentStyle',
            parent=normal_style,
            textColor=colors.HexColor('#c62828'),
            fontName='Helvetica-Bold',
            alignment=1
        )
        
        if report_type == 'class':
            elements.append(Paragraph("Class Attendance Report", title_style))
            if class_id:
                class_ = Class_.query.get(int(class_id))
                elements.append(Paragraph(f"Class: {class_.name}", normal_style))
                if start_date and end_date:
                    elements.append(Paragraph(f"Period: {start_date} to {end_date}", normal_style))
                elements.append(Spacer(1, 0.2*inch))
                
                # Fetch class students
                students = Student.query.filter_by(class_id=int(class_id)).order_by(Student.roll_number, Student.name).all()
                
                # Fetch present records
                att_query = Attendance.query.filter_by(class_id=int(class_id))
                if start_date and end_date:
                    att_query = att_query.filter(Attendance.date.between(start_date, end_date))
                present_attendances = att_query.all()
                
                # Get unique sessions (date, subject_id)
                sessions = sorted(list(set((att.date, att.subject_id) for att in present_attendances)), key=lambda x: (x[0], x[1] or 0), reverse=True)
                
                present_table_data = [['S.No', 'Date', 'Roll No', 'Student Name', 'Subject', 'Status']]
                absent_table_data = [['S.No', 'Date', 'Roll No', 'Student Name', 'Subject', 'Status']]
                
                pres_sno = 1
                abs_sno = 1
                
                for session_date, subj_id in sessions:
                    session_present = [att for att in present_attendances if att.date == session_date and att.subject_id == subj_id]
                    present_map = {att.student_id: att for att in session_present}
                    
                    subj_name = '-'
                    if subj_id:
                        subj_obj = Subject.query.get(subj_id)
                        if subj_obj:
                            subj_name = subj_obj.name
                            
                    for s in students:
                        if s.id in present_map:
                            present_table_data.append([
                                str(pres_sno),
                                str(session_date),
                                s.roll_number,
                                s.name,
                                subj_name,
                                Paragraph('Present', present_style)
                            ])
                            pres_sno += 1
                        else:
                            absent_table_data.append([
                                str(abs_sno),
                                str(session_date),
                                s.roll_number,
                                s.name,
                                subj_name,
                                Paragraph('Absent', absent_style)
                            ])
                            abs_sno += 1
                            
                has_records = False
                
                # Add Absent Students List
                if len(absent_table_data) > 1:
                    elements.append(Paragraph("Absent Students List (S.No wise)", ParagraphStyle('SubTitleAbs', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#c62828'), spaceAfter=10)))
                    abs_table = Table(absent_table_data)
                    abs_table.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#c62828')),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0,0), (-1,0), 10),
                        ('BOTTOMPADDING', (0,0), (-1,0), 8),
                        ('TOPPADDING', (0,0), (-1,0), 8),
                        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#bdc3c7')),
                        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#fff5f5')])
                    ]))
                    elements.append(abs_table)
                    has_records = True
                    
                # Add Present Students List
                if len(present_table_data) > 1:
                    if has_records:
                        elements.append(Spacer(1, 0.3*inch))
                    elements.append(Paragraph("Present Students List (S.No wise)", ParagraphStyle('SubTitlePres', parent=styles['Heading2'], fontSize=14, textColor=colors.HexColor('#2e7d32'), spaceAfter=10)))
                    pres_table = Table(present_table_data)
                    pres_table.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2e7d32')),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0,0), (-1,0), 10),
                        ('BOTTOMPADDING', (0,0), (-1,0), 8),
                        ('TOPPADDING', (0,0), (-1,0), 8),
                        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#bdc3c7')),
                        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f5fff5')])
                    ]))
                    elements.append(pres_table)
                    has_records = True
                    
                if not has_records:
                    elements.append(Paragraph("No attendance records found.", normal_style))
        else:
            elements.append(Paragraph("Student Attendance Report", title_style))
            if student_id:
                student = Student.query.get(int(student_id))
                elements.append(Paragraph(f"Student: {student.name}", normal_style))
                elements.append(Paragraph(f"Roll Number: {student.roll_number}", normal_style))
                if start_date and end_date:
                    elements.append(Paragraph(f"Period: {start_date} to {end_date}", normal_style))
                elements.append(Spacer(1, 0.2*inch))
                
                # Header row for main table
                data = [['Date', 'Time', 'Subject', 'Status']]
                
                # Get the class sessions for the student's class
                att_query = Attendance.query.filter_by(class_id=student.class_id)
                if start_date and end_date:
                    att_query = att_query.filter(Attendance.date.between(start_date, end_date))
                class_attendances = att_query.all()
                
                sessions = sorted(list(set((att.date, att.subject_id) for att in class_attendances)), key=lambda x: (x[0], x[1] or 0), reverse=True)
                student_present_map = {(att.date, att.subject_id): att for att in class_attendances if att.student_id == student.id}
                
                for session_date, subj_id in sessions:
                    subj_name = '-'
                    if subj_id:
                        subj_obj = Subject.query.get(subj_id)
                        if subj_obj:
                            subj_name = subj_obj.name
                            
                    if (session_date, subj_id) in student_present_map:
                        att = student_present_map[(session_date, subj_id)]
                        data.append([
                            str(session_date),
                            att.time.strftime('%H:%M:%S') if att.time else '-',
                            subj_name,
                            Paragraph('Present', present_style)
                        ])
                    else:
                        data.append([
                            str(session_date),
                            '-',
                            subj_name,
                            Paragraph('Absent', absent_style)
                        ])

                if len(data) > 1:
                    table = Table(data)
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1a252f')),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
                        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0,0), (-1,0), 11),
                        ('BOTTOMPADDING', (0,0), (-1,0), 8),
                        ('TOPPADDING', (0,0), (-1,0), 8),
                        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#bdc3c7')),
                        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8f9fa')])
                    ]))
                    elements.append(table)
                else:
                    elements.append(Paragraph("No attendance records found.", normal_style))

        doc.build(elements)
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name='attendance_report.pdf',
                         mimetype='application/pdf')
    
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    cls_query = Class_.query.filter_by(organization_id=session.get('org_id'))
    if course_id: cls_query = cls_query.filter_by(course_id=course_id)
    if year: cls_query = cls_query.filter_by(study_year=year)
    classes = cls_query.all()
    class_ids = [c.id for c in classes]
    if class_ids:
        students = Student.query.filter(Student.class_id.in_(class_ids)).all()
    else:
        students = []
    return render_template('institution/reports.html', students=students, classes=classes)

# Student Portal
@app.route('/student/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def student_login():
    if request.method == 'POST':
        identifier = (request.form.get('roll_number') or request.form.get('identifier') or request.form.get('phone') or '').strip()
        password = request.form.get('password', '')

        # Match by phone, roll number, username, or email
        student = Student.query.filter(
            (Student.phone == identifier) | 
            (Student.roll_number == identifier) | 
            (Student.username == identifier) | 
            (Student.email == identifier)
        ).first()

        if student:
            authenticated = False
            if student.password:
                if check_password_hash(student.password, password):
                    authenticated = True
                elif student.password == password:
                    authenticated = True
            elif not student.password and password in ['student123', 'password', '123456']:
                authenticated = True

            if authenticated:
                session.clear()
                session['student_id'] = student.id
                session['student_name'] = student.name
                session['role'] = 'student'
                session['org_id'] = student.organization_id
                if student.organization:
                    session['org_name'] = student.organization.name
                    session['org_type'] = getattr(student.organization, 'type', 'school') or 'school'
                flash(f'Welcome, {student.name}!', 'success')
                return redirect(url_for('student_dashboard'))

        flash('Invalid credentials. Please check your Roll Number / Phone / Email and try again.', 'danger')

    return render_template('student/login.html')

@app.route('/student/register', methods=['GET', 'POST'])
def student_register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        org_email = request.form.get('org_email')
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')

        if not all([name, email, phone, org_email, password, confirm]):
            flash('All fields are required.', 'danger')
            return render_template('student_register.html')

        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('student_register.html')

        # Look up organization by org_email (admin user email or organization email)
        org = None
        admin_user = User.query.filter_by(email=org_email).first()
        if admin_user:
            org = admin_user.organization
        else:
            org = None

        if not org:
            flash('Organization with email not found. Please check organization email.', 'danger')
            return render_template('student_register.html')

        # Check if student email/phone is already registered
        # Check if student is already registered in DB (e.g. by admin)
        existing_student = Student.query.filter_by(phone=phone).first()
        if not existing_student and email:
            existing_student = Student.query.filter_by(email=email).first()

        if existing_student:
            if existing_student.password:
                flash('Account already registered. Please login.', 'danger')
                return redirect(url_for('student_login'))
            else:
                # Update existing student's credentials with their chosen password
                existing_student.email = email
                existing_student.password = generate_password_hash(password)
                if not existing_student.username and email:
                    existing_student.username = email.split('@')[0]
                db.session.commit()
                flash('Registration complete! You can now login.', 'success')
                return redirect(url_for('student_login'))

        # Get or create a default class for this organization to satisfy database constraints
        class_ = Class_.query.filter_by(organization_id=org.id).first()
        if not class_:
            class_ = Class_(
                name='General Class',
                academic_year=india_now().strftime('%Y'),
                organization_id=org.id
            )
            db.session.add(class_)
            db.session.commit()

        # Generate a unique roll number
        import random
        random_suffix = ''.join(random.choices('0123456789', k=4))
        roll_number = f"STU-{india_now().strftime('%y')}-{random_suffix}"

        student = Student(
            name=name,
            username=email.split('@')[0],
            email=email,
            roll_number=roll_number,
            phone=phone,
            password=generate_password_hash(password),
            organization_id=org.id,
            class_id=class_.id
        )
        db.session.add(student)
        db.session.commit()

        flash('Registration successful! You can now login.', 'success')
        return redirect(url_for('student_login'))

    return render_template('student_register.html')

@app.route('/student/get-classes')
def student_get_classes():
    """AJAX endpoint: returns classes for a given org_id"""
    org_id = request.args.get('org_id')
    classes = Class_.query.filter_by(organization_id=org_id).all() if org_id else []
    return jsonify([{'id': c.id, 'name': c.name} for c in classes])

@app.route('/student/dashboard')
def student_dashboard():
    if 'student_id' not in session:
        flash('Please login to access your student dashboard.', 'warning')
        return redirect(url_for('student_login'))

    student = Student.query.get(session['student_id'])
    if not student:
        session.clear()
        flash('Student account not found. Please log in again.', 'warning')
        return redirect(url_for('student_login'))

    class_id = student.class_id
    
    # Query distinct (date, subject_id) where attendance was marked for this class
    sessions = db.session.query(Attendance.date, Attendance.subject_id).filter_by(class_id=class_id).distinct().all()
    
    # Query the student's actual attendance records
    student_att = Attendance.query.filter_by(student_id=student.id).all()
    # Map them for quick lookup: (date, subject_id) -> record
    att_map = {}
    for att in student_att:
        att_map[(att.date, att.subject_id)] = att
        
    # Build complete attendance history
    history = []
    present_count = 0
    total_attendance = 0
    
    for date_val, subj_id in sessions:
        total_attendance += 1
        att_record = att_map.get((date_val, subj_id))
        if att_record:
            present_count += 1
            history.append(att_record)
        else:
            from types import SimpleNamespace
            subj = Subject.query.get(subj_id) if subj_id else None
            absent_rec = SimpleNamespace(
                date=date_val,
                day=date_val.strftime('%A'),
                time=None,
                status='absent',
                student=student,
                class_=student.class_,
                subject=subj
            )
            history.append(absent_rec)
            
    # Sort history by date descending
    history.sort(key=lambda x: x.date, reverse=True)
    
    absent_count = total_attendance - present_count
    attendance_pct = round((present_count / total_attendance * 100), 1) if total_attendance > 0 else 0
    
    # Calculate monthly statistics
    today = india_now().date()
    start_of_month = today.replace(day=1)
    
    monthly_total = 0
    monthly_present = 0
    for h in history:
        if h.date >= start_of_month:
            monthly_total += 1
            if h.status == 'present':
                monthly_present += 1
                
    recent_history = history[:30]

    # Today's timetable slots in chronological order
    today_day = india_now().strftime('%A')
    today_slots = Timetable.query.filter_by(
        class_id=class_id, 
        day_of_week=today_day
    ).order_by(Timetable.start_time).all() if class_id else []

    # Upcoming Assignments for student's class
    upcoming_assignments = Assignment.query.filter(
        Assignment.class_id == class_id,
        Assignment.deadline >= india_now()
    ).order_by(Assignment.deadline).limit(5).all() if class_id else []

    return render_template('student/dashboard.html',
                          student=student,
                          percentage=attendance_pct,
                          attendance_pct=attendance_pct,
                          present_count=present_count,
                          absent_count=absent_count,
                          total_attendance=total_attendance,
                          monthly_present=monthly_present,
                          monthly_total=monthly_total,
                          recent_attendance=recent_history,
                          records=recent_history,
                          today_day=today_day,
                          today_slots=today_slots,
                          upcoming_assignments=upcoming_assignments)

# Staff Portal Routes
@app.route('/staff/register', methods=['GET', 'POST'])
def staff_register():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        email = request.form.get('email')
        org_email = request.form.get('org_email')
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')

        if not all([name, phone, email, org_email, password, confirm]):
            flash('All fields are required.', 'danger')
            return render_template('staff_register.html')

        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('staff_register.html')

        # Find organization by admin user email or organization email
        org = None
        admin_user = User.query.filter_by(email=org_email).first()
        if admin_user:
            org = admin_user.organization
        else:
            org = None

        if not org:
            flash('Organization with email not found. Please contact your administrator.', 'danger')
            return render_template('staff_register.html')

        if Staff.query.filter_by(email=email).first():
            flash('Staff Email already registered. Please login.', 'danger')
            return redirect(url_for('staff_login'))

        staff = Staff(
            name=name,
            phone=phone,
            email=email,
            org_email=org_email,
            password_hash=generate_password_hash(password),
            organization_id=org.id
        )
        db.session.add(staff)
        db.session.commit()

        flash('Registration successful! You can now login.', 'success')
        return redirect(url_for('staff_login'))

    return render_template('staff_register.html')

@app.route('/staff/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def staff_login():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()
        password = (request.form.get('password') or '').strip()
        org_type = (request.form.get('org_type') or 'college').strip()
        role = (request.form.get('role') or 'staff').strip().lower()

        if not all([email, password]):
            flash('All fields are required.', 'danger')
            return redirect(url_for('staff_login'))

        # Enforce that HOD is ONLY for college and institution
        if role == 'hod' and org_type not in ['college', 'institution']:
            flash('HOD role is only available for College and Institutions.', 'warning')
            return redirect(url_for('staff_login'))

        if role == 'admin':
            # Check User table first
            user = User.query.filter((User.username == email) | (User.email == email)).first()
            if user and check_password_hash(user.password_hash, password):
                session.clear()
                session['user_id'] = user.id
                session['username'] = user.username
                session['org_type'] = user.org_type
                session['org_id'] = user.organization_id
                session['org_name'] = user.organization.name
                session['role'] = 'admin'
                session['is_admin'] = True
                flash(f'Welcome, Administrator {user.username}!', 'success')
                return redirect(url_for('campus.assistant'))

            # Check Staff with admin role
            staff = Staff.query.filter((Staff.email == email) | (Staff.phone == email)).first()
            if staff and check_password_hash(staff.password_hash, password):
                session.clear()
                session['staff_id'] = staff.id
                session['user_id'] = staff.id
                session['username'] = staff.name
                session['org_type'] = staff.organization.type
                session['org_id'] = staff.organization_id
                session['org_name'] = staff.organization.name
                session['role'] = 'admin'
                session['is_staff'] = True
                session['is_admin'] = True
                flash(f'Welcome, Admin {staff.name}!', 'success')
                return redirect(url_for('campus.assistant'))

            flash('Invalid admin credentials.', 'danger')
            return redirect(url_for('staff_login'))

        elif role == 'hod':
            staff = Staff.query.filter((Staff.email == email) | (Staff.phone == email) | (Staff.name == email)).first()
            if staff and check_password_hash(staff.password_hash, password):
                if staff.organization.type not in ['college', 'institution']:
                    flash('HOD role is only available for College and Institutions.', 'warning')
                    return redirect(url_for('staff_login'))
                session.clear()
                session['staff_id'] = staff.id
                session['user_id'] = staff.id
                session['username'] = staff.name
                session['org_type'] = staff.organization.type
                session['org_id'] = staff.organization_id
                session['org_name'] = staff.organization.name
                session['role'] = 'hod'
                session['is_staff'] = True
                session['is_hod'] = True
                if getattr(staff, 'role', None) != 'hod':
                    staff.role = 'hod'
                    db.session.commit()
                flash(f'Welcome, HOD {staff.name}!', 'success')
                if staff.organization.type == 'college':
                    return redirect(url_for('college_dashboard'))
                elif staff.organization.type == 'institution':
                    return redirect(url_for('institution_dashboard'))
                return redirect(url_for('staff_dashboard'))
            else:
                flash('Invalid credentials for HOD. Please check your email/mobile and password.', 'danger')
                return redirect(url_for('staff_login'))

        else:  # Staff role
            staff = Staff.query.filter((Staff.email == email) | (Staff.phone == email) | (Staff.name == email)).first()
            if staff and check_password_hash(staff.password_hash, password):
                session.clear()
                session['staff_id'] = staff.id
                session['username'] = staff.name
                session['org_type'] = staff.organization.type
                session['org_id'] = staff.organization_id
                session['org_name'] = staff.organization.name
                session['role'] = 'staff'
                session['is_staff'] = True
                flash(f'Welcome, {staff.name}!', 'success')
                return redirect(url_for('staff_dashboard'))
            else:
                flash('Invalid credentials. Please check your email and password.', 'danger')

    return render_template('staff_login.html')

@app.route('/staff/dashboard')
def staff_dashboard():
    if not session.get('is_staff'):
        flash('Please login as staff to access this page', 'danger')
        return redirect(url_for('staff_login'))
        
    staff_id = session.get('staff_id')
    staff = Staff.query.get(staff_id)
    if not staff:
        return redirect(url_for('staff_login'))
        
    # Find classes assigned to this staff member
    classes = Class_.query.filter_by(
        class_teacher=staff.name,
        organization_id=staff.organization_id
    ).all()
    
    total_classes = len(classes)
    total_students = sum(len(c.students) for c in classes)
    
    # Calculate today's attendance for these classes
    today = india_now().date()
    today_attendance = 0
    for class_ in classes:
        today_attendance += Attendance.query.filter_by(class_id=class_.id, date=today).count()
        
    staff_face_count = StaffFaceEncoding.query.filter_by(staff_id=staff.id).count()
    staff_today_attendance = StaffAttendance.query.filter_by(staff_id=staff.id, date=today).first()
        
    return render_template(
        'staff/dashboard.html',
        classes=classes,
        total_classes=total_classes,
        total_students=total_students,
        today_attendance=today_attendance,
        staff_face_count=staff_face_count,
        staff_today_attendance=staff_today_attendance
    )



# ============================================================
# STAFF / FACULTY BIOMETRIC & ATTENDANCE WITH GPS ROUTES
# ============================================================

@app.route('/staff/face-register', methods=['GET'])
@staff_required
def staff_face_register():
    staff_id = session.get('staff_id')
    staff = Staff.query.get(staff_id)
    if not staff:
        return redirect(url_for('staff_login'))
    
    encodings = StaffFaceEncoding.query.filter_by(staff_id=staff.id).all()
    encodings_count = len(encodings)
    registered_at = encodings[0].created_at if encodings else None
    
    return render_template(
        'staff/face_register.html',
        staff=staff,
        encodings_count=encodings_count,
        registered_at=registered_at
    )


@app.route('/staff/api/face-status', methods=['GET'])
@staff_required
def staff_api_face_status():
    staff_id = session.get('staff_id')
    count = StaffFaceEncoding.query.filter_by(staff_id=staff_id).count()
    return jsonify({
        'success': True,
        'has_face': count > 0,
        'encoding_count': count
    })


@app.route('/staff/api/register-face', methods=['POST'])
@csrf.exempt
@staff_required
def staff_api_register_face():
    """Register face encodings for logged-in staff member using SCRFD + ArcFace."""
    import base64, uuid
    data = request.get_json(force=True) if request.is_json else request.form
    staff_id = session.get('staff_id')
    staff = Staff.query.get(staff_id)
    if not staff:
        return jsonify({'success': False, 'error': 'Staff session not found.'}), 404

    images_b64 = data.get('images_base64', [])
    if not images_b64:
        return jsonify({'success': False, 'error': 'No facial images provided.'}), 400

    if not FACE_API_AVAILABLE:
        return jsonify({'success': False, 'error': 'Face recognition engine not available on this server.'}), 503

    pipeline = get_pipeline()
    success_count = 0
    errors = []

    for idx, img_b64 in enumerate(images_b64[:6]):
        try:
            if ',' in img_b64:
                img_b64 = img_b64.split(',', 1)[1]
            img_data = base64.b64decode(img_b64)
            filename = f"staff_face_{staff.id}_{uuid.uuid4().hex}.jpg"
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            with open(temp_path, 'wb') as f:
                f.write(img_data)

            from face_api.pipeline import decode_image
            image = decode_image(temp_path)
            if image is None:
                errors.append(f'Pose {idx+1}: Invalid image data')
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                continue

            faces = pipeline.detector.detect(image)
            if not faces:
                errors.append(f'Pose {idx+1}: No usable face detected. Please upload a clearer image.')
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                continue

            if len(faces) > 1:
                errors.append(f'Pose {idx+1}: Multiple faces detected. Please upload an image containing only this staff member.')
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                continue

            face = faces[0]
            quality_result = pipeline.quality_filter.evaluate(image, face)
            if not quality_result.is_valid:
                errors.append(f'Pose {idx+1}: Quality rejected ({quality_result.reason})')
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                continue

            face_enc = pipeline.recognizer.extract_embedding(image, face.landmarks)
            record = StaffFaceEncoding(
                staff_id=staff.id,
                encoding_path="",
                encoding_data=face_enc.tolist(),
                created_at=datetime.utcnow()
            )
            db.session.add(record)
            success_count += 1
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except Exception as e:
            errors.append(f'Pose {idx+1}: {str(e)}')

    if success_count == 0:
        return jsonify({'success': False, 'error': 'No face registered. ' + '; '.join(errors)}), 400

    db.session.commit()
    msg = f"{success_count} ArcFace biometric sample(s) registered successfully for {staff.name}!"
    if errors:
        msg += " (Notes: " + '; '.join(errors) + ")"
    
    # Audit log
    audit = AuditLog(
        organization_id=staff.organization_id,
        user_id=session.get('user_id'),
        action='Staff Face Registration',
        ip_address=request.remote_addr,
        details=f'Biometric profile registered for faculty {staff.name} ({success_count} ArcFace samples)'
    )
    db.session.add(audit)
    db.session.commit()

    return jsonify({'success': True, 'message': msg, 'encoding_count': success_count})


@app.route('/staff/api/delete-face', methods=['POST'])
@csrf.exempt
@staff_required
def staff_api_delete_face():
    staff_id = session.get('staff_id')
    staff = Staff.query.get(staff_id)
    if not staff:
        return jsonify({'success': False, 'error': 'Staff not found.'}), 404
    
    deleted = StaffFaceEncoding.query.filter_by(staff_id=staff.id).delete()
    db.session.commit()
    return jsonify({
        'success': True,
        'message': f'Face biometric data cleared ({deleted} records removed). You can now re-enroll.'
    })


@app.route('/staff/mark-attendance', methods=['GET'])
@staff_required
def staff_mark_attendance():
    staff_id = session.get('staff_id')
    staff = Staff.query.get(staff_id)
    if not staff:
        return redirect(url_for('staff_login'))

    today = india_now().date()
    today_record = StaffAttendance.query.filter_by(staff_id=staff.id, date=today).first()
    has_face = StaffFaceEncoding.query.filter_by(staff_id=staff.id).count() > 0

    recent_records = StaffAttendance.query.filter_by(staff_id=staff.id).order_by(
        StaffAttendance.date.desc(), StaffAttendance.time.desc()
    ).limit(10).all()

    return render_template(
        'staff/mark_attendance.html',
        staff=staff,
        today_record=today_record,
        has_face=has_face,
        recent_records=recent_records,
        today=today,
        now_time=india_now().strftime('%I:%M %p')
    )


@app.route('/staff/api/mark-attendance', methods=['POST'])
@csrf.exempt
@staff_required
def staff_api_mark_attendance():
    """Mark staff attendance with face verification + Geolocation."""
    import base64, uuid
    data = request.get_json(force=True) if request.is_json else request.form
    staff_id = session.get('staff_id')
    staff = Staff.query.get(staff_id)
    if not staff:
        return jsonify({'success': False, 'error': 'Staff not found.'}), 404

    image_b64 = data.get('image_base64')
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    accuracy = data.get('accuracy')
    location_name = data.get('location_name', 'Campus Location (GPS Verified)')

    if latitude is None or longitude is None or str(latitude).strip() == '' or str(longitude).strip() == '':
        return jsonify({
            'success': False,
            'error': 'Location access is required. Please grant GPS/Location permission in your browser.'
        }), 400

    try:
        lat_float = float(latitude)
        lng_float = float(longitude)
        acc_float = float(accuracy) if accuracy is not None and str(accuracy).strip() != '' else 0.0
    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid GPS coordinates format.'}), 400

    enc_records = StaffFaceEncoding.query.filter_by(staff_id=staff.id).all()
    if not enc_records:
        return jsonify({
            'success': False,
            'error': 'No registered face profile found for your account. Please complete Face Registration first.'
        }), 400

    known_512 = [
        np.array(rec.encoding_data, dtype=np.float32)
        for rec in enc_records
        if rec.encoding_data and len(rec.encoding_data) == 512
    ]
    legacy_128 = [
        np.array(rec.encoding_data, dtype=np.float64)
        for rec in enc_records
        if rec.encoding_data and len(rec.encoding_data) == 128
    ]

    if not known_512 and not legacy_128:
        return jsonify({
            'success': False,
            'error': 'Biometric profile corrupted. Please re-register your face.'
        }), 400

    if not image_b64:
        return jsonify({'success': False, 'error': 'No facial image captured by camera.'}), 400

    temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"staff_att_temp_{uuid.uuid4().hex}.jpg")
    try:
        if ',' in image_b64:
            image_b64 = image_b64.split(',', 1)[1]
        with open(temp_path, 'wb') as f:
            f.write(base64.b64decode(image_b64))

        if not FACE_API_AVAILABLE:
            return jsonify({'success': False, 'error': 'Face recognition engine not available on this server.'}), 503
        pipeline = get_pipeline()
        from face_api.pipeline import decode_image
        captured_img = decode_image(temp_path)
        if captured_img is None:
            return jsonify({'success': False, 'error': 'Invalid image captured by camera.'}), 400

        if known_512:
            # SCRFD Detection
            faces = pipeline.detector.detect(captured_img)
            if not faces:
                return jsonify({
                    'success': False,
                    'error': 'No face detected in camera view. Please align your face inside the circle with good lighting.'
                }), 400

            # Find best face
            best_face = max(faces, key=lambda f: (f.bbox[2]-f.bbox[0]) * (f.bbox[3]-f.bbox[1]))
            quality_result = pipeline.quality_filter.evaluate(captured_img, best_face)
            if not quality_result.is_valid:
                return jsonify({
                    'success': False,
                    'error': f'Image rejected: {quality_result.reason}. Please ensure good lighting and face camera directly.'
                }), 400

            candidate_enc = pipeline.recognizer.extract_embedding(captured_img, best_face.landmarks)
            # Cosine similarity against known 512-d encodings
            similarities = [float(np.dot(candidate_enc, k)) for k in known_512]
            best_sim = max(similarities)
            confidence = pipeline.matcher.similarity_to_confidence(best_sim)

            if best_sim < pipeline.matcher.threshold:
                return jsonify({
                    'success': False,
                    'error': f'Face verification failed. Captured face did not match your registered profile (Confidence: {confidence}%). Please ensure adequate lighting and face camera directly.'
                }), 400
        else:
            # Graceful legacy fallback if staff member has not re-registered yet
            legacy_img = face_recognition.load_image_file(temp_path)
            face_locations = face_recognition.face_locations(legacy_img, model='hog')
            if not face_locations:
                return jsonify({
                    'success': False,
                    'error': 'No face detected in camera view. Please align your face inside the circle with good lighting.'
                }), 400
            candidate_enc = face_recognition.face_encodings(legacy_img, [face_locations[0]])[0]
            matches = face_recognition.compare_faces(legacy_128, candidate_enc, tolerance=0.5)
            face_distances = face_recognition.face_distance(legacy_128, candidate_enc)
            min_dist = float(np.min(face_distances))
            confidence = max(0, min(100, round((1.0 - min_dist) * 100, 1)))
            if True not in matches:
                return jsonify({
                    'success': False,
                    'error': f'Face verification failed. Captured face did not match your registered profile (Confidence: {confidence}%).'
                }), 400

    except Exception as e:
        return jsonify({'success': False, 'error': f'Face processing error: {str(e)}'}), 500
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

    today = india_now().date()
    now_time = india_now().time()

    existing_record = StaffAttendance.query.filter_by(staff_id=staff.id, date=today).first()
    if existing_record:
        return jsonify({
            'success': True,
            'already_marked': True,
            'message': f'Attendance was already marked for today at {existing_record.time.strftime("%I:%M %p")}.',
            'time': existing_record.time.strftime('%I:%M:%S %p'),
            'date': existing_record.date.strftime('%b %d, %Y'),
            'latitude': existing_record.latitude,
            'longitude': existing_record.longitude,
            'location_name': existing_record.location_name,
            'accuracy': existing_record.accuracy_meters,
            'status': existing_record.status,
            'confidence': f'{confidence}%'
        })

    status_label = 'present'
    if now_time.hour > 9 or (now_time.hour == 9 and now_time.minute > 30):
        status_label = 'late'

    new_record = StaffAttendance(
        staff_id=staff.id,
        organization_id=staff.organization_id,
        date=today,
        time=now_time,
        status=status_label,
        latitude=lat_float,
        longitude=lng_float,
        location_name=location_name,
        accuracy_meters=acc_float,
        created_at=datetime.utcnow()
    )
    db.session.add(new_record)

    audit = AuditLog(
        organization_id=staff.organization_id,
        user_id=session.get('user_id'),
        action='Staff Attendance Checked In',
        ip_address=request.remote_addr,
        details=f'{staff.name} checked in at {now_time.strftime("%I:%M %p")} with GPS ({lat_float:.5f}, {lng_float:.5f}, ±{acc_float:.1f}m, status: {status_label})'
    )
    db.session.add(audit)
    db.session.commit()

    return jsonify({
        'success': True,
        'already_marked': False,
        'message': f'Attendance marked successfully for {staff.name}!',
        'time': now_time.strftime('%I:%M:%S %p'),
        'date': today.strftime('%b %d, %Y'),
        'latitude': lat_float,
        'longitude': lng_float,
        'accuracy': acc_float,
        'location_name': location_name,
        'status': status_label,
        'confidence': f'{confidence}%'
    })


@app.route('/staff/attendance-records', methods=['GET'])
@staff_required
def staff_attendance_records():
    staff_id = session.get('staff_id')
    staff = Staff.query.get(staff_id)
    if not staff:
        return redirect(url_for('staff_login'))

    month_filter = request.args.get('month', '')
    query = StaffAttendance.query.filter_by(staff_id=staff.id)
    if month_filter:
        try:
            year, month = map(int, month_filter.split('-'))
            query = query.filter(db.extract('year', StaffAttendance.date) == year,
                                 db.extract('month', StaffAttendance.date) == month)
        except Exception:
            pass

    records = query.order_by(StaffAttendance.date.desc(), StaffAttendance.time.desc()).all()
    
    total_present = len([r for r in records if r.status in ['present', 'on-time']])
    total_late = len([r for r in records if r.status == 'late'])
    total_days = len(records)

    return render_template(
        'staff/attendance_records.html',
        staff=staff,
        records=records,
        total_present=total_present,
        total_late=total_late,
        total_days=total_days,
        month_filter=month_filter
    )


@app.route('/<org_type>/staff-attendance', methods=['GET'])
@org_required(['school', 'college', 'institution'])
def admin_staff_attendance(org_type):
    org_id = session.get('org_id')
    date_str = request.args.get('date', india_now().strftime('%Y-%m-%d'))
    try:
        selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except Exception:
        selected_date = india_now().date()

    staff_members = Staff.query.filter_by(organization_id=org_id).order_by(Staff.name).all()
    records = StaffAttendance.query.filter_by(organization_id=org_id, date=selected_date).all()
    records_by_staff = {r.staff_id: r for r in records}

    staff_data = []
    present_count = 0
    late_count = 0
    for s in staff_members:
        rec = records_by_staff.get(s.id)
        if rec:
            if rec.status == 'late':
                late_count += 1
            else:
                present_count += 1
        has_face = StaffFaceEncoding.query.filter_by(staff_id=s.id).count() > 0
        staff_data.append({
            'staff': s,
            'attendance': rec,
            'has_face': has_face
        })

    return render_template(
        'staff/admin_staff_attendance.html',
        org_type=org_type,
        selected_date=selected_date,
        staff_data=staff_data,
        total_staff=len(staff_members),
        present_count=present_count,
        late_count=late_count,
        absent_count=max(0, len(staff_members) - (present_count + late_count))
    )


# Password Reset / OTP Recovery Routes
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        if not email:
            flash('Email is required.', 'danger')
            return render_template('forgot_password.html')

        # Check if the email exists in User or Staff or Student
        exists = (
            User.query.filter_by(email=email).first() or
            Staff.query.filter_by(email=email).first() or
            Student.query.filter_by(email=email).first()
        )

        if not exists:
            flash('No user, staff, or student found with that email address.', 'danger')
            return render_template('forgot_password.html')

        # Generate a random 6-digit OTP
        otp = str(random.randint(100000, 999999))
        
        # Save or update OTPVerification entry
        otp_entry = OTPVerification.query.filter_by(email=email).first()
        if not otp_entry:
            otp_entry = OTPVerification(email=email)
        otp_entry.otp = otp
        otp_entry.is_verified = False
        db.session.add(otp_entry)
        db.session.commit()

        # Send OTP email
        smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com').strip()
        smtp_port = int(os.environ.get('SMTP_PORT', 465))
        smtp_username = os.environ.get('SMTP_USERNAME', '').strip()
        smtp_password = os.environ.get('SMTP_PASSWORD', '').strip()

        if smtp_username and smtp_password:
            try:
                import ssl
                msg = EmailMessage()
                msg.set_content(f'Your password reset OTP is: {otp}\nPlease use this OTP to reset your password.')
                msg['Subject'] = 'CampusAI App - Password Reset OTP'
                msg['From'] = smtp_username
                msg['To'] = email

                context = ssl.create_default_context()
                # Try SMTP_SSL (port 465) first, fall back to STARTTLS (port 587)
                try:
                    server = smtplib.SMTP_SSL(smtp_server, 465, context=context)
                    server.login(smtp_username, smtp_password)
                    server.send_message(msg)
                    server.quit()
                except Exception:
                    server = smtplib.SMTP(smtp_server, 587)
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                    server.login(smtp_username, smtp_password)
                    server.send_message(msg)
                    server.quit()
                flash('An OTP has been sent to your email.', 'success')
            except smtplib.SMTPAuthenticationError:
                print(f"SMTP Auth Error: App Password is invalid or expired. Generate a new one at https://myaccount.google.com/apppasswords")
                flash('Email authentication failed. Please contact the admin to update the SMTP App Password.', 'danger')
            except Exception as e:
                print(f"Error sending email: {e}")
                flash(f'Failed to send email. Please try again later.', 'danger')
        else:
            flash('Email service is not configured. Please contact the admin.', 'danger')

        session['reset_email'] = email
        return redirect(url_for('verify_otp'))

    return render_template('forgot_password.html')

@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    email = session.get('reset_email')
    if not email:
        flash('Please request an OTP first.', 'warning')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        otp = request.form.get('otp')
        if not otp:
            flash('OTP is required.', 'danger')
            return render_template('verify_otp.html', email=email)

        otp_entry = OTPVerification.query.filter_by(email=email).first()
        if otp_entry and otp_entry.otp == otp:
            otp_entry.is_verified = True
            db.session.commit()
            flash('OTP verified successfully! You can now reset your password.', 'success')
            return redirect(url_for('reset_password'))
        else:
            flash('Invalid OTP. Please check the code and try again.', 'danger')

    return render_template('verify_otp.html', email=email)

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    email = session.get('reset_email')
    if not email:
        flash('Please request an OTP first.', 'warning')
        return redirect(url_for('forgot_password'))

    otp_entry = OTPVerification.query.filter_by(email=email).first()
    if not otp_entry or not otp_entry.is_verified:
        flash('Please verify your OTP first.', 'warning')
        return redirect(url_for('verify_otp'))

    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not new_password or not confirm_password:
            flash('All password fields are required.', 'danger')
            return render_template('reset_password.html')

        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html')

        # Update password for whichever account matches this email
        hashed = generate_password_hash(new_password)
        updated = False

        user = User.query.filter_by(email=email).first()
        if user:
            user.password_hash = hashed
            updated = True

        staff = Staff.query.filter_by(email=email).first()
        if staff:
            staff.password_hash = hashed
            updated = True

        student = Student.query.filter_by(email=email).first()
        if student:
            student.password = hashed
            updated = True

        if updated:
            db.session.delete(otp_entry)
            db.session.commit()
            session.pop('reset_email', None)
            flash('Password reset successfully! You can now login.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Error resetting password. User not found.', 'danger')

    return render_template('reset_password.html')

@app.route('/capture-cctv', methods=['POST'])
def capture_cctv():
    import base64
    import cv2
    from flask import jsonify, request
    
    data = request.get_json() or {}
    url = data.get('url')
    if not url:
        return jsonify({'error': 'Camera URL is required'}), 400
        
    try:
        # Try converting to integer if it's a digit (local webcam index)
        if url.isdigit():
            url = int(url)
            
        cap = cv2.VideoCapture(url)
        if not cap.isOpened():
            return jsonify({'error': 'Could not open CCTV stream or Local index. Check URL/index.'}), 400
            
        success, frame = cap.read()
        cap.release()
        
        if not success:
            return jsonify({'error': 'Failed to capture frame.'}), 400
            
        _, buffer = cv2.imencode('.jpg', frame)
        img_base64 = base64.b64encode(buffer).decode('utf-8')
        
        return jsonify({
            'success': True,
            'image': 'data:image/jpeg;base64,' + img_base64
        })
    except Exception as e:
        return jsonify({'error': f'Error accessing camera: {str(e)}'}), 500

@app.route('/api/timetable/current-subject/<int:class_id>', methods=['GET'])
def get_current_timetable_subject(class_id):
    now = india_now()
    day_name = now.strftime('%A')
    current_time_str = now.strftime('%H:%M')
    
    slots = Timetable.query.filter_by(class_id=class_id, day_of_week=day_name).all()
    active_subject = None
    matched_slot = None
    
    for slot in slots:
        if slot.start_time and slot.end_time:
            st = slot.start_time.strip()
            et = slot.end_time.strip()
            if len(st) == 4 and ':' in st: st = '0' + st
            if len(et) == 4 and ':' in et: et = '0' + et
            if st <= current_time_str <= et:
                active_subject = slot.subject_name
                matched_slot = {
                    'id': slot.id,
                    'subject_name': slot.subject_name,
                    'start_time': slot.start_time,
                    'end_time': slot.end_time,
                    'room': slot.room,
                    'faculty': slot.faculty
                }
                break
                
    if not active_subject and slots:
        active_subject = slots[0].subject_name

    all_class_slots = Timetable.query.filter_by(class_id=class_id).all()
    subject_list = list(set([s.subject_name for s in all_class_slots if s.subject_name]))
    
    return jsonify({
        'success': True,
        'day': day_name,
        'current_time': current_time_str,
        'active_subject': active_subject or '',
        'matched_slot': matched_slot,
        'all_subjects': subject_list
    })

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('splash'))

@app.route('/init-db')
def init_db():
    """Initialize database with default data"""
    db.create_all()

    # Automatic migration to add encoding_data JSON column if not exists
    try:
        from sqlalchemy import text
        db.session.execute(text("ALTER TABLE face_encoding ADD COLUMN encoding_data JSON"))
        db.session.commit()
    except Exception as e:
        db.session.rollback()

    # Create default organizations if they don't exist
    defaults = [
        ('SMVIT School', 'school', 'smvit_school', 'school123'),
        ('SMVIT College', 'college', 'smvit_college', 'college123'),
        ('SMVIT Institution', 'institution', 'smvit_institution', 'institution123')
    ]

    for org_name, org_type, username, password in defaults:
        org = Organization.query.filter_by(name=org_name).first()
        if not org:
            org = Organization(name=org_name, type=org_type)
            db.session.add(org)
            db.session.commit()

            user = User(
                username=username,
                email=f'{username}@example.com',
                password_hash=generate_password_hash(password),
                org_type=org_type,
                organization_id=org.id
            )
            db.session.add(user)
            db.session.commit()

    return "Database initialized successfully!"

# ==========================================
# DELETE ROUTES - GENERAL & ORGANIZATION-SPECIFIC
# ==========================================

# --- SCHOOL DELETE ROUTES ---
@app.route('/school/delete-class/<int:class_id>')
@org_required(['school'])
def school_delete_class(class_id):
    org_id = session.get('org_id')
    class_ = Class_.query.filter_by(id=class_id, organization_id=org_id).first_or_404()
    
    # 1. Delete all student face encodings and attendances
    students = Student.query.filter_by(class_id=class_.id).all()
    for student in students:
        FaceEncoding.query.filter_by(student_id=student.id).delete()
        Attendance.query.filter_by(student_id=student.id).delete()
        db.session.delete(student)
        
    # 2. Delete all attendance records of the class
    Attendance.query.filter_by(class_id=class_.id).delete()
    
    db.session.delete(class_)
    db.session.commit()
    flash('Class and all its students/attendance records deleted successfully.', 'success')
    return redirect(url_for('school_classes'))


@app.route('/school/delete-student/<int:student_id>')
@org_required(['school'])
def school_delete_student(student_id):
    org_id = session.get('org_id')
    student = Student.query.filter_by(id=student_id, organization_id=org_id).first_or_404()
    
    # Delete face encodings and attendance
    FaceEncoding.query.filter_by(student_id=student.id).delete()
    Attendance.query.filter_by(student_id=student.id).delete()
    
    db.session.delete(student)
    db.session.commit()
    flash('Student and all their records deleted successfully.', 'success')
    return redirect(url_for('school_students'))

# --- SCHOOL EDIT (RENAME) ROUTES ---
@app.route('/school/edit-class/<int:class_id>', methods=['POST'])
@org_required(['school'])
def school_edit_class(class_id):
    org_id = session.get('org_id')
    class_ = Class_.query.filter_by(id=class_id, organization_id=org_id).first_or_404()
    class_.name = request.form.get('class_name', class_.name)
    class_.academic_year = request.form.get('academic_year', class_.academic_year)
    class_.class_teacher = request.form.get('class_teacher', class_.class_teacher)
    db.session.commit()
    flash('Class updated successfully.', 'success')
    return redirect(url_for('school_classes'))

@app.route('/school/edit-student/<int:student_id>', methods=['POST'])
@org_required(['school'])
def school_edit_student(student_id):
    org_id = session.get('org_id')
    student = Student.query.filter_by(id=student_id, organization_id=org_id).first_or_404()
    student.name = request.form.get('name', student.name)
    student.roll_number = request.form.get('roll_number', student.roll_number)
    student.phone = request.form.get('phone', student.phone)
    db.session.commit()
    flash('Student updated successfully.', 'success')
    return redirect(url_for('school_students'))




# --- COLLEGE DELETE ROUTES ---
@app.route('/college/delete-course/<int:course_id>')
@org_required(['college'])
def college_delete_course(course_id):
    org_id = session.get('org_id')
    course = Course.query.filter_by(id=course_id, organization_id=org_id).first_or_404()
    
    # 1. Delete all classes under this course (which cascades to students, attendances, face encodings)
    classes = Class_.query.filter_by(course_id=course.id).all()
    for class_ in classes:
        students = Student.query.filter_by(class_id=class_.id).all()
        for student in students:
            FaceEncoding.query.filter_by(student_id=student.id).delete()
            Attendance.query.filter_by(student_id=student.id).delete()
            db.session.delete(student)
        Attendance.query.filter_by(class_id=class_.id).delete()
        db.session.delete(class_)
        
    # 2. Delete subjects and their attendance
    subjects = Subject.query.filter_by(course_id=course.id).all()
    for subj in subjects:
        Attendance.query.filter_by(subject_id=subj.id).delete()
        db.session.delete(subj)
        
    # 3. Delete StudyYears
    StudyYear.query.filter_by(course_id=course.id).delete()
    
    db.session.delete(course)
    db.session.commit()
    flash('Course and all its classes, subjects, students, and attendance records deleted successfully.', 'success')
    return redirect(url_for('college_dashboard'))

@app.route('/college/delete-year/<int:year_id>')
@org_required(['college'])
def college_delete_year(year_id):
    org_id = session.get('org_id')
    study_year = StudyYear.query.filter_by(id=year_id, organization_id=org_id).first_or_404()
    course_id = study_year.course_id
    
    db.session.delete(study_year)
    db.session.commit()
    flash('Study Year deleted successfully.', 'success')
    return redirect(url_for('college_dashboard', course_id=course_id))

@app.route('/college/delete-subject/<int:subject_id>')
@org_required(['college'])
def college_delete_subject(subject_id):
    org_id = session.get('org_id')
    subject = Subject.query.filter_by(id=subject_id, organization_id=org_id).first_or_404()
    
    # Delete subject attendances
    Attendance.query.filter_by(subject_id=subject.id).delete()
    
    db.session.delete(subject)
    db.session.commit()
    flash('Subject and its attendance records deleted successfully.', 'success')
    return redirect(url_for('college_dashboard'))

@app.route('/college/delete-class/<int:class_id>')
@org_required(['college'])
def college_delete_class(class_id):
    org_id = session.get('org_id')
    class_ = Class_.query.filter_by(id=class_id, organization_id=org_id).first_or_404()
    course_id = class_.course_id
    year = class_.study_year
    
    students = Student.query.filter_by(class_id=class_.id).all()
    for student in students:
        FaceEncoding.query.filter_by(student_id=student.id).delete()
        Attendance.query.filter_by(student_id=student.id).delete()
        db.session.delete(student)
    Attendance.query.filter_by(class_id=class_.id).delete()
    
    db.session.delete(class_)
    db.session.commit()
    flash('Class and all its students/attendance records deleted successfully.', 'success')
    return redirect(url_for('college_classes', course_id=course_id, year=year))

@app.route('/college/delete-student/<int:student_id>')
@org_required(['college'])
def college_delete_student(student_id):
    org_id = session.get('org_id')
    student = Student.query.filter_by(id=student_id, organization_id=org_id).first_or_404()
    class_ = Class_.query.get(student.class_id)
    course_id = class_.course_id if class_ else None
    year = class_.study_year if class_ else None
    
    FaceEncoding.query.filter_by(student_id=student.id).delete()
    Attendance.query.filter_by(student_id=student.id).delete()
    
    db.session.delete(student)
    db.session.commit()
    flash('Student deleted successfully.', 'success')
    return redirect(url_for('college_students', course_id=course_id, year=year))

# --- COLLEGE EDIT (RENAME) ROUTES ---
@app.route('/college/edit-course/<int:course_id>', methods=['POST'])
@org_required(['college'])
def college_edit_course(course_id):
    org_id = session.get('org_id')
    course = Course.query.filter_by(id=course_id, organization_id=org_id).first_or_404()
    course.name = request.form.get('name', course.name)
    db.session.commit()
    flash('Course updated successfully.', 'success')
    return redirect(url_for('college_courses'))

@app.route('/college/edit-class/<int:class_id>', methods=['POST'])
@org_required(['college'])
def college_edit_class(class_id):
    org_id = session.get('org_id')
    class_ = Class_.query.filter_by(id=class_id, organization_id=org_id).first_or_404()
    class_.name = request.form.get('class_name', class_.name)
    class_.academic_year = request.form.get('academic_year', class_.academic_year)
    db.session.commit()
    flash('Class updated successfully.', 'success')
    return redirect(url_for('college_classes', course_id=class_.course_id, year=class_.study_year))

@app.route('/college/edit-student/<int:student_id>', methods=['POST'])
@org_required(['college'])
def college_edit_student(student_id):
    org_id = session.get('org_id')
    student = Student.query.filter_by(id=student_id, organization_id=org_id).first_or_404()
    student.name = request.form.get('name', student.name)
    student.roll_number = request.form.get('roll_number', student.roll_number)
    student.phone = request.form.get('phone', student.phone)
    class_ = Class_.query.get(student.class_id)
    db.session.commit()
    flash('Student updated successfully.', 'success')
    return redirect(url_for('college_students', course_id=class_.course_id if class_ else None, year=class_.study_year if class_ else None))

@app.route('/college/edit-subject/<int:subject_id>', methods=['POST'])
@org_required(['college'])
def college_edit_subject(subject_id):
    org_id = session.get('org_id')
    subject = Subject.query.filter_by(id=subject_id, organization_id=org_id).first_or_404()
    subject.name = request.form.get('name', subject.name)
    db.session.commit()
    flash('Subject updated successfully.', 'success')
    return redirect(url_for('college_subjects'))

# --- INSTITUTION EDIT (RENAME) ROUTES ---
@app.route('/institution/edit-course/<int:course_id>', methods=['POST'])
@org_required(['institution'])
def institution_edit_course(course_id):
    org_id = session.get('org_id')
    course = Course.query.filter_by(id=course_id, organization_id=org_id).first_or_404()
    course.name = request.form.get('name', course.name)
    db.session.commit()
    flash('Course updated successfully.', 'success')
    return redirect(url_for('institution_dashboard'))

@app.route('/institution/edit-class/<int:class_id>', methods=['POST'])
@org_required(['institution'])
def institution_edit_class(class_id):
    org_id = session.get('org_id')
    class_ = Class_.query.filter_by(id=class_id, organization_id=org_id).first_or_404()
    class_.name = request.form.get('class_name', class_.name)
    class_.academic_year = request.form.get('academic_year', class_.academic_year)
    db.session.commit()
    flash('Class updated successfully.', 'success')
    return redirect(url_for('institution_classes', course_id=class_.course_id, branch=class_.branch, year=class_.study_year, sem=class_.semester))

@app.route('/institution/edit-student/<int:student_id>', methods=['POST'])
@org_required(['institution'])
def institution_edit_student(student_id):
    org_id = session.get('org_id')
    student = Student.query.filter_by(id=student_id, organization_id=org_id).first_or_404()
    student.name = request.form.get('name', student.name)
    student.roll_number = request.form.get('roll_number', student.roll_number)
    student.phone = request.form.get('phone', student.phone)
    class_ = Class_.query.get(student.class_id)
    db.session.commit()
    flash('Student updated successfully.', 'success')
    return redirect(url_for('institution_students', course_id=class_.course_id if class_ else None, branch=class_.branch if class_ else None, year=class_.study_year if class_ else None, sem=class_.semester if class_ else None))

@app.route('/institution/edit-subject/<int:subject_id>', methods=['POST'])
@org_required(['institution'])
def institution_edit_subject(subject_id):
    org_id = session.get('org_id')
    subject = Subject.query.filter_by(id=subject_id, organization_id=org_id).first_or_404()
    subject.name = request.form.get('name', subject.name)
    db.session.commit()
    flash('Subject updated successfully.', 'success')
    return redirect(url_for('institution_dashboard'))

# --- INSTITUTION DELETE ROUTES ---
@app.route('/institution/delete-course/<int:course_id>')
@org_required(['institution'])
def institution_delete_course(course_id):
    org_id = session.get('org_id')
    course = Course.query.filter_by(id=course_id, organization_id=org_id).first_or_404()
    
    # 1. Delete all classes under this course (which cascades to students, attendances, face encodings)
    classes = Class_.query.filter_by(course_id=course.id).all()
    for class_ in classes:
        students = Student.query.filter_by(class_id=class_.id).all()
        for student in students:
            FaceEncoding.query.filter_by(student_id=student.id).delete()
            Attendance.query.filter_by(student_id=student.id).delete()
            db.session.delete(student)
        Attendance.query.filter_by(class_id=class_.id).delete()
        db.session.delete(class_)
        
    # 2. Delete subjects and their attendance
    subjects = Subject.query.filter_by(course_id=course.id).all()
    for subj in subjects:
        Attendance.query.filter_by(subject_id=subj.id).delete()
        db.session.delete(subj)
        
    # 3. Delete StudyYears, Branches, Semesters
    StudyYear.query.filter_by(course_id=course.id).delete()
    Branch.query.filter_by(course_id=course.id).delete()
    Semester.query.filter_by(course_id=course.id).delete()
    
    db.session.delete(course)
    db.session.commit()
    flash('Course and all its classes, subjects, students, branches, semesters, and attendance records deleted successfully.', 'success')
    return redirect(url_for('institution_dashboard'))

@app.route('/institution/delete-branch/<int:branch_id>')
@org_required(['institution'])
def institution_delete_branch(branch_id):
    org_id = session.get('org_id')
    branch = Branch.query.filter_by(id=branch_id, organization_id=org_id).first_or_404()
    course_id = branch.course_id
    
    db.session.delete(branch)
    db.session.commit()
    flash('Branch deleted successfully.', 'success')
    return redirect(url_for('institution_dashboard', course_id=course_id))

@app.route('/institution/delete-year/<int:year_id>')
@org_required(['institution'])
def institution_delete_year(year_id):
    org_id = session.get('org_id')
    study_year = StudyYear.query.filter_by(id=year_id, organization_id=org_id).first_or_404()
    course_id = study_year.course_id
    branch = request.args.get('branch')
    
    db.session.delete(study_year)
    db.session.commit()
    flash('Study Year deleted successfully.', 'success')
    return redirect(url_for('institution_dashboard', course_id=course_id, branch=branch))

@app.route('/institution/delete-sem/<int:sem_id>')
@org_required(['institution'])
def institution_delete_sem(sem_id):
    org_id = session.get('org_id')
    sem = Semester.query.filter_by(id=sem_id, organization_id=org_id).first_or_404()
    course_id = sem.course_id
    branch = request.args.get('branch')
    year = request.args.get('year')
    
    db.session.delete(sem)
    db.session.commit()
    flash('Semester deleted successfully.', 'success')
    return redirect(url_for('institution_dashboard', course_id=course_id, branch=branch, year=year))

@app.route('/institution/delete-subject/<int:subject_id>')
@org_required(['institution'])
def institution_delete_subject(subject_id):
    org_id = session.get('org_id')
    subject = Subject.query.filter_by(id=subject_id, organization_id=org_id).first_or_404()
    
    # Delete subject attendances
    Attendance.query.filter_by(subject_id=subject.id).delete()
    
    db.session.delete(subject)
    db.session.commit()
    flash('Subject and its attendance records deleted successfully.', 'success')
    return redirect(url_for('institution_dashboard'))

@app.route('/institution/delete-class/<int:class_id>')
@org_required(['institution'])
def institution_delete_class(class_id):
    org_id = session.get('org_id')
    class_ = Class_.query.filter_by(id=class_id, organization_id=org_id).first_or_404()
    course_id = class_.course_id
    branch = class_.branch
    year = class_.study_year
    sem = class_.semester
    
    students = Student.query.filter_by(class_id=class_.id).all()
    for student in students:
        FaceEncoding.query.filter_by(student_id=student.id).delete()
        Attendance.query.filter_by(student_id=student.id).delete()
        db.session.delete(student)
    Attendance.query.filter_by(class_id=class_.id).delete()
    
    db.session.delete(class_)
    db.session.commit()
    flash('Class and all its students/attendance records deleted successfully.', 'success')
    return redirect(url_for('institution_classes', course_id=course_id, branch=branch, year=year, sem=sem))

@app.route('/institution/delete-student/<int:student_id>')
@org_required(['institution'])
def institution_delete_student(student_id):
    org_id = session.get('org_id')
    student = Student.query.filter_by(id=student_id, organization_id=org_id).first_or_404()
    class_ = Class_.query.get(student.class_id)
    course_id = class_.course_id if class_ else None
    branch = class_.branch if class_ else None
    year = class_.study_year if class_ else None
    sem = class_.semester if class_ else None
    
    FaceEncoding.query.filter_by(student_id=student.id).delete()
    Attendance.query.filter_by(student_id=student.id).delete()
    
    db.session.delete(student)
    db.session.commit()
    flash('Student deleted successfully.', 'success')
    return redirect(url_for('institution_students', course_id=course_id, branch=branch, year=year, sem=sem))

@app.route('/manifest.json')
def serve_manifest():
    return send_file('static/manifest.json')

@app.route('/.well-known/assetlinks.json')
def assetlinks():
    # Retrieve Google Play SHA256 fingerprint & package name from environment variables
    sha256 = os.environ.get('PLAY_STORE_SHA256', 'YOUR_PLAY_STORE_SHA256_HERE')
    package_name = os.environ.get('PLAY_STORE_PACKAGE', 'com.smartattendance.app')
    return jsonify([{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app",
            "package_name": package_name,
            "sha256_cert_fingerprints": [sha256]
        }
    }])


# ─────────────────────────────────────────────────
# FEE STRUCTURE ROUTES
# ─────────────────────────────────────────────────

@app.route('/school/fees', methods=['GET', 'POST'])
@login_required
@org_required(['school'])
def school_fees():
    org_id = session.get('org_id')
    classes = Class_.query.filter_by(organization_id=org_id).all()
    if request.method == 'POST':
        fee = FeeStructure(
            organization_id=org_id,
            class_id=request.form.get('class_id') or None,
            fee_type=request.form.get('fee_type'),
            amount=float(request.form.get('amount', 0)),
            due_date=datetime.strptime(request.form.get('due_date'), '%Y-%m-%d').date(),
            description=request.form.get('description', '')
        )
        db.session.add(fee)
        db.session.commit()
        flash('Fee item added successfully!', 'success')
        return redirect(url_for('school_fees'))
    fees = FeeStructure.query.filter_by(organization_id=org_id).order_by(FeeStructure.due_date).all()
    return render_template('school/fees.html', fees=fees, classes=classes)

@app.route('/school/fees/delete/<int:fee_id>')
@login_required
@org_required(['school'])
def school_delete_fee(fee_id):
    fee = FeeStructure.query.get_or_404(fee_id)
    db.session.delete(fee)
    db.session.commit()
    flash('Fee item deleted.', 'success')
    return redirect(url_for('school_fees'))

@app.route('/school/leave-applications', methods=['GET', 'POST'])
@login_required
@org_required(['school'])
def school_leave_applications():
    org_id = session.get('org_id')
    if request.method == 'POST':
        leave_id = request.form.get('leave_id')
        action = request.form.get('action')
        leave = LeaveApplication.query.get_or_404(leave_id)
        if action in ('Approved', 'Rejected'):
            leave.status = action
            db.session.commit()
            flash(f'Leave application {action.lower()}.', 'success')
        return redirect(url_for('school_leave_applications'))
    leaves = LeaveApplication.query.filter_by(organization_id=org_id).order_by(LeaveApplication.applied_on.desc()).all()
    return render_template('school/leave_applications.html', leaves=leaves)

@app.route('/college/fees', methods=['GET', 'POST'])
@login_required
@org_required(['college'])
def college_fees():
    org_id = session.get('org_id')
    courses = Course.query.filter_by(organization_id=org_id).all()
    if request.method == 'POST':
        fee = FeeStructure(
            organization_id=org_id,
            course_id=request.form.get('course_id') or None,
            fee_type=request.form.get('fee_type'),
            amount=float(request.form.get('amount', 0)),
            due_date=datetime.strptime(request.form.get('due_date'), '%Y-%m-%d').date(),
            description=request.form.get('description', '')
        )
        db.session.add(fee)
        db.session.commit()
        flash('Fee item added successfully!', 'success')
        return redirect(url_for('college_fees'))
    fees = FeeStructure.query.filter_by(organization_id=org_id).order_by(FeeStructure.due_date).all()
    return render_template('college/fees.html', fees=fees, courses=courses)

@app.route('/college/fees/delete/<int:fee_id>')
@login_required
@org_required(['college'])
def college_delete_fee(fee_id):
    fee = FeeStructure.query.get_or_404(fee_id)
    db.session.delete(fee)
    db.session.commit()
    flash('Fee item deleted.', 'success')
    return redirect(url_for('college_fees'))

@app.route('/college/leave-applications', methods=['GET', 'POST'])
@login_required
@org_required(['college'])
def college_leave_applications():
    org_id = session.get('org_id')
    if request.method == 'POST':
        leave_id = request.form.get('leave_id')
        action = request.form.get('action')
        leave = LeaveApplication.query.get_or_404(leave_id)
        if action in ('Approved', 'Rejected'):
            leave.status = action
            db.session.commit()
            flash(f'Leave application {action.lower()}.', 'success')
        return redirect(url_for('college_leave_applications'))
    leaves = LeaveApplication.query.filter_by(organization_id=org_id).order_by(LeaveApplication.applied_on.desc()).all()
    return render_template('college/leave_applications.html', leaves=leaves)

@app.route('/institution/fees', methods=['GET', 'POST'])
@login_required
@org_required(['institution'])
def institution_fees():
    org_id = session.get('org_id')
    courses = Course.query.filter_by(organization_id=org_id).all()
    if request.method == 'POST':
        fee = FeeStructure(
            organization_id=org_id,
            course_id=request.form.get('course_id') or None,
            fee_type=request.form.get('fee_type'),
            amount=float(request.form.get('amount', 0)),
            due_date=datetime.strptime(request.form.get('due_date'), '%Y-%m-%d').date(),
            description=request.form.get('description', '')
        )
        db.session.add(fee)
        db.session.commit()
        flash('Fee item added successfully!', 'success')
        return redirect(url_for('institution_fees'))
    fees = FeeStructure.query.filter_by(organization_id=org_id).order_by(FeeStructure.due_date).all()
    return render_template('institution/fees.html', fees=fees, courses=courses)

@app.route('/institution/fees/delete/<int:fee_id>')
@login_required
@org_required(['institution'])
def institution_delete_fee(fee_id):
    fee = FeeStructure.query.get_or_404(fee_id)
    db.session.delete(fee)
    db.session.commit()
    flash('Fee item deleted.', 'success')
    return redirect(url_for('institution_fees'))

@app.route('/institution/leave-applications', methods=['GET', 'POST'])
@login_required
@org_required(['institution'])
def institution_leave_applications():
    org_id = session.get('org_id')
    if request.method == 'POST':
        leave_id = request.form.get('leave_id')
        action = request.form.get('action')
        leave = LeaveApplication.query.get_or_404(leave_id)
        if action in ('Approved', 'Rejected'):
            leave.status = action
            db.session.commit()
            flash(f'Leave application {action.lower()}.', 'success')
        return redirect(url_for('institution_leave_applications'))
    leaves = LeaveApplication.query.filter_by(organization_id=org_id).order_by(LeaveApplication.applied_on.desc()).all()
    return render_template('institution/leave_applications.html', leaves=leaves)

# ─────────────────────────────────────────────────
# STUDENT LEAVE APPLICATION
# ─────────────────────────────────────────────────

@app.route('/student/leave', methods=['GET', 'POST'])
def student_leave():
    if 'student_id' not in session:
        flash('Please login to access this page.', 'warning')
        return redirect(url_for('student_login'))
    student_id = session.get('student_id')
    student = Student.query.get(student_id)
    if not student:
        session.clear()
        return redirect(url_for('student_login'))
    if request.method == 'POST':
        leave = LeaveApplication(
            organization_id=student.organization_id,
            student_id=student_id,
            start_date=datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date(),
            end_date=datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date(),
            reason=request.form.get('reason')
        )
        db.session.add(leave)
        db.session.commit()
        flash('Leave application submitted successfully!', 'success')
        return redirect(url_for('student_leave'))
    leaves = LeaveApplication.query.filter_by(student_id=student_id).order_by(LeaveApplication.applied_on.desc()).all()
    return render_template('student/apply_leave.html', leaves=leaves, student=student)

# ─────────────────────────────────────────────────
# STAFF LEAVE APPLICATION
# ─────────────────────────────────────────────────

@app.route('/staff/leave', methods=['GET', 'POST'])
def staff_leave():
    if not session.get('is_staff'):
        flash('Please login as staff.', 'warning')
        return redirect(url_for('staff_login'))
    staff_id = session.get('staff_id')
    staff = Staff.query.get(staff_id)
    if not staff:
        session.clear()
        return redirect(url_for('staff_login'))
    if request.method == 'POST':
        leave = LeaveApplication(
            organization_id=staff.organization_id,
            staff_id=staff_id,
            start_date=datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date(),
            end_date=datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date(),
            reason=request.form.get('reason')
        )
        db.session.add(leave)
        db.session.commit()
        flash('Leave application submitted successfully!', 'success')
        return redirect(url_for('staff_leave'))
    leaves = LeaveApplication.query.filter_by(staff_id=staff_id).order_by(LeaveApplication.applied_on.desc()).all()
    return render_template('staff/apply_leave.html', leaves=leaves, staff=staff)


# ─────────────────────────────────────────────────
# BIOMETRICS DIAGNOSTICS & MIGRATION API
# ─────────────────────────────────────────────────

@app.route('/api/system/biometrics-status', methods=['GET'])
def api_biometrics_status():
    """System biometric diagnostics and engine status."""
    try:
        if not FACE_API_AVAILABLE:
            return jsonify({'engine': 'unavailable', 'error': 'onnxruntime not installed on this server', 'face_api_available': False})
        pipeline = get_pipeline()
        diag = pipeline.get_diagnostics()

        # Database statistics
        total_512 = 0
        total_128 = 0
        encs = FaceEncoding.query.all()
        for e in encs:
            if e.encoding_data and isinstance(e.encoding_data, list):
                if len(e.encoding_data) == 512:
                    total_512 += 1
                elif len(e.encoding_data) == 128:
                    total_128 += 1

        staff_512 = 0
        staff_128 = 0
        staff_encs = StaffFaceEncoding.query.all()
        for se in staff_encs:
            if se.encoding_data and isinstance(se.encoding_data, list):
                if len(se.encoding_data) == 512:
                    staff_512 += 1
                elif len(se.encoding_data) == 128:
                    staff_128 += 1

        diag["database_stats"] = {
            "student_arcface_512d": total_512,
            "student_legacy_128d": total_128,
            "staff_arcface_512d": staff_512,
            "staff_legacy_128d": staff_128,
            "total_registered_embeddings": total_512 + staff_512
        }
        return jsonify({"status": "success", "diagnostics": diag})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/admin/migrate-faces', methods=['GET', 'POST'])
@csrf.exempt
def admin_migrate_faces():
    """Administrator face encoding migration endpoint from legacy dlib to ArcFace."""
    org_id = session.get('org_id')
    from migrate_face_encodings import run_face_migration
    if request.method == 'POST':
        try:
            stats = run_face_migration(app=app, organization_id=org_id)
            return jsonify({
                "status": "success",
                "message": f"Migration complete: {stats['successfully_converted']} converted, {stats['already_arcface']} already on ArcFace.",
                "stats": stats
            })
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    # GET request - return current status
    try:
        total_students = Student.query.count()
        arcface_count = 0
        students = Student.query.all()
        for s in students:
            encs = FaceEncoding.query.filter_by(student_id=s.id).all()
            if any(e.encoding_data and len(e.encoding_data) == 512 for e in encs):
                arcface_count += 1
        return jsonify({
            "status": "success",
            "total_students": total_students,
            "students_with_arcface": arcface_count,
            "students_needing_conversion": total_students - arcface_count
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    port = int(os.environ.get('PORT', 5000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
