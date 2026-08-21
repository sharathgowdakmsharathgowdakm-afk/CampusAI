from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import cv2
import numpy as np
import pickle
import random
import string
from io import BytesIO
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, PageBreak
from reportlab.lib import colors
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///attendance.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

db = SQLAlchemy(app)

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

class Class_(db.Model):
    __tablename__ = 'class'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    academic_year = db.Column(db.String(20), nullable=False)
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    students = db.relationship('Student', backref='class_', lazy=True)
    attendances = db.relationship('Attendance', backref='class_', lazy=True)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    roll_number = db.Column(db.String(20), nullable=False)
    phone = db.Column(db.String(15))
    organization_id = db.Column(db.Integer, db.ForeignKey('organization.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    attendances = db.relationship('Attendance', backref='student', lazy=True)
    face_encodings = db.relationship('FaceEncoding', backref='student', lazy=True)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(10), nullable=False)  # present, absent
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class FaceEncoding(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    encoding_path = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Template Filters
@app.template_filter('strftime')
def _jinja2_filter_datetime(date, fmt=None):
    if date == 'now':
        date = datetime.now()
    return date.strftime(fmt)

# Decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        org_type = request.form.get('org_type')
        username = request.form.get('username')
        password = request.form.get('password')

        if not all([org_type, username, password]):
            flash('All fields are required', 'danger')
            return redirect(url_for('login'))

        user = User.query.filter_by(username=username, org_type=org_type).first()

        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['org_type'] = user.org_type
            session['org_id'] = user.organization_id
            session['org_name'] = user.organization.name

            if org_type == 'school':
                return redirect(url_for('school_dashboard'))
            elif org_type == 'college':
                return redirect(url_for('college_dashboard'))
            elif org_type == 'institution':
                return redirect(url_for('institution_dashboard'))
        else:
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
    classes = Class_.query.filter_by(organization_id=session.get('org_id')).all()
    total_students = Student.query.filter_by(organization_id=session.get('org_id')).count()
    today_attendance = Attendance.query.filter_by(
        date=datetime.now().date()
    ).join(Student).filter_by(organization_id=session.get('org_id')).count()

    return render_template('school/dashboard.html',
                         classes=classes,
                         total_students=total_students,
                         today_attendance=today_attendance)

@app.route('/school/add-class', methods=['GET', 'POST'])
@org_required(['school'])
def school_add_class():
    if request.method == 'POST':
        class_name = request.form.get('class_name')
        academic_year = request.form.get('academic_year')

        if not all([class_name, academic_year]):
            flash('All fields are required', 'danger')
            return redirect(url_for('school_add_class'))

        class_ = Class_(
            name=class_name,
            academic_year=academic_year,
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

@app.route('/school/face-register', methods=['GET', 'POST'])
@org_required(['school'])
def school_face_register():
    students = Student.query.filter_by(
        organization_id=session.get('org_id')
    ).all()

    if request.method == 'POST':
        student_id = request.form.get('student_id', '')

        if not student_id:
            return jsonify({'error': 'Student not selected'}), 400

        if 'face_image' not in request.files:
            return jsonify({'error': 'No face image provided'}), 400

        file = request.files['face_image']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        try:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # Load image using OpenCV
            image = cv2.imread(filepath)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # Load Haar cascade for face detection
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)

            if len(faces) == 0:
                return jsonify({'error': 'No face detected in image'}), 400

            # Use the first detected face
            (x, y, w, h) = faces[0]
            face_roi = gray[y:y+h, x:x+w]

            # Resize face to standard size for comparison
            face_resized = cv2.resize(face_roi, (100, 100))

            # Save face encoding (grayscale image array)
            encoding_path = os.path.join(
                'face_encodings',
                f'student_{student_id}_{datetime.now().timestamp()}.pkl'
            )

            with open(encoding_path, 'wb') as f:
                pickle.dump(face_resized, f)

            face_record = FaceEncoding(
                student_id=int(student_id),
                encoding_path=encoding_path,
                created_at=datetime.utcnow()
            )
            db.session.add(face_record)
            db.session.commit()

            return jsonify({'success': 'Face registered successfully'})

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return render_template('school/face_register.html', students=students)

@app.route('/school/mark-attendance', methods=['GET', 'POST'])
@org_required(['school'])
def school_mark_attendance():
    classes = Class_.query.filter_by(
        organization_id=session.get('org_id')
    ).all()

    if request.method == 'POST':
        class_id = request.form.get('class_id', '')

        if not class_id:
            return jsonify({'error': 'Class not selected'}), 400

        if 'attendance_image' not in request.files:
            return jsonify({'error': 'No image provided'}), 400

        file = request.files['attendance_image']
        try:
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'],
'temp_attendance.jpg')
            file.save(temp_path)

            # Load image using OpenCV
            image = cv2.imread(temp_path)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # Load Haar cascade for face detection
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)

            if len(faces) == 0:
                return jsonify({'error': 'No faces detected'}), 400

            students = Student.query.filter_by(class_id=int(class_id)).all()
            recognized_students = []

            for (x, y, w, h) in faces:
                detected_face = gray[y:y+h, x:x+w]
                detected_resized = cv2.resize(detected_face, (100, 100))

                for student in students:
                    face_recs = FaceEncoding.query.filter_by(student_id=student.id).all()

                    for face_rec in face_recs:
                        try:
                            with open(face_rec.encoding_path, 'rb') as f:
                                stored_face = pickle.load(f)

                            # Simple template matching for face recognition
                            result = cv2.matchTemplate(detected_resized, stored_face, cv2.TM_CCOEFF_NORMED)
                            max_val = cv2.minMaxLoc(result)[1]

                            # Threshold for face match (adjust as needed)
                            if max_val > 0.7:
                                existing = Attendance.query.filter_by(
                                    student_id=student.id,
                                    date=datetime.now().date()
                                ).first()

                                if not existing:
                                    attendance = Attendance(
                                        student_id=student.id,
                                        class_id=int(class_id),
                                        date=datetime.now().date(),
                                        time=datetime.now().time(),
                                        status='present',
                                    )
                                    db.session.add(attendance)
                                    recognized_students.append({
                                        'name': student.name,
                                        'roll_number': student.roll_number
                                    })
                                break
                        except Exception as e:
                            continue

            db.session.commit()
            return jsonify({
                'success': f'Attendance marked for {len(recognized_students)} students',
                'recognized': recognized_students
            })

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return render_template('school/mark_attendance.html', classes=classes)

