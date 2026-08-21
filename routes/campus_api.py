"""
Smart Campus Platform — REST API v2 Blueprint
Mobile/PWA endpoints for the campus platform.
All endpoints require JWT authentication.
"""
from flask import Blueprint, jsonify, request, session
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta, date
import json

campus_api_bp = Blueprint('campus_api', __name__, url_prefix='/api/v2')


# ─────────────────────────────────────────────
# AUTHENTICATION
# ─────────────────────────────────────────────

@campus_api_bp.route('/auth/login', methods=['POST'])
def api_v2_login():
    """Unified login for student/parent/admin via API."""
    from app import Student, User, Parent
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    user_type = data.get('user_type', 'student')
    email_or_roll = data.get('email') or data.get('roll_number', '')
    password = data.get('password', '')

    if user_type == 'student':
        user = Student.query.filter_by(roll_number=email_or_roll).first()
        if not user:
            user = Student.query.filter_by(email=email_or_roll).first()
        if not user:
            return jsonify({'error': 'Student not found'}), 404
        pwd_ok = (user.password == password) or (
            user.password and check_password_hash(user.password, password))
        if not pwd_ok:
            return jsonify({'error': 'Invalid credentials'}), 401
        token = create_access_token(identity=f"student:{user.id}", expires_delta=timedelta(days=7))
        return jsonify({
            'access_token': token,
            'user_type': 'student',
            'profile': {
                'id': user.id, 'name': user.name,
                'roll_number': user.roll_number, 'email': user.email,
                'class_id': user.class_id, 'org_id': user.organization_id
            }
        })

    elif user_type == 'parent':
        user = Parent.query.filter_by(email=email_or_roll).first()
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({'error': 'Invalid credentials'}), 401
        token = create_access_token(identity=f"parent:{user.id}", expires_delta=timedelta(days=7))
        return jsonify({
            'access_token': token,
            'user_type': 'parent',
            'profile': {
                'id': user.id, 'name': user.name,
                'email': user.email, 'student_id': user.student_id
            }
        })

    elif user_type == 'admin':
        user = User.query.filter_by(username=email_or_roll).first()
        if not user:
            user = User.query.filter_by(email=email_or_roll).first()
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({'error': 'Invalid credentials'}), 401
        token = create_access_token(identity=f"admin:{user.id}", expires_delta=timedelta(days=1))
        return jsonify({
            'access_token': token,
            'user_type': 'admin',
            'profile': {
                'id': user.id, 'username': user.username,
                'email': user.email, 'org_type': user.org_type,
                'org_id': user.organization_id
            }
        })

    return jsonify({'error': 'Invalid user_type'}), 400


# ─────────────────────────────────────────────
# ATTENDANCE API
# ─────────────────────────────────────────────

@campus_api_bp.route('/attendance/summary', methods=['GET'])
@jwt_required()
def attendance_summary():
    from app import Attendance, Student
    identity = get_jwt_identity()
    if not identity.startswith('student:'):
        return jsonify({'error': 'Student access required'}), 403
    sid = int(identity.split(':')[1])

    records = Attendance.query.filter_by(student_id=sid).order_by(Attendance.date.desc()).all()
    total = len(records)
    present = sum(1 for r in records if r._status == 'present')
    absent = total - present
    pct = round(present / total * 100, 1) if total else 0

    recent = [{
        'date': r.date.strftime('%Y-%m-%d'),
        'status': r._status,
        'subject': r.subject.name if r.subject else None
    } for r in records[:30]]

    return jsonify({
        'total': total, 'present': present, 'absent': absent,
        'percentage': pct,
        'at_risk': pct < 75,
        'recent': recent
    })


