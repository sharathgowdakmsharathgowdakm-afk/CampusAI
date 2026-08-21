from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

student_bp = Blueprint('student', __name__, url_prefix='/student')

@student_bp.route('/login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        identifier = request.form.get('roll_number') or request.form.get('identifier', '')
        password = request.form.get('password', '')

        # Import from app context to use the correct db instance
        from app import Student

        # Try matching by email, username, phone, or roll number
        student = (
            Student.query.filter_by(email=identifier).first() or
            Student.query.filter_by(username=identifier).first() or
            Student.query.filter_by(phone=identifier).first() or
            Student.query.filter_by(roll_number=identifier).first()
        )

        if student and student.password:
            if check_password_hash(student.password, password):
                session['student_id'] = student.id
                session['student_name'] = student.name
                return redirect(url_for('student.dashboard'))
        elif student and not student.password and password == 'student123':
            session['student_id'] = student.id
            session['student_name'] = student.name
            return redirect(url_for('student.dashboard'))

        flash('Invalid credentials. Please check your details and try again.', 'danger')

    return render_template('student/login.html')

@student_bp.route('/dashboard')
def dashboard():
    if 'student_id' not in session:
        return redirect(url_for('student.student_login'))

    student_id = session['student_id']

    # Import from app context to use the correct db/models
    from app import Student, Attendance, db

    student = Student.query.get(student_id)
    if not student:
        session.clear()
        flash('Student record not found. Please log in again.', 'danger')
        return redirect(url_for('student.student_login'))

    # Count total sessions for student's class
    total_records = db.session.query(Attendance).filter_by(class_id=student.class_id).distinct(
        Attendance.date, Attendance.subject_id
    ).count()

    # Count sessions where student was present
    present_records = Attendance.query.filter(
        Attendance.student_id == student_id,
        Attendance._status == 'present'
    ).count()

    percentage = (present_records / total_records * 100) if total_records > 0 else 0

    recent_attendance = Attendance.query.filter_by(
        student_id=student_id
    ).order_by(Attendance.date.desc()).limit(10).all()

    return render_template('student/dashboard.html',
                           student=student,
                           percentage=round(percentage, 2),
                           recent_attendance=recent_attendance)

@student_bp.route('/logout')
def logout():
    session.pop('student_id', None)
    session.pop('student_name', None)
    return redirect(url_for('student.student_login'))