@app.route('/school/attendance-records')
@org_required(['school'])
def school_attendance_records():
    classes = Class_.query.filter_by(organization_id=session.get('org_id')).all()
    records = []

    for class_ in classes:
        attendances = Attendance.query.filter_by(class_id=class_.id).all()
        records.extend(attendances)

    return render_template('school/attendance_records.html', records=records, classes=classes)

@app.route('/school/reports', methods=['GET', 'POST'])
@org_required(['school'])
def school_reports():
    if request.method == 'POST':
        student_id = request.form.get('student_id')
        class_id = request.form.get('class_id')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        # Generate PDF report
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []

        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=getSampleStyleSheet()['Heading1'],
            fontSize=16,
            spaceAfter=30,
        )
        elements.append(Paragraph("Attendance Report", title_style))

        # Student info
        if student_id:
            student = Student.query.get(int(student_id))
            elements.append(Paragraph(f"Student: {student.name}", getSampleStyleSheet()['Normal']))
            elements.append(Paragraph(f"Roll Number: {student.roll_number}", getSampleStyleSheet()['Normal']))

        # Attendance data
        data = [['Date', 'Time', 'Status']]
        attendances = Attendance.query.filter_by(student_id=int(student_id) if student_id else None)

        if start_date and end_date:
            attendances = attendances.filter(Attendance.date.between(start_date, end_date))

        attendances = attendances.all()

        for att in attendances:
            data.append([str(att.date), str(att.time), att.status])

        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))

        elements.append(table)
        doc.build(elements)

        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name='attendance_report.pdf', mimetype='application/pdf')

    students = Student.query.filter_by(organization_id=session.get('org_id')).all()
    classes = Class_.query.filter_by(organization_id=session.get('org_id')).all()

    return render_template('school/reports.html', students=students, classes=classes)

@app.route('/school/students')
@org_required(['school'])
def school_students():
    students = Student.query.filter_by(organization_id=session.get('org_id')).all()
    return render_template('school/students.html', students=students)

# College Routes (Similar to School)
@app.route('/college/dashboard')
@org_required(['college'])
def college_dashboard():
    return render_template('college/dashboard.html')

# Institution Routes (Similar to College)
@app.route('/institution/dashboard')
@org_required(['institution'])
def institution_dashboard():
    return render_template('institution/dashboard.html')

# Student Portal
@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        phone = request.form.get('phone')
        password = request.form.get('password')

        # Simple authentication - in real app, you'd have proper student accounts
        student = Student.query.filter_by(phone=phone).first()
        if student and password == 'student123':  # Default password
            session['student_id'] = student.id
            return redirect(url_for('student_dashboard'))

        flash('Invalid credentials', 'danger')

    return render_template('student_login.html')

@app.route('/student/dashboard')
def student_dashboard():
    if 'student_id' not in session:
        return redirect(url_for('student_login'))

    student = Student.query.get(session['student_id'])
    attendances = Attendance.query.filter_by(student_id=student.id).order_by(Attendance.date.desc()).limit(30).all()

    total_days = len(attendances)
    present_days = len([a for a in attendances if a.status == 'present'])
    attendance_percentage = (present_days / total_days * 100) if total_days > 0 else 0

    return render_template('student_report.html',
                         student=student,
                         attendances=attendances,
                         attendance_percentage=round(attendance_percentage, 1))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('splash'))

@app.route('/init-db')
def init_db():
    """Initialize database with default data"""
    db.create_all()

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

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)