@campus_api_bp.route('/attendance/predict', methods=['GET'])
@jwt_required()
def predict_attendance():
    from app import Attendance
    identity = get_jwt_identity()
    if not identity.startswith('student:'):
        return jsonify({'error': 'Student access required'}), 403
    sid = int(identity.split(':')[1])

    records = Attendance.query.filter_by(student_id=sid).order_by(Attendance.date).all()
    total = len(records)
    present = sum(1 for r in records if r._status == 'present')
    pct = round(present / total * 100, 1) if total else 0

    predicted = pct
    try:
        import numpy as np
        from sklearn.linear_model import LinearRegression
        if total >= 5:
            X = np.array(range(total)).reshape(-1, 1)
            y = np.array([1 if r._status == 'present' else 0 for r in records], dtype=float)
            model = LinearRegression().fit(X, y)
            future = model.predict([[total + 7]])[0]
            predicted = round(min(100, max(0, future * 100)), 1)
    except ImportError:
        pass

    return jsonify({
        'current_percentage': pct,
        'predicted_percentage': predicted,
        'at_risk': pct < 75,
        'detention_probability': max(0, min(100, round((75 - pct) * 3, 1))) if pct < 75 else 0
    })


# ─────────────────────────────────────────────
# ASSIGNMENTS API
# ─────────────────────────────────────────────

@campus_api_bp.route('/assignments', methods=['GET'])
@jwt_required()
def get_assignments():
    from app import Assignment, AssignmentSubmission, Student
    identity = get_jwt_identity()
    assignments = []

    if identity.startswith('student:'):
        sid = int(identity.split(':')[1])
        student = Student.query.get(sid)
        if student:
            asgns = Assignment.query.filter_by(class_id=student.class_id).all()
            sub_map = {s.assignment_id: s for s in AssignmentSubmission.query.filter_by(student_id=sid).all()}
            for a in asgns:
                sub = sub_map.get(a.id)
                assignments.append({
                    'id': a.id,
                    'title': a.title,
                    'description': a.description,
                    'deadline': a.deadline.isoformat() if a.deadline else None,
                    'max_marks': a.max_marks,
                    'submitted': sub is not None,
                    'marks': sub.marks if sub else None,
                    'status': sub.status if sub else 'pending'
                })

    return jsonify({'assignments': assignments})


# ─────────────────────────────────────────────
# LMS API
# ─────────────────────────────────────────────

@campus_api_bp.route('/lms/content', methods=['GET'])
@jwt_required()
def get_lms_content():
    from app import LMSContent, Student
    identity = get_jwt_identity()
    class_id = None

    if identity.startswith('student:'):
        sid = int(identity.split(':')[1])
        student = Student.query.get(sid)
        if student:
            class_id = student.class_id

    q = LMSContent.query
    if class_id:
        q = q.filter_by(class_id=class_id)
    content = q.order_by(LMSContent.created_at.desc()).limit(50).all()

    return jsonify({'content': [{
        'id': c.id,
        'title': c.title,
        'type': c.content_type,
        'description': c.description,
        'url': c.external_url,
        'duration': c.duration,
        'created_at': c.created_at.isoformat()
    } for c in content]})


# ─────────────────────────────────────────────
# NOTIFICATIONS API
# ─────────────────────────────────────────────

@campus_api_bp.route('/notifications', methods=['GET'])
@jwt_required()
def get_notifications():
    from app import Notification, Student, Parent, User
    identity = get_jwt_identity()
    org_id = None

    if identity.startswith('student:'):
        sid = int(identity.split(':')[1])
        student = Student.query.get(sid)
        org_id = student.organization_id if student else None
    elif identity.startswith('parent:'):
        pid = int(identity.split(':')[1])
        parent = Parent.query.get(pid)
        org_id = parent.organization_id if parent else None
    elif identity.startswith('admin:'):
        uid = int(identity.split(':')[1])
        user = User.query.get(uid)
        org_id = user.organization_id if user else None

    if not org_id:
        return jsonify({'notifications': []})

    notifs = Notification.query.filter_by(org_id=org_id).order_by(
        Notification.created_at.desc()).limit(20).all()

    return jsonify({'notifications': [{
        'id': n.id,
        'title': n.title,
        'message': n.message,
        'type': n.notif_type,
        'is_read': n.is_read,
        'created_at': n.created_at.isoformat()
    } for n in notifs]})


# ─────────────────────────────────────────────
# TIMETABLE API
# ─────────────────────────────────────────────

@campus_api_bp.route('/timetable', methods=['GET'])
@jwt_required()
def get_timetable():
    from app import Timetable, Student
    identity = get_jwt_identity()
    class_id = request.args.get('class_id', type=int)

    if not class_id and identity.startswith('student:'):
        sid = int(identity.split(':')[1])
        student = Student.query.get(sid)
        if student:
            class_id = student.class_id

    if not class_id:
        return jsonify({'timetable': []})

    entries = Timetable.query.filter_by(class_id=class_id).all()
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    result = {d: [] for d in days}
    for e in entries:
        if e.day_of_week in result:
            result[e.day_of_week].append({
                'id': e.id,
                'subject': e.subject_name,
                'start': e.start_time,
                'end': e.end_time,
                'room': e.room,
                'faculty': e.faculty
            })
    return jsonify({'timetable': result})


# ─────────────────────────────────────────────
# PARENT DASHBOARD API
# ─────────────────────────────────────────────

@campus_api_bp.route('/parent/dashboard', methods=['GET'])
@jwt_required()
def parent_api_dashboard():
    from app import Student, Attendance, Assignment, AssignmentSubmission
    identity = get_jwt_identity()
    if not identity.startswith('parent:'):
        return jsonify({'error': 'Parent access required'}), 403

    pid = int(identity.split(':')[1])
    from app import Parent
    parent = Parent.query.get(pid)
    if not parent:
        return jsonify({'error': 'Parent not found'}), 404

    sid = parent.student_id
    student = Student.query.get(sid)
    total = Attendance.query.filter_by(student_id=sid).count()
    present = Attendance.query.filter_by(student_id=sid, _status='present').count()
    pct = round(present / total * 100, 1) if total else 0

    return jsonify({
        'student': {
            'name': student.name,
            'roll_number': student.roll_number,
            'class_id': student.class_id
        },
        'attendance': {
            'total': total,
            'present': present,
            'absent': total - present,
            'percentage': pct,
            'at_risk': pct < 75
        }
    })


# ─────────────────────────────────────────────
# AI CHATBOT API
# ─────────────────────────────────────────────

@campus_api_bp.route('/assistant/chat', methods=['POST'])
@jwt_required()
def api_chat():
    from app import db, ChatMessage, Student
    from routes.campus import ai_bot_response
    identity = get_jwt_identity()
    data = request.get_json()
    message = data.get('message', '').strip()
    if not message:
        return jsonify({'error': 'Empty message'}), 400

    org_id = None
    if identity.startswith('student:'):
        sid = int(identity.split(':')[1])
        student = Student.query.get(sid)
        org_id = student.organization_id if student else None

    reply = ai_bot_response(message, org_id)
    return jsonify({'reply': reply})


# ─────────────────────────────────────────────
# PERFORMANCE SUMMARY API
# ─────────────────────────────────────────────

@campus_api_bp.route('/performance/summary', methods=['GET'])
@jwt_required()
def performance_summary():
    from app import InternalMark, Exam, Attendance
    identity = get_jwt_identity()
    if not identity.startswith('student:'):
        return jsonify({'error': 'Student access required'}), 403
    sid = int(identity.split(':')[1])

    marks = InternalMark.query.filter_by(student_id=sid).all()
    marks_list = []
    total_pct = 0
    for m in marks:
        exam = Exam.query.get(m.exam_id)
        if exam and m.marks_obtained is not None:
            pct = round(m.marks_obtained / exam.max_marks * 100, 1)
            total_pct += pct
            marks_list.append({
                'exam': exam.name,
                'marks': m.marks_obtained,
                'max': exam.max_marks,
                'percentage': pct,
                'grade': m.grade
            })

    avg = round(total_pct / len(marks_list), 1) if marks_list else 0
    att = Attendance.query.filter_by(student_id=sid, _status='present').count()
    att_total = Attendance.query.filter_by(student_id=sid).count()
    att_pct = round(att / att_total * 100, 1) if att_total else 0

    predicted_gpa = min(4.0, round((0.6 * avg + 0.4 * att_pct) / 25, 2))

    return jsonify({
        'marks': marks_list,
        'average_percentage': avg,
        'attendance_percentage': att_pct,
        'predicted_gpa': predicted_gpa
    })
