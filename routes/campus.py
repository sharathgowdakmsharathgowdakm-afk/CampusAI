"""
Smart Campus Platform — Main Blueprint
All new AI Campus modules integrated with the existing Smart Attendance System.
The existing attendance engine and routes are completely untouched.
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, flash, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta, date
from functools import wraps
import os
import json
import uuid
import re

campus_bp = Blueprint('campus', __name__, url_prefix='/campus')

@campus_bp.before_request
def load_org_details():
    org_id = session.get('org_id')
    if org_id:
        from app import Organization
        try:
            org = Organization.query.get(org_id)
            if org:
                session['org_name'] = org.name
                if org.logo_path:
                    session['org_logo'] = org.logo_path
        except Exception:
            pass

# ─────────────────────────────────────────────
# Helper decorators (reuse session from app.py)
# ─────────────────────────────────────────────

def campus_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session and 'staff_id' not in session and 'parent_id' not in session and 'student_id' not in session:
            flash('Please login to continue', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Admin access required', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def staff_or_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session and 'staff_id' not in session:
            flash('Admin or Staff access required', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def log_audit(action, user_type='admin'):
    """Log user actions to audit table."""
    try:
        from app import db, AuditLog
        log = AuditLog(
            user_id=session.get('user_id') or session.get('staff_id') or session.get('student_id'),
            user_type=user_type,
            username=session.get('username') or session.get('staff_name') or session.get('student_name', 'unknown'),
            action=action,
            ip_address=request.remote_addr,
            org_id=session.get('org_id')
        )
        db.session.add(log)
        db.session.commit()
    except Exception:
        pass

# ─────────────────────────────────────────────
# AI CAMPUS ASSISTANT
# ─────────────────────────────────────────────

def ai_bot_response(message, org_id):
    """Rule-based AI campus assistant — queries live DB for answers."""
    from app import (db, Student, Attendance, Class_, Subject, Assignment,
                     Exam, Timetable, Notification, LMSContent)
    msg = message.lower().strip()

    # Attendance queries
    if any(w in msg for w in ['attendance', 'present', 'absent', 'percentage']):
        if 'student_id' in session:
            sid = session['student_id']
            total = Attendance.query.filter_by(student_id=sid).count()
            present = Attendance.query.filter_by(student_id=sid, _status='present').count()
            pct = round((present / total * 100), 1) if total > 0 else 0
            return (f"📊 Your current attendance is **{pct}%** "
                    f"({present} present out of {total} total classes). "
                    + ("⚠️ You are at risk of shortage!" if pct < 75 else "✅ You're on track!"))
        total = Attendance.query.join(Student).filter(Student.organization_id == org_id).count()
        present = Attendance.query.join(Student).filter(
            Student.organization_id == org_id, Attendance._status == 'present').count()
        pct = round((present / total * 100), 1) if total > 0 else 0
        return f"📊 Overall attendance for your institution is **{pct}%** ({present}/{total} classes)."

    # Student count
    if any(w in msg for w in ['how many students', 'total students', 'student count']):
        count = Student.query.filter_by(organization_id=org_id).count()
        return f"👥 There are **{count} students** registered in your institution."

    # Class/subject info
    if any(w in msg for w in ['class', 'classes', 'section']):
        count = Class_.query.filter_by(organization_id=org_id).count()
        return f"🏫 Your institution has **{count} classes/sections** registered."

    # Assignment deadline
    if any(w in msg for w in ['assignment', 'deadline', 'submission']):
        from app import Assignment
        upcoming = Assignment.query.filter(
            Assignment.organization_id == org_id,
            Assignment.deadline >= datetime.now()
        ).order_by(Assignment.deadline).limit(3).all()
        if upcoming:
            lines = [f"📝 Upcoming assignments:"]
            for a in upcoming:
                lines.append(f"• **{a.title}** — due {a.deadline.strftime('%d %b %Y %H:%M')}")
            return "\n".join(lines)
        return "📝 No upcoming assignments found."

    # Exam schedule
    if any(w in msg for w in ['exam', 'test', 'examination']):
        upcoming = Exam.query.filter(
            Exam.organization_id == org_id,
            Exam.date >= date.today()
        ).order_by(Exam.date).limit(3).all()
        if upcoming:
            lines = ["📅 Upcoming exams:"]
            for e in upcoming:
                lines.append(f"• **{e.name}** ({e.subject_name or 'General'}) — {e.date.strftime('%d %b %Y')}")
            return "\n".join(lines)
        return "📅 No upcoming exams scheduled."

    # Timetable
    if any(w in msg for w in ['timetable', 'schedule', 'time table', 'class schedule']):
        return "📋 View your full timetable on the **Timetable** page under Academic ERP."

    # Notifications
    if any(w in msg for w in ['notification', 'alert', 'notice']):
        count = Notification.query.filter_by(org_id=org_id, is_read=False).count()
        return f"🔔 You have **{count} unread notifications**. Check the Notifications page."

    # LMS / Study material
    if any(w in msg for w in ['material', 'notes', 'video', 'lms', 'lecture', 'pdf']):
        count = LMSContent.query.filter_by(organization_id=org_id).count()
        return f"📚 There are **{count} learning materials** available in the LMS. Click LMS in the sidebar."

    # Low attendance warning
    if any(w in msg for w in ['risk', 'shortage', 'detention', 'low attendance']):
        threshold = 75
        students = Student.query.filter_by(organization_id=org_id).all()
        at_risk = []
        for s in students:
            total = Attendance.query.filter_by(student_id=s.id).count()
            present = Attendance.query.filter_by(student_id=s.id, _status='present').count()
            if total > 0 and (present / total * 100) < threshold:
                at_risk.append(s.name)
        if at_risk:
            names = ", ".join(at_risk[:5]) + (f" and {len(at_risk)-5} more" if len(at_risk) > 5 else "")
            return f"⚠️ **{len(at_risk)} students** are at risk of attendance shortage: {names}"
        return "✅ No students are currently at risk of attendance shortage."

    # Greetings
    if any(w in msg for w in ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening']):
        hour = datetime.now().hour
        greeting = "Good morning" if hour < 12 else ("Good afternoon" if hour < 17 else "Good evening")
        name = session.get('username') or session.get('student_name', '')
        return f"👋 {greeting}{', ' + name if name else ''}! I'm your AI Campus Assistant. Ask me about attendance, assignments, exams, timetable, or LMS."

    # Help
    if any(w in msg for w in ['help', 'what can you do', 'features']):
        return ("🤖 I can help you with:\n"
                "• **Attendance** — check percentages, at-risk students\n"
                "• **Assignments** — upcoming deadlines\n"
                "• **Exams** — upcoming exam schedule\n"
                "• **Notifications** — unread alerts\n"
                "• **LMS** — learning material count\n"
                "• **Students/Classes** — institution stats\n\n"
                "Just ask me anything in natural language!")

    # Fallback
    return ("🤔 I'm not sure about that. Try asking about:\n"
            "attendance, assignments, exams, timetable, notifications, or LMS.")


@campus_bp.route('/assistant', methods=['GET'])
@campus_login_required
def assistant():
    org_id = session.get('org_id')
    from app import ChatMessage
    # Load last 20 messages for this session
    chat_session_id = session.get('chat_session_id')
    if not chat_session_id:
        chat_session_id = str(uuid.uuid4())
        session['chat_session_id'] = chat_session_id
    history = ChatMessage.query.filter_by(session_id=chat_session_id).order_by(ChatMessage.timestamp).limit(30).all()
    return render_template('campus/assistant.html', history=history)


@campus_bp.route('/assistant/chat', methods=['POST'])
@campus_login_required
def assistant_chat():
    from app import db, ChatMessage
    data = request.get_json()
    user_msg = data.get('message', '').strip()
    if not user_msg:
        return jsonify({'error': 'Empty message'}), 400
    org_id = session.get('org_id')
    chat_session_id = session.get('chat_session_id', str(uuid.uuid4()))
    session['chat_session_id'] = chat_session_id

    # Save user message
    db.session.add(ChatMessage(session_id=chat_session_id, role='user', message=user_msg, org_id=org_id))

    # Get bot response
    bot_reply = ai_bot_response(user_msg, org_id)

    # Save bot response
    db.session.add(ChatMessage(session_id=chat_session_id, role='bot', message=bot_reply, org_id=org_id))
    db.session.commit()

    return jsonify({'reply': bot_reply})


# ─────────────────────────────────────────────
# AI ATTENDANCE PREDICTION
# ─────────────────────────────────────────────

@campus_bp.route('/ai/attendance-prediction')
@staff_or_admin_required
def ai_attendance_prediction():
    from app import db, Student, Attendance, Class_
    org_id = session.get('org_id')
    classes = Class_.query.filter_by(organization_id=org_id).all()
    class_id = request.args.get('class_id', type=int)

    predictions = []
    weekly_labels = []
    weekly_data = []
    monthly_labels = []
    monthly_data = []

    # Weekly trend — last 7 days
    today = date.today()
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        query = Attendance.query.join(Student).filter(Student.organization_id == org_id, Attendance.date == d)
        if class_id:
            query = query.filter(Attendance.class_id == class_id)
        present = query.filter(Attendance._status == 'present').count()
        total = query.count()
        pct = round((present / total * 100), 1) if total else 0
        weekly_labels.append(d.strftime('%a %d'))
        weekly_data.append(pct)

    # Monthly trend — last 4 weeks
    for i in range(3, -1, -1):
        start = today - timedelta(weeks=i+1)
        end = today - timedelta(weeks=i)
        query = Attendance.query.join(Student).filter(
            Student.organization_id == org_id,
            Attendance.date.between(start, end)
        )
        if class_id:
            query = query.filter(Attendance.class_id == class_id)
        present = query.filter(Attendance._status == 'present').count()
        total = query.count()
        pct = round((present / total * 100), 1) if total else 0
        monthly_labels.append(f"Week {4-i}")
        monthly_data.append(pct)

    # Per-student predictions (scikit-learn linear regression on past 30 days)
    students = Student.query.filter_by(organization_id=org_id)
    if class_id:
        students = students.filter_by(class_id=class_id)
    students = students.all()

    try:
        import numpy as np
        from sklearn.linear_model import LinearRegression
        use_ml = True
    except ImportError:
        use_ml = False

    threshold = 75
    for s in students:
        records = Attendance.query.filter_by(student_id=s.id).order_by(Attendance.date).all()
        total = len(records)
        present = sum(1 for r in records if r._status == 'present')
        current_pct = round((present / total * 100), 1) if total else 0

        # Predict next 7-day percentage using linear regression
        predicted_pct = current_pct
        if use_ml and total >= 5:
            try:
                X = np.array(range(total)).reshape(-1, 1)
                y = np.array([1 if r._status == 'present' else 0 for r in records], dtype=float)
                model = LinearRegression().fit(X, y)
                future_avg = model.predict([[total + 7]])[0]
                predicted_pct = round(min(100, max(0, future_avg * 100)), 1)
            except Exception:
                predicted_pct = current_pct

        risk_level = 'high' if current_pct < 60 else ('medium' if current_pct < 75 else 'low')
        detention_prob = max(0, min(100, round((75 - current_pct) * 3, 1))) if current_pct < 75 else 0

        predictions.append({
            'name': s.name,
            'roll': s.roll_number,
            'current': current_pct,
            'predicted': predicted_pct,
            'risk': risk_level,
            'detention_prob': detention_prob,
            'total_classes': total
        })

    predictions.sort(key=lambda x: x['current'])

    return render_template('campus/ai_prediction.html',
        classes=classes, class_id=class_id,
        predictions=predictions,
        weekly_labels=json.dumps(weekly_labels),
        weekly_data=json.dumps(weekly_data),
        monthly_labels=json.dumps(monthly_labels),
        monthly_data=json.dumps(monthly_data),
        at_risk_count=sum(1 for p in predictions if p['risk'] != 'low'),
        avg_attendance=round(sum(p['current'] for p in predictions) / len(predictions), 1) if predictions else 0
    )


# ─────────────────────────────────────────────
# AI STUDENT PERFORMANCE PREDICTION
# ─────────────────────────────────────────────

@campus_bp.route('/ai/performance')
@staff_or_admin_required
def ai_performance():
    from app import db, Student, Attendance, InternalMark, Exam, Class_
    org_id = session.get('org_id')
    classes = Class_.query.filter_by(organization_id=org_id).all()
    class_id = request.args.get('class_id', type=int)

    students_q = Student.query.filter_by(organization_id=org_id)
    if class_id:
        students_q = students_q.filter_by(class_id=class_id)
    students = students_q.all()

    performance_data = []
    for s in students:
        # Attendance percentage
        total_att = Attendance.query.filter_by(student_id=s.id).count()
        present_att = Attendance.query.filter_by(student_id=s.id, _status='present').count()
        att_pct = round((present_att / total_att * 100), 1) if total_att else 0

        # Internal marks average
        marks = InternalMark.query.filter_by(student_id=s.id).all()
        if marks:
            mark_vals = []
            for m in marks:
                exam = Exam.query.get(m.exam_id)
                if exam and exam.max_marks and m.marks_obtained is not None:
                    mark_vals.append(m.marks_obtained / exam.max_marks * 100)
            avg_marks = round(sum(mark_vals) / len(mark_vals), 1) if mark_vals else 0
        else:
            avg_marks = None

        # GPA prediction (weighted: 60% marks + 40% attendance)
        if avg_marks is not None:
            score = 0.6 * avg_marks + 0.4 * att_pct
        else:
            score = att_pct * 0.4
        predicted_gpa = round(score / 25, 2)  # scale to 4.0
        predicted_gpa = min(4.0, predicted_gpa)

        # Intervention needed
        intervention = (att_pct < 75) or (avg_marks is not None and avg_marks < 50)

        # Suggestions
        suggestions = []
        if att_pct < 75:
            suggestions.append("⚠️ Improve attendance urgently (below 75%)")
        if avg_marks is not None and avg_marks < 50:
            suggestions.append("📚 Additional study sessions recommended")
        if avg_marks is not None and avg_marks >= 80 and att_pct >= 90:
            suggestions.append("🌟 Excellent performance — consider advanced challenges")
        if not suggestions:
            suggestions.append("✅ Keep up the good work!")

        performance_data.append({
            'name': s.name,
            'roll': s.roll_number,
            'att_pct': att_pct,
            'avg_marks': avg_marks,
            'predicted_gpa': predicted_gpa,
            'intervention': intervention,
            'suggestions': suggestions
        })

    performance_data.sort(key=lambda x: x['predicted_gpa'], reverse=True)
    intervention_count = sum(1 for p in performance_data if p['intervention'])

    # Chart data
    chart_labels = [p['roll'] for p in performance_data[:15]]
    chart_att = [p['att_pct'] for p in performance_data[:15]]
    chart_marks = [p['avg_marks'] if p['avg_marks'] is not None else 0 for p in performance_data[:15]]

    return render_template('campus/performance.html',
        classes=classes, class_id=class_id,
        performance_data=performance_data,
        intervention_count=intervention_count,
        chart_labels=json.dumps(chart_labels),
        chart_att=json.dumps(chart_att),
        chart_marks=json.dumps(chart_marks)
    )


# ─────────────────────────────────────────────
# ACADEMIC ERP — TIMETABLE
# ─────────────────────────────────────────────

@campus_bp.route('/academic/timetable')
@campus_login_required
def timetable():
    from app import Timetable, Class_, Subject, Attendance
    org_id = session.get('org_id')
    classes = Class_.query.filter_by(organization_id=org_id).all()
    class_id = request.args.get('class_id', type=int) or (classes[0].id if classes else None)

    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    today_day = datetime.now().strftime('%A')
    today_date = date.today()

    slots = {}
    if class_id:
        entries = Timetable.query.filter_by(class_id=class_id, organization_id=org_id).all()
        for e in entries:
            if e.day_of_week not in slots:
                slots[e.day_of_week] = []
            slots[e.day_of_week].append(e)

    # Today's timetable entries in chronological order across the organization / selected class
    today_query = Timetable.query.filter_by(organization_id=org_id, day_of_week=today_day)
    if class_id:
        today_query = today_query.filter_by(class_id=class_id)
    today_slots_raw = today_query.order_by(Timetable.start_time).all()

    today_slots = []
    for slot in today_slots_raw:
        slot_class = Class_.query.get(slot.class_id)
        class_name = slot_class.name if slot_class else f"Class #{slot.class_id}"
        total_students = len(slot_class.students) if slot_class else 0
        
        # Check attendance for this class today
        present_count = Attendance.query.filter_by(
            class_id=slot.class_id, 
            date=today_date, 
            _status='present'
        ).count()
        total_marked = Attendance.query.filter_by(
            class_id=slot.class_id, 
            date=today_date
        ).count()

        today_slots.append({
            'id': slot.id,
            'class_id': slot.class_id,
            'class_name': class_name,
            'subject_name': slot.subject_name or 'General Class',
            'start_time': slot.start_time,
            'end_time': slot.end_time,
            'room': slot.room or 'Main Hall',
            'faculty': slot.faculty or 'Instructor',
            'total_students': total_students,
            'present_count': present_count,
            'total_marked': total_marked,
            'is_marked': total_marked > 0
        })

    return render_template(
        'campus/timetable.html', 
        days=days, 
        slots=slots, 
        classes=classes, 
        class_id=class_id,
        today_day=today_day,
        today_slots=today_slots
    )


@campus_bp.route('/academic/timetable/mark/<int:entry_id>')
@campus_login_required
def timetable_mark_attendance(entry_id):
    """Directly launch attendance marking for a timetable slot in sequence."""
    from app import Timetable, Class_
    entry = Timetable.query.get_or_404(entry_id)
    org_type = session.get('org_type', 'school')
    
    # Store timetable context in session for sequential attendance flow
    session['timetable_current_slot'] = entry_id
    session['timetable_class_id'] = entry.class_id
    session['timetable_subject_name'] = entry.subject_name
    
    flash(f"Ready to mark attendance for Period: {entry.subject_name} ({entry.start_time} - {entry.end_time})", 'info')
    
    # Redirect to corresponding organization's attendance engine with prefilled parameters
    if org_type == 'college':
        return redirect(url_for('college_mark_attendance', class_id=entry.class_id, subject=entry.subject_name))
    elif org_type == 'institution':
        return redirect(url_for('institution_mark_attendance', class_id=entry.class_id, subject=entry.subject_name))
    else:
        return redirect(url_for('school_mark_attendance', class_id=entry.class_id))


@campus_bp.route('/academic/timetable/add', methods=['POST'])
@admin_required
def add_timetable():
    from app import db, Timetable
    org_id = session.get('org_id')
    entry = Timetable(
        class_id=int(request.form['class_id']),
        subject_name=request.form.get('subject_name', ''),
        day_of_week=request.form['day_of_week'],
        start_time=request.form['start_time'],
        end_time=request.form['end_time'],
        room=request.form.get('room', ''),
        faculty=request.form.get('faculty', ''),
        organization_id=org_id
    )
    db.session.add(entry)
    db.session.commit()
    log_audit(f"Added timetable entry for class {request.form['class_id']}")
    flash('Timetable entry added!', 'success')
    return redirect(url_for('campus.timetable', class_id=request.form['class_id']))


@campus_bp.route('/academic/timetable/delete/<int:entry_id>', methods=['POST'])
@admin_required
def delete_timetable(entry_id):
    from app import db, Timetable
    entry = Timetable.query.get_or_404(entry_id)
    class_id = entry.class_id
    db.session.delete(entry)
    db.session.commit()
    flash('Entry deleted.', 'success')
    return redirect(url_for('campus.timetable', class_id=class_id))


# ─────────────────────────────────────────────
# ACADEMIC ERP — EXAMS & INTERNAL MARKS
# ─────────────────────────────────────────────

@campus_bp.route('/academic/exams')
@admin_required
def exams():
    from app import Exam, Class_
    org_id = session.get('org_id')
    classes = Class_.query.filter_by(organization_id=org_id).all()
    class_id = request.args.get('class_id', type=int)
    q = Exam.query.filter_by(organization_id=org_id)
    if class_id:
        q = q.filter_by(class_id=class_id)
    exams_list = q.order_by(Exam.date.desc()).all()
    return render_template('campus/exams.html', exams=exams_list, classes=classes, class_id=class_id)


@campus_bp.route('/academic/exams/add', methods=['POST'])
@admin_required
def add_exam():
    from app import db, Exam
    org_id = session.get('org_id')
    date_val = None
    if request.form.get('date'):
        try:
            date_val = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
        except ValueError:
            pass
    exam = Exam(
        name=request.form['name'],
        exam_type=request.form.get('exam_type', 'internal'),
        class_id=int(request.form['class_id']),
        subject_name=request.form.get('subject_name', ''),
        date=date_val,
        max_marks=float(request.form.get('max_marks', 100)),
        organization_id=org_id
    )
    db.session.add(exam)
    db.session.commit()
    flash('Exam added successfully!', 'success')
    return redirect(url_for('campus.exams', class_id=request.form['class_id']))


@campus_bp.route('/academic/marks')
@admin_required
def internal_marks():
    from app import InternalMark, Exam, Student, Class_
    org_id = session.get('org_id')
    classes = Class_.query.filter_by(organization_id=org_id).all()
    class_id = request.args.get('class_id', type=int)
    exam_id = request.args.get('exam_id', type=int)
    exams_list = Exam.query.filter_by(organization_id=org_id)
    if class_id:
        exams_list = exams_list.filter_by(class_id=class_id)
    exams_list = exams_list.all()

    students = []
    marks_map = {}
    selected_exam = None
    if exam_id:
        selected_exam = Exam.query.get(exam_id)
        if selected_exam:
            students = Student.query.filter_by(class_id=selected_exam.class_id).all()
            for m in InternalMark.query.filter_by(exam_id=exam_id).all():
                marks_map[m.student_id] = m

    return render_template('campus/marks.html',
        classes=classes, class_id=class_id, exams=exams_list,
        exam_id=exam_id, selected_exam=selected_exam,
        students=students, marks_map=marks_map)


@campus_bp.route('/academic/marks/save', methods=['POST'])
@admin_required
def save_marks():
    from app import db, InternalMark
    exam_id = int(request.form['exam_id'])
    student_ids = request.form.getlist('student_id')
    for sid in student_ids:
        marks_val = request.form.get(f'marks_{sid}', '')
        if marks_val:
            existing = InternalMark.query.filter_by(exam_id=exam_id, student_id=int(sid)).first()
            if existing:
                existing.marks_obtained = float(marks_val)
                existing.grade = _compute_grade(float(marks_val), 100)
            else:
                db.session.add(InternalMark(
                    student_id=int(sid),
                    exam_id=exam_id,
                    marks_obtained=float(marks_val),
                    grade=_compute_grade(float(marks_val), 100)
                ))
    db.session.commit()
    flash('Marks saved successfully!', 'success')
    return redirect(url_for('campus.internal_marks', exam_id=exam_id))


def _compute_grade(marks, max_marks):
    pct = (marks / max_marks) * 100
    if pct >= 90: return 'O'
    elif pct >= 80: return 'A+'
    elif pct >= 70: return 'A'
    elif pct >= 60: return 'B+'
    elif pct >= 50: return 'B'
    elif pct >= 40: return 'C'
    return 'F'


# ─────────────────────────────────────────────
# ASSIGNMENT MANAGEMENT
# ─────────────────────────────────────────────

ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'txt', 'png', 'jpg', 'zip', 'pptx', 'xlsx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@campus_bp.route('/assignments')
@campus_login_required
def assignments():
    from app import Assignment, Class_, AssignmentSubmission
    org_id = session.get('org_id')
    is_admin = 'user_id' in session
    is_staff = 'staff_id' in session
    is_student = 'student_id' in session

    if is_student:
        sid = session['student_id']
        from app import Student
        student = Student.query.get(sid)
        if student:
            asgns = Assignment.query.filter_by(class_id=student.class_id, organization_id=org_id).order_by(Assignment.deadline).all()
        else:
            asgns = []
        my_submissions = {s.assignment_id: s for s in AssignmentSubmission.query.filter_by(student_id=sid).all()}
        return render_template('campus/assignments_student.html', assignments=asgns, my_submissions=my_submissions)

    # Admin / staff view
    classes = Class_.query.filter_by(organization_id=org_id).all()
    class_id = request.args.get('class_id', type=int)
    q = Assignment.query.filter_by(organization_id=org_id)
    if class_id:
        q = q.filter_by(class_id=class_id)
    asgns = q.order_by(Assignment.deadline).all()
    return render_template('campus/assignments_teacher.html', assignments=asgns, classes=classes, class_id=class_id)


@campus_bp.route('/assignments/create', methods=['POST'])
@admin_required
def create_assignment():
    from app import db, Assignment
    org_id = session.get('org_id')
    file_path = None
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename and allowed_file(file.filename):
            fn = secure_filename(file.filename)
            dest = os.path.join('uploads', 'assignments', fn)
            os.makedirs(os.path.join('uploads', 'assignments'), exist_ok=True)
            file.save(dest)
            file_path = dest

    deadline = None
    if request.form.get('deadline'):
        try:
            deadline = datetime.strptime(request.form['deadline'], '%Y-%m-%dT%H:%M')
        except ValueError:
            pass

    asgn = Assignment(
        title=request.form['title'],
        description=request.form.get('description', ''),
        deadline=deadline,
        file_path=file_path,
        class_id=int(request.form['class_id']),
        max_marks=float(request.form.get('max_marks', 100)),
        organization_id=org_id
    )
    db.session.add(asgn)
    db.session.commit()
    log_audit(f"Created assignment '{asgn.title}'")
    flash('Assignment created!', 'success')
    return redirect(url_for('campus.assignments'))


@campus_bp.route('/assignments/<int:asgn_id>/submissions')
@admin_required
def assignment_submissions(asgn_id):
    from app import Assignment, AssignmentSubmission, Student
    asgn = Assignment.query.get_or_404(asgn_id)
    subs = AssignmentSubmission.query.filter_by(assignment_id=asgn_id).all()
    students = Student.query.filter_by(class_id=asgn.class_id).all()
    sub_map = {s.student_id: s for s in subs}
    return render_template('campus/submissions.html', asgn=asgn, students=students, sub_map=sub_map)


@campus_bp.route('/assignments/<int:asgn_id>/grade', methods=['POST'])
@admin_required
def grade_submission(asgn_id):
    from app import db, AssignmentSubmission
    sub_id = int(request.form['submission_id'])
    sub = AssignmentSubmission.query.get_or_404(sub_id)
    sub.marks = float(request.form.get('marks', 0))
    sub.feedback = request.form.get('feedback', '')
    sub.status = 'graded'
    db.session.commit()
    flash('Marks saved!', 'success')
    return redirect(url_for('campus.assignment_submissions', asgn_id=asgn_id))


@campus_bp.route('/assignments/<int:asgn_id>/submit', methods=['POST'])
def submit_assignment(asgn_id):
    if 'student_id' not in session:
        return jsonify({'error': 'Not logged in as student'}), 401
    from app import db, AssignmentSubmission
    sid = session['student_id']
    existing = AssignmentSubmission.query.filter_by(assignment_id=asgn_id, student_id=sid).first()
    if existing:
        flash('You have already submitted this assignment.', 'warning')
        return redirect(url_for('campus.assignments'))

    file_path = None
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename and allowed_file(file.filename):
            fn = secure_filename(file.filename)
            dest = os.path.join('uploads', 'submissions', fn)
            os.makedirs(os.path.join('uploads', 'submissions'), exist_ok=True)
            file.save(dest)
            file_path = dest

    from app import Assignment
    asgn = Assignment.query.get(asgn_id)
    status = 'late' if (asgn and asgn.deadline and datetime.now() > asgn.deadline) else 'submitted'

    sub = AssignmentSubmission(
        assignment_id=asgn_id,
        student_id=sid,
        file_path=file_path,
        text_content=request.form.get('text_content', ''),
        status=status
    )
    db.session.add(sub)
    db.session.commit()
    flash('Assignment submitted successfully!', 'success')
    return redirect(url_for('campus.assignments'))


# ─────────────────────────────────────────────
# LMS — Learning Management System
# ─────────────────────────────────────────────

@campus_bp.route('/lms')
@campus_login_required
def lms():
    from app import LMSContent, Class_, Quiz, QuizSubmission
    org_id = session.get('org_id')
    classes = Class_.query.filter_by(organization_id=org_id).all()
    class_id = request.args.get('class_id', type=int)
    content_type = request.args.get('type')

    q = LMSContent.query.filter_by(organization_id=org_id)
    if class_id:
        q = q.filter_by(class_id=class_id)
    if content_type:
        q = q.filter_by(content_type=content_type)
    content = q.order_by(LMSContent.created_at.desc()).all()

    quizzes = Quiz.query.filter_by(organization_id=org_id)
    if class_id:
        quizzes = quizzes.filter_by(class_id=class_id)
    quizzes = quizzes.all()

    is_admin = 'user_id' in session or 'staff_id' in session
    return render_template('campus/lms.html',
        content=content, classes=classes, class_id=class_id,
        content_type=content_type, quizzes=quizzes, is_admin=is_admin)


@campus_bp.route('/lms/upload', methods=['POST'])
@admin_required
def lms_upload():
    from app import db, LMSContent
    org_id = session.get('org_id')
    file_path = None
    if 'file' in request.files:
        file = request.files['file']
        if file and file.filename:
            fn = secure_filename(file.filename)
            dest = os.path.join('uploads', 'lms', fn)
            os.makedirs(os.path.join('uploads', 'lms'), exist_ok=True)
            file.save(dest)
            file_path = dest

    content = LMSContent(
        title=request.form['title'],
        description=request.form.get('description', ''),
        content_type=request.form['content_type'],
        file_path=file_path,
        external_url=request.form.get('external_url', ''),
        class_id=int(request.form['class_id']),
        duration=request.form.get('duration', ''),
        organization_id=org_id
    )
    db.session.add(content)
    db.session.commit()
    flash('Content uploaded to LMS!', 'success')
    return redirect(url_for('campus.lms', class_id=request.form['class_id']))


@campus_bp.route('/lms/delete/<int:content_id>', methods=['POST'])
@admin_required
def lms_delete(content_id):
    from app import db, LMSContent
    c = LMSContent.query.get_or_404(content_id)
    db.session.delete(c)
    db.session.commit()
    flash('Content removed.', 'success')
    return redirect(url_for('campus.lms'))


@campus_bp.route('/lms/quiz/create', methods=['POST'])
@admin_required
def create_quiz():
    from app import db, Quiz
    org_id = session.get('org_id')
    questions = []
    q_texts = request.form.getlist('question[]')
    opts_a = request.form.getlist('opt_a[]')
    opts_b = request.form.getlist('opt_b[]')
    opts_c = request.form.getlist('opt_c[]')
    opts_d = request.form.getlist('opt_d[]')
    answers = request.form.getlist('answer[]')
    for i, qt in enumerate(q_texts):
        if qt.strip():
            questions.append({
                'q': qt, 'a': opts_a[i] if i < len(opts_a) else '',
                'b': opts_b[i] if i < len(opts_b) else '',
                'c': opts_c[i] if i < len(opts_c) else '',
                'd': opts_d[i] if i < len(opts_d) else '',
                'answer': answers[i] if i < len(answers) else 'a'
            })
    quiz = Quiz(
        title=request.form['title'],
        class_id=int(request.form['class_id']),
        questions_json=json.dumps(questions),
        duration_minutes=int(request.form.get('duration', 30)),
        max_marks=float(request.form.get('max_marks', 10)),
        organization_id=org_id
    )
    db.session.add(quiz)
    db.session.commit()
    flash('Quiz created!', 'success')
    return redirect(url_for('campus.lms'))


@campus_bp.route('/lms/quiz/<int:quiz_id>')
@campus_login_required
def take_quiz(quiz_id):
    from app import Quiz
    quiz = Quiz.query.get_or_404(quiz_id)
    questions = json.loads(quiz.questions_json or '[]')
    return render_template('campus/quiz.html', quiz=quiz, questions=questions)


@campus_bp.route('/lms/quiz/<int:quiz_id>/submit', methods=['POST'])
def submit_quiz(quiz_id):
    from app import db, Quiz, QuizSubmission
    if 'student_id' not in session:
        return redirect(url_for('student_login'))
    quiz = Quiz.query.get_or_404(quiz_id)
    questions = json.loads(quiz.questions_json or '[]')
    answers = {}
    score = 0
    for i, q in enumerate(questions):
        ans = request.form.get(f'q_{i}', '')
        answers[str(i)] = ans
        if ans.lower() == q.get('answer', '').lower():
            score += 1
    marks = round((score / len(questions)) * quiz.max_marks, 1) if questions else 0
    sub = QuizSubmission(
        quiz_id=quiz_id,
        student_id=session['student_id'],
        answers_json=json.dumps(answers),
        score=marks
    )
    db.session.add(sub)
    db.session.commit()
    flash(f'Quiz submitted! Your score: {marks}/{quiz.max_marks}', 'success')
    return redirect(url_for('campus.lms'))


# ─────────────────────────────────────────────
# PARENT PORTAL
# ─────────────────────────────────────────────

@campus_bp.route('/parent/login', methods=['GET', 'POST'])
def parent_login():
    if request.method == 'POST':
        from app import Parent
        email = request.form.get('email')
        password = request.form.get('password')
        parent = Parent.query.filter_by(email=email).first()
        if parent and check_password_hash(parent.password_hash, password):
            session['parent_id'] = parent.id
            session['parent_name'] = parent.name
            session['parent_student_id'] = parent.student_id
            session['org_id'] = parent.organization_id
            return redirect(url_for('campus.parent_dashboard'))
        flash('Invalid email or password', 'danger')
    return render_template('campus/parent_login.html')


@campus_bp.route('/parent/register', methods=['GET', 'POST'])
def parent_register():
    if request.method == 'POST':
        from app import db, Parent, Student
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        password = request.form.get('password')
        roll_number = request.form.get('roll_number')
        student = Student.query.filter_by(roll_number=roll_number).first()
        if not student:
            flash('Student roll number not found', 'danger')
            return redirect(url_for('campus.parent_register'))
        existing = Parent.query.filter_by(email=email).first()
        if existing:
            flash('Email already registered', 'danger')
            return redirect(url_for('campus.parent_register'))
        parent = Parent(
            name=name, email=email, phone=phone,
            password_hash=generate_password_hash(password),
            student_id=student.id,
            organization_id=student.organization_id
        )
        db.session.add(parent)
        db.session.commit()
        flash('Parent account created! Please login.', 'success')
        return redirect(url_for('campus.parent_login'))
    return render_template('campus/parent_register.html')


@campus_bp.route('/parent/dashboard')
def parent_dashboard():
    if 'parent_id' not in session:
        return redirect(url_for('campus.parent_login'))
    from app import Student, Attendance, Assignment, AssignmentSubmission, Timetable, Notification, InternalMark, Exam
    sid = session['parent_student_id']
    student = Student.query.get_or_404(sid)

    # Attendance summary
    total_att = Attendance.query.filter_by(student_id=sid).count()
    present_att = Attendance.query.filter_by(student_id=sid, _status='present').count()
    att_pct = round((present_att / total_att * 100), 1) if total_att else 0
    recent_att = Attendance.query.filter_by(student_id=sid).order_by(Attendance.date.desc()).limit(10).all()

    # Assignments
    asgns = Assignment.query.filter_by(class_id=student.class_id, organization_id=student.organization_id).all()
    sub_map = {s.assignment_id: s for s in AssignmentSubmission.query.filter_by(student_id=sid).all()}

    # Timetable
    today_day = datetime.now().strftime('%A')
    today_classes = Timetable.query.filter_by(class_id=student.class_id, day_of_week=today_day).order_by(Timetable.start_time).all()

    # Notifications
    notifs = Notification.query.filter_by(org_id=student.organization_id, is_read=False).order_by(Notification.created_at.desc()).limit(5).all()

    # Marks summary
    marks = InternalMark.query.filter_by(student_id=sid).all()
    marks_data = []
    for m in marks:
        exam = Exam.query.get(m.exam_id)
        marks_data.append({'exam': exam.name if exam else 'N/A', 'marks': m.marks_obtained, 'grade': m.grade})

    return render_template('campus/parent_dashboard.html',
        student=student, att_pct=att_pct, total_att=total_att,
        present_att=present_att, recent_att=recent_att,
        assignments=asgns, sub_map=sub_map,
        today_classes=today_classes, notifications=notifs,
        marks_data=marks_data)


@campus_bp.route('/parent/logout')
def parent_logout():
    session.pop('parent_id', None)
    session.pop('parent_name', None)
    session.pop('parent_student_id', None)
    return redirect(url_for('campus.parent_login'))


# ─────────────────────────────────────────────
# SMART NOTIFICATIONS
# ─────────────────────────────────────────────

@campus_bp.route('/notifications')
@campus_login_required
def notifications():
    from app import Notification
    org_id = session.get('org_id')
    notifs = Notification.query.filter_by(org_id=org_id).order_by(Notification.created_at.desc()).limit(50).all()
    unread = Notification.query.filter_by(org_id=org_id, is_read=False).count()
    return render_template('campus/notifications.html', notifications=notifs, unread=unread)


@campus_bp.route('/notifications/send', methods=['POST'])
@admin_required
def send_notification():
    from app import db, Notification, Student, Attendance
    org_id = session.get('org_id')
    title = request.form.get('title', 'Notification')
    message = request.form.get('message', '')
    notif_type = request.form.get('notif_type', 'info')
    user_type = request.form.get('user_type', 'all')

    notif = Notification(
        org_id=org_id, title=title, message=message,
        notif_type=notif_type, user_type=user_type
    )
    db.session.add(notif)

    # Auto-notify low attendance students
    if request.form.get('auto_low_attendance'):
        students = Student.query.filter_by(organization_id=org_id).all()
        for s in students:
            total = Attendance.query.filter_by(student_id=s.id).count()
            present = Attendance.query.filter_by(student_id=s.id, _status='present').count()
            if total > 0 and (present / total * 100) < 75:
                db.session.add(Notification(
                    org_id=org_id,
                    title='⚠️ Low Attendance Alert',
                    message=f'Dear {s.name}, your attendance is below 75%. Please improve.',
                    notif_type='danger',
                    user_type='student',
                    user_id=s.id
                ))

    db.session.commit()
    log_audit(f"Sent notification: {title}")
    flash('Notification sent!', 'success')
    return redirect(url_for('campus.notifications'))


@campus_bp.route('/notifications/mark-read', methods=['POST'])
@campus_login_required
def mark_notifications_read():
    from app import db, Notification
    org_id = session.get('org_id')
    Notification.query.filter_by(org_id=org_id, is_read=False).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})


# ─────────────────────────────────────────────
# ANALYTICS DASHBOARDS
# ─────────────────────────────────────────────

@campus_bp.route('/analytics/admin')
@admin_required
def analytics_admin():
    from app import db, Student, Attendance, Class_, Staff, Assignment, LMSContent, Exam, InternalMark
    org_id = session.get('org_id')
    today = date.today()

    total_students = Student.query.filter_by(organization_id=org_id).count()
    classes = Class_.query.filter_by(organization_id=org_id).all()
    total_classes = len(classes)
    total_staff = Staff.query.filter_by(organization_id=org_id).count()

    # Daily attendance last 30 days
    labels, att_data = [], []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        present = Attendance.query.join(Student).filter(
            Student.organization_id == org_id, Attendance.date == d, Attendance._status == 'present').count()
        total = Attendance.query.join(Student).filter(Student.organization_id == org_id, Attendance.date == d).count()
        pct = round(present / total * 100, 1) if total else 0
        labels.append(d.strftime('%d %b'))
        att_data.append(pct)

    # Per-class attendance & underperforming classes
    class_labels = []
    class_att = []
    underperforming = []
    for c in classes:
        stu_ids = [s.id for s in c.students]
        stu_count = len(stu_ids)
        total = Attendance.query.filter(Attendance.student_id.in_(stu_ids)).count() if stu_ids else 0
        present = Attendance.query.filter(Attendance.student_id.in_(stu_ids), Attendance._status == 'present').count() if stu_ids else 0
        c_pct = round(present / total * 100, 1) if total else 0
        class_labels.append(c.name)
        class_att.append(c_pct)
        if c_pct < 75 or (total == 0 and stu_count > 0):
            underperforming.append({
                'id': c.id,
                'name': c.name,
                'count': stu_count,
                'avg': c_pct
            })

    # Student-level distribution: Above 85%, 75-85%, Below 75%
    students = Student.query.filter_by(organization_id=org_id).all()
    dist_above_85 = 0
    dist_75_85 = 0
    dist_below_75 = 0
    risk_students_count = 0
    all_student_pcts = []

    for s in students:
        total = Attendance.query.filter_by(student_id=s.id).count()
        present = Attendance.query.filter_by(student_id=s.id, _status='present').count()
        pct = round(present / total * 100, 1) if total else 0
        all_student_pcts.append(pct)
        if pct >= 85:
            dist_above_85 += 1
        elif pct >= 75:
            dist_75_85 += 1
        else:
            dist_below_75 += 1
            risk_students_count += 1

    avg_campus_att = round(sum(all_student_pcts) / len(all_student_pcts), 1) if all_student_pcts else (
        round(sum(class_att) / len(class_att), 1) if class_att else 0
    )

    metrics = {
        'total_students': total_students,
        'total_classes': total_classes,
        'avg_attendance': avg_campus_att,
        'risk_students': risk_students_count,
        'underperforming': underperforming
    }

    # Assignment stats
    total_assignments = Assignment.query.filter_by(organization_id=org_id).count()
    total_lms = LMSContent.query.filter_by(organization_id=org_id).count()
    total_exams = Exam.query.filter_by(organization_id=org_id).count()

    # Grade distribution
    grades = ['O', 'A+', 'A', 'B+', 'B', 'C', 'F']
    grade_counts = []
    for g in grades:
        count = db.session.query(InternalMark).join(Exam).filter(
            Exam.organization_id == org_id, InternalMark.grade == g).count()
        grade_counts.append(count)

    dist_data = [dist_above_85, dist_75_85, dist_below_75]

    return render_template('campus/analytics_admin.html',
        metrics=metrics,
        chart_labels=json.dumps(class_labels),
        chart_data=json.dumps(class_att),
        dist_data=json.dumps(dist_data),
        total_students=total_students, total_classes=total_classes,
        total_staff=total_staff, total_assignments=total_assignments,
        total_lms=total_lms, total_exams=total_exams,
        labels=json.dumps(labels), att_data=json.dumps(att_data),
        class_labels=json.dumps(class_labels), class_att=json.dumps(class_att),
        grade_labels=json.dumps(grades), grade_counts=json.dumps(grade_counts))


@campus_bp.route('/analytics/faculty')
@campus_login_required
def analytics_faculty():
    from app import Student, Attendance, Class_
    org_id = session.get('org_id')
    classes = Class_.query.filter_by(organization_id=org_id).all()
    
    class_list = []
    total_students = 0
    all_pcts = []
    risk_count = 0

    for c in classes:
        stu_ids = [s.id for s in c.students]
        c_count = len(stu_ids)
        total_students += c_count
        total = Attendance.query.filter(Attendance.student_id.in_(stu_ids)).count() if stu_ids else 0
        present = Attendance.query.filter(Attendance.student_id.in_(stu_ids), Attendance._status == 'present').count() if stu_ids else 0
        c_avg = round(present / total * 100, 1) if total else 0
        all_pcts.append(c_avg)
        if c_avg < 75:
            risk_count += 1
        class_list.append({
            'id': c.id,
            'name': c.name,
            'count': c_count,
            'avg': c_avg
        })

    avg_attendance = round(sum(all_pcts) / len(all_pcts), 1) if all_pcts else 0
    metrics = {
        'total_classes': len(classes),
        'total_students': total_students,
        'avg_attendance': avg_attendance,
        'risk_students': risk_count,
        'classes': class_list
    }
    return render_template('campus/analytics_faculty.html', metrics=metrics)


@campus_bp.route('/analytics/student')
def analytics_student():
    if 'student_id' not in session:
        return redirect(url_for('student_login'))
    from app import Attendance, Assignment, AssignmentSubmission, InternalMark, Exam, LMSContent, QuizSubmission, Student
    sid = session['student_id']
    student = Student.query.get(sid)

    # Attendance trend (last 30 days)
    records = Attendance.query.filter_by(student_id=sid).order_by(Attendance.date).all()
    total = len(records)
    present = sum(1 for r in records if r._status == 'present')
    att_pct = round(present / total * 100, 1) if total else 0

    labels = [r.date.strftime('%d %b') for r in records[-30:]]
    status_vals = [1 if r._status == 'present' else 0 for r in records[-30:]]

    # Marks trend
    marks_records = InternalMark.query.filter_by(student_id=sid).all()
    m_labels = []
    m_vals = []
    summary_marks = []
    mark_pct_list = []
    for m in marks_records:
        exam = Exam.query.get(m.exam_id)
        if exam and m.marks_obtained is not None:
            pct = round(m.marks_obtained / exam.max_marks * 100, 1) if exam.max_marks else 0
            m_labels.append(exam.name[:20])
            m_vals.append(pct)
            mark_pct_list.append(pct)
            summary_marks.append({
                'exam': exam.name,
                'marks': m.marks_obtained,
                'max': exam.max_marks,
                'percentage': pct,
                'grade': m.grade or ('A' if pct >= 80 else ('B' if pct >= 60 else 'C'))
            })

    avg_marks = round(sum(mark_pct_list) / len(mark_pct_list), 1) if mark_pct_list else 0
    score = (0.6 * avg_marks + 0.4 * att_pct) if avg_marks > 0 else (att_pct * 0.4)
    predicted_gpa = round(min(4.0, score / 25), 2)

    summary = {
        'attendance_percentage': att_pct,
        'average_percentage': avg_marks,
        'predicted_gpa': predicted_gpa,
        'marks': summary_marks
    }

    # Quiz scores
    quiz_subs = QuizSubmission.query.filter_by(student_id=sid).all()
    quiz_scores = [q.score for q in quiz_subs if q.score is not None]
    avg_quiz = round(sum(quiz_scores) / len(quiz_scores), 1) if quiz_scores else 0

    # Assignment completion
    total_asgns = Assignment.query.filter_by(class_id=student.class_id).count() if student and student.class_id else 0
    submitted_asgns = AssignmentSubmission.query.filter_by(student_id=sid).count()

    return render_template('campus/analytics_student.html',
        summary=summary,
        att_pct=att_pct, total=total, present=present,
        labels=json.dumps(labels), status_vals=json.dumps(status_vals),
        m_labels=json.dumps(m_labels), m_vals=json.dumps(m_vals),
        avg_quiz=avg_quiz, total_asgns=total_asgns, submitted_asgns=submitted_asgns)


# ─────────────────────────────────────────────
# AI REPORT GENERATOR
# ─────────────────────────────────────────────

@campus_bp.route('/reports', methods=['GET', 'POST'])
@admin_required
def ai_reports():
    if request.method == 'POST':
        return generate_report()
    from app import Class_
    org_id = session.get('org_id')
    classes = Class_.query.filter_by(organization_id=org_id).all()
    return render_template('campus/ai_report.html', classes=classes)


@campus_bp.route('/reports/generate', methods=['POST'])
@admin_required
def generate_report():
    from app import db, Student, Attendance, Class_, InternalMark, Exam, Staff
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib import colors as rl_colors

    org_id = session.get('org_id')
    report_focus = request.form.get('focus') or request.form.get('report_type') or 'attendance'
    class_id = request.form.get('class_id', type=int)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=48, bottomMargin=36)
    elements = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('T', parent=styles['Heading1'], fontSize=16, textColor=rl_colors.HexColor('#4f46e5'), spaceAfter=4)
    sub_style = ParagraphStyle('S', parent=styles['Normal'], fontSize=9, textColor=rl_colors.HexColor('#6b7280'), spaceAfter=10)
    h2_style = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=12, textColor=rl_colors.HexColor('#1f2937'), spaceBefore=8, spaceAfter=4)
    summary_style = ParagraphStyle('Summ', parent=styles['Normal'], fontSize=9, textColor=rl_colors.HexColor('#374151'), spaceAfter=8, leading=12)

    org_name = session.get('org_name', 'Smart Institution')
    gen_time = datetime.now().strftime('%d %B %Y, %H:%M')

    # Selected Class info
    target_class = Class_.query.get(class_id) if class_id else None
    class_label = f"Class: {target_class.name}" if target_class else "All Classes"

    elements.append(Paragraph(f"<b>{org_name}</b> — AI Smart Campus Report", title_style))
    elements.append(Paragraph(f"Generated: {gen_time}  |  Scope: {class_label}  |  Focus: {report_focus.replace('_', ' ').title()}", sub_style))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=rl_colors.HexColor('#4f46e5')))
    elements.append(Spacer(1, 0.15*inch))

    students_query = Student.query.filter_by(organization_id=org_id)
    if class_id:
        students_query = students_query.filter_by(class_id=class_id)
    students = students_query.all()

    # Calculate aggregate numbers for AI Summary
    total_stus = len(students)
    at_risk_stus = []
    stu_att_list = []
    
    for s in students:
        t = Attendance.query.filter_by(student_id=s.id).count()
        p = Attendance.query.filter_by(student_id=s.id, _status='present').count()
        pct = round(p / t * 100, 1) if t else 0
        stu_att_list.append(pct)
        if pct < 75:
            at_risk_stus.append(s.name)

    avg_att = round(sum(stu_att_list) / len(stu_att_list), 1) if stu_att_list else 0

    # AI Executive Summary Block
    elements.append(Paragraph("<b>AI Executive Summary & Insights</b>", h2_style))
    summary_text = (
        f"This AI analysis evaluated <b>{total_stus} students</b> under <b>{class_label}</b>. "
        f"The current overall attendance is <b>{avg_att}%</b>. "
        + (f"<b>{len(at_risk_stus)} students</b> have attendance below the 75% regulatory threshold and are at risk of detention. Immediate advisory notices are recommended."
           if at_risk_stus else "All evaluated students are maintaining satisfactory attendance compliance (≥75%).")
    )
    elements.append(Paragraph(summary_text, summary_style))
    elements.append(Spacer(1, 0.1*inch))

    if report_focus in ['attendance', 'comprehensive']:
        elements.append(Paragraph("<b>1. Detailed Attendance & Risk Matrix</b>", h2_style))
        table_data = [['#', 'Name', 'Roll No', 'Total', 'Present', 'Absent', 'Attendance %', 'Status']]
        for i, s in enumerate(students, 1):
            total = Attendance.query.filter_by(student_id=s.id).count()
            present = Attendance.query.filter_by(student_id=s.id, _status='present').count()
            absent = total - present
            pct = round(present / total * 100, 1) if total else 0
            status_text = 'CRITICAL' if pct < 60 else ('AT RISK' if pct < 75 else 'GOOD')
            table_data.append([str(i), s.name[:18], s.roll_number or '-', str(total), str(present), str(absent), f"{pct}%", status_text])

        if len(table_data) == 1:
            table_data.append(['-', 'No student records found', '-', '-', '-', '-', '-', '-'])

        t = Table(table_data, colWidths=[20, 130, 75, 45, 50, 45, 80, 75])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), rl_colors.HexColor('#4f46e5')),
            ('TEXTCOLOR', (0, 0), (-1, 0), rl_colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, rl_colors.HexColor('#d1d5db')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor('#f9fafb')]),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 0.2*inch))

    if report_focus in ['academic', 'performance', 'comprehensive']:
        elements.append(Paragraph("<b>2. Academic Performance & Estimated GPA</b>", h2_style))
        table_data = [['#', 'Name', 'Roll No', 'Avg Marks %', 'Attendance %', 'Est. GPA', 'AI Outlook']]
        for i, s in enumerate(students, 1):
            marks = InternalMark.query.filter_by(student_id=s.id).all()
            avg_m = 0
            if marks:
                vals = []
                for m in marks:
                    ex = Exam.query.get(m.exam_id)
                    if ex and ex.max_marks and m.marks_obtained is not None:
                        vals.append(m.marks_obtained / ex.max_marks * 100)
                avg_m = round(sum(vals) / len(vals), 1) if vals else 0
            total = Attendance.query.filter_by(student_id=s.id).count()
            present = Attendance.query.filter_by(student_id=s.id, _status='present').count()
            att_pct = round(present / total * 100, 1) if total else 0
            gpa = min(4.0, round((0.6 * avg_m + 0.4 * att_pct) / 25, 2))
            outlook = 'Needs Support' if att_pct < 75 or avg_m < 50 else ('Distinction' if gpa >= 3.5 else 'On Track')
            table_data.append([str(i), s.name[:18], s.roll_number or '-', f"{avg_m}%", f"{att_pct}%", str(gpa), outlook])

        if len(table_data) == 1:
            table_data.append(['-', 'No academic marks found', '-', '-', '-', '-', '-'])

        t = Table(table_data, colWidths=[20, 130, 75, 75, 75, 65, 80])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), rl_colors.HexColor('#059669')),
            ('TEXTCOLOR', (0, 0), (-1, 0), rl_colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, rl_colors.HexColor('#d1d5db')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [rl_colors.white, rl_colors.HexColor('#f0fdf4')]),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 0.15*inch))

    # Recommendations footer
    elements.append(Paragraph("<b>Recommendations:</b>", ParagraphStyle('RecH', parent=styles['Normal'], fontSize=9, fontName='Helvetica-Bold', textColor=rl_colors.HexColor('#1f2937'))))
    elements.append(Paragraph("• Coordinate parent-teacher alerts for all students identified under the Critical or At-Risk tier.<br/>• Use the Smart Attendance Face Engine for consistent period-wise tracking across all daily timetable slots.", summary_style))

    doc.build(elements)
    buffer.seek(0)
    filename = f"smart_report_{report_focus}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    log_audit(f"Generated {report_focus} smart PDF report")
    return send_file(buffer, as_attachment=True, download_name=filename, mimetype='application/pdf')


# ─────────────────────────────────────────────
# SECURITY — 2FA & AUDIT LOGS
# ─────────────────────────────────────────────

@campus_bp.route('/security/audit-logs')
@admin_required
def audit_logs():
    from app import AuditLog
    org_id = session.get('org_id')
    logs = AuditLog.query.filter_by(org_id=org_id).order_by(AuditLog.timestamp.desc()).limit(100).all()
    return render_template('campus/audit_logs.html', logs=logs)


@campus_bp.route('/security/2fa/setup')
@admin_required
def setup_2fa():
    try:
        import pyotp
        secret = pyotp.random_base32()
        session['totp_secret'] = secret
        totp = pyotp.TOTP(secret)
        org_name = session.get('org_name', 'SmartCampus')
        username = session.get('username', 'user')
        provisioning_uri = totp.provisioning_uri(username, issuer_name=org_name)
        return render_template('campus/setup_2fa.html', secret=secret, qr_uri=provisioning_uri)
    except ImportError:
        flash('2FA requires pyotp. Run: pip install pyotp', 'warning')
        return redirect(url_for('campus.audit_logs'))


@campus_bp.route('/security/2fa/verify', methods=['POST'])
@admin_required
def verify_2fa():
    try:
        import pyotp
        secret = session.get('totp_secret')
        code = request.form.get('code', '')
        if secret and pyotp.TOTP(secret).verify(code):
            session['2fa_enabled'] = True
            flash('✅ 2FA enabled successfully!', 'success')
        else:
            flash('❌ Invalid code. Please try again.', 'danger')
    except ImportError:
        flash('2FA library not installed', 'danger')
    return redirect(url_for('campus.audit_logs'))


# ─────────────────────────────────────────────
# NOTIFICATION COUNT API (for badge in sidebar)
# ─────────────────────────────────────────────

@campus_bp.route('/api/notification-count')
@campus_login_required
def notification_count():
    from app import Notification
    org_id = session.get('org_id')
    count = Notification.query.filter_by(org_id=org_id, is_read=False).count()
    return jsonify({'count': count})


# ─────────────────────────────────────────────
# EXAM RESULTS
# ─────────────────────────────────────────────

class ExamResultRecord:
    """In-memory simple store — replace with DB model if persistence needed."""
    _store = []

    @classmethod
    def add(cls, record):
        record['id'] = len(cls._store) + 1
        cls._store.append(record)
        return record

    @classmethod
    def all_for_org(cls, org_id):
        return [r for r in cls._store if r.get('org_id') == org_id]


@campus_bp.route('/exam-results')
@campus_login_required
def exam_results():
    from app import Class_, Student, Exam
    org_id = session.get('org_id')
    classes = Class_.query.filter_by(organization_id=org_id).all()
    all_students = Student.query.filter_by(organization_id=org_id).all()
    exams = Exam.query.filter_by(organization_id=org_id).order_by(Exam.date.desc()).all()

    raw = ExamResultRecord.all_for_org(org_id)
    # Enrich with lookup names
    student_map = {s.id: s for s in all_students}
    class_map   = {c.id: c for c in classes}
    exam_map    = {e.id: e for e in exams}

    # Serialize students for frontend
    serialized_students = [
        {'id': s.id, 'name': s.name, 'roll_number': s.roll_number, 'class_id': s.class_id} 
        for s in all_students
    ]

    saved_results = []
    for r in raw:
        stu = student_map.get(r.get('student_id'))
        cls_ = class_map.get(r.get('class_id'))
        ex   = exam_map.get(r.get('exam_id'))
        saved_results.append({
            'id':           r['id'],
            'student_name': stu.name if stu else r.get('student_name', 'N/A'),
            'roll_number':  stu.roll_number if stu else '—',
            'exam_name':    ex.name if ex else r.get('exam_name', 'General Exam'),
            'class_name':   cls_.name if cls_ else '—',
            'class_id':     r.get('class_id', ''),
            'exam_id':      r.get('exam_id', ''),
            'total_marks':  r.get('total_marks', 0),
            'obtained':     r.get('obtained', 0),
        })

    return render_template('campus/exam_results.html',
                           classes=classes,
                           all_students=serialized_students,
                           exams=exams,
                           saved_results=saved_results)


@campus_bp.route('/exam-results/save-subject', methods=['POST'])
@campus_login_required
def save_exam_subject():
    from app import Student, Class_
    org_id = session.get('org_id')
    data   = request.get_json(silent=True) or {}

    class_id     = data.get('class_id')
    subject_name = data.get('subject_name', '').strip()
    exam_name    = data.get('exam_name', 'General Exam').strip()
    semester     = data.get('semester', '').strip()
    student_marks = data.get('student_marks', [])
    
    if not class_id or not subject_name or not student_marks:
        return jsonify({'error': 'Missing required fields: class, subject, or marks data.'}), 400

    students_updated = 0

    for sm in student_marks:
        student_id = sm.get('student_id')
        total      = sm.get('total', 0)
        obtained   = sm.get('obtained', 0)
        
        if not student_id:
            continue
            
        student_id = int(student_id)
        
        # Find existing record for this student + exam + semester
        existing_record = None
        for r in ExamResultRecord.all_for_org(org_id):
            if r.get('student_id') == student_id and r.get('exam_name') == exam_name and r.get('semester') == semester:
                existing_record = r
                break
                
        if existing_record:
            # Update existing record
            # Check if subject already exists and update it, else append
            subject_exists = False
            for sub in existing_record['subjects']:
                if sub['name'] == subject_name:
                    sub['total'] = total
                    sub['obtained'] = obtained
                    subject_exists = True
                    break
            
            if not subject_exists:
                existing_record['subjects'].append({
                    'name': subject_name,
                    'total': total,
                    'obtained': obtained
                })
                
            # Recalculate totals
            existing_record['total_marks'] = sum(s['total'] for s in existing_record['subjects'])
            existing_record['obtained'] = sum(s['obtained'] for s in existing_record['subjects'])
            
            pct = (existing_record['obtained'] / existing_record['total_marks'] * 100) if existing_record['total_marks'] > 0 else 0
            existing_record['percentage'] = round(pct, 2)
            existing_record['cgpa'] = round(pct / 9.5, 2)
            
            if pct >= 75: existing_record['result_label'] = 'Distinction'
            elif pct >= 60: existing_record['result_label'] = 'First Class'
            elif pct >= 35: existing_record['result_label'] = 'Pass'
            else: existing_record['result_label'] = 'Fail'
            
        else:
            # Create new record
            student_name = 'N/A'
            try:
                stu = Student.query.get(student_id)
                if stu: student_name = stu.name
            except Exception:
                pass
                
            pct = (obtained / total * 100) if total > 0 else 0
            if pct >= 75: result_label = 'Distinction'
            elif pct >= 60: result_label = 'First Class'
            elif pct >= 35: result_label = 'Pass'
            else: result_label = 'Fail'
            
            ExamResultRecord.add({
                'org_id':       org_id,
                'student_id':   student_id,
                'student_name': student_name,
                'class_id':     int(class_id),
                'exam_id':      None,
                'exam_name':    exam_name,
                'semester':     semester,
                'subjects':     [{'name': subject_name, 'total': total, 'obtained': obtained}],
                'total_marks':  total,
                'obtained':     obtained,
                'percentage':   round(pct, 2),
                'cgpa':         round(pct / 9.5, 2),
                'result_label': result_label,
                'created_at':   datetime.now().isoformat(),
            })
            
        students_updated += 1

    return jsonify({'success': f'Successfully saved {subject_name} marks for {students_updated} student(s).'})

# ─────────────────────────────────────────────
# FEEDBACK & SURVEYS
# ─────────────────────────────────────────────

class FeedbackStore:
    """In-memory store for feedback forms and responses."""
    surveys = []

    @classmethod
    def add_survey(cls, survey):
        survey['id'] = len(cls.surveys) + 1
        survey['responses'] = []
        cls.surveys.append(survey)
        return survey

    @classmethod
    def get_survey(cls, survey_id):
        for s in cls.surveys:
            if s['id'] == survey_id:
                return s
        return None

    @classmethod
    def get_surveys_for_org(cls, org_id):
        return [s for s in cls.surveys if s.get('org_id') == org_id]

    @classmethod
    def add_response(cls, survey_id, response):
        survey = cls.get_survey(survey_id)
        if survey:
            survey['responses'].append(response)
            return True
        return False


@campus_bp.route('/feedback')
@campus_login_required
def feedback():
    from app import Class_
    org_id = session.get('org_id')
    classes = Class_.query.filter_by(organization_id=org_id).all()
    class_map = {str(c.id): c.name for c in classes}
    
    all_surveys = FeedbackStore.get_surveys_for_org(org_id)
    
    # Format surveys for admin/staff view
    formatted_surveys = []
    for s in all_surveys:
        target_name = "All Students" if s['target'] == 'all' else class_map.get(str(s['target']), f"Class {s['target']}")
        formatted_surveys.append({
            'id': s['id'],
            'title': s['title'],
            'target_name': target_name,
            'questions': s['questions'],
            'responses': s['responses']
        })
        
    # Pending surveys for student view
    pending_surveys = []
    if session.get('student_id'):
        from app import Student
        student = Student.query.get(session['student_id'])
        if student:
            class_id_str = str(student.class_id)
            for s in all_surveys:
                # Check if survey targets this student
                if s['target'] == 'all' or str(s['target']) == class_id_str:
                    # Check if student already responded
                    has_responded = any(r.get('student_id') == student.id for r in s['responses'])
                    if not has_responded:
                        pending_surveys.append(s)
                        
    return render_template('campus/feedback.html', 
                           classes=classes, 
                           surveys=formatted_surveys[::-1], 
                           pending_surveys=pending_surveys[::-1])


@campus_bp.route('/feedback/create', methods=['POST'])
@campus_login_required
def create_feedback():
    org_id = session.get('org_id')
    data = request.get_json(silent=True) or {}
    
    title = data.get('title', '').strip()
    target = data.get('target', 'all')
    questions = data.get('questions', [])
    
    if not title or not questions:
        return jsonify({'error': 'Title and at least one question are required.'}), 400
        
    FeedbackStore.add_survey({
        'org_id': org_id,
        'title': title,
        'target': target,
        'questions': questions,
        'created_by': session.get('user_id') or session.get('staff_id'),
        'created_at': datetime.now().isoformat()
    })
    
    return jsonify({'success': 'Feedback form published successfully!'})


@campus_bp.route('/feedback/submit', methods=['POST'])
@campus_login_required
def submit_feedback():
    if not session.get('student_id'):
        return jsonify({'error': 'Only students can submit feedback.'}), 403
        
    data = request.get_json(silent=True) or {}
    survey_id = data.get('survey_id')
    answers = data.get('answers', [])
    
    if not survey_id or not answers:
        return jsonify({'error': 'Invalid submission data.'}), 400
        
    from app import Student
    student = Student.query.get(session['student_id'])
    student_name = student.name if student else 'Unknown Student'
    
    response = {
        'student_id': session['student_id'],
        'student_name': student_name,
        'answers': answers,
        'submitted_at': datetime.now().isoformat()
    }
    
    if FeedbackStore.add_response(int(survey_id), response):
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Survey not found.'}), 404


@campus_bp.route('/feedback/responses/<int:survey_id>')
@campus_login_required
def get_feedback_responses(survey_id):
    survey = FeedbackStore.get_survey(survey_id)
    if not survey:
        return "Survey not found.", 404
        
    if not survey['responses']:
        return '<div class="text-center text-muted"><i class="fas fa-inbox fa-3x mb-3 d-block" style="color:#cbd5e1"></i>No responses yet.</div>'
        
    html = f"<h6><strong>Survey:</strong> {survey['title']} ({len(survey['responses'])} Responses)</h6><hr>"
    
    for idx, resp in enumerate(survey['responses']):
        html += f"""
        <div class="card mb-3 shadow-sm border-0 bg-light">
            <div class="card-body">
                <h6 class="card-title text-primary"><i class="fas fa-user-graduate me-2"></i>{resp['student_name']}</h6>
                <div class="mt-3">
        """
        for ans in resp['answers']:
            html += f"""
                    <div class="mb-2">
                        <small class="text-muted fw-bold d-block">{ans['question']}</small>
                        <span>{ans['answer']}</span>
                    </div>
            """
        html += """
                </div>
            </div>
        </div>
        """
        
    return html

# ─────────────────────────────────────────────
# SETTINGS (Org Name & Logo)
# ─────────────────────────────────────────────

@campus_bp.route('/settings', methods=['GET', 'POST'])
@campus_login_required
def settings():
    if not session.get('user_id') and not session.get('staff_id'):
        flash("Admin or Staff access required to access settings.", "danger")
        return redirect(url_for('campus.dashboard'))
        
    from app import Organization, db
    import os
    from werkzeug.utils import secure_filename
    
    org_id = session.get('org_id')
    org = Organization.query.get(org_id)
    if not org:
        flash("Organization not found.", "danger")
        return redirect(url_for('campus.dashboard'))
        
    if request.method == 'POST':
        new_name = request.form.get('org_name', '').strip()
        if new_name:
            org.name = new_name
            session['org_name'] = new_name  # Update session so base template updates immediately
            
        # Handle logo upload
        if 'org_logo' in request.files:
            file = request.files['org_logo']
            if file and file.filename != '':
                filename = secure_filename(f"org_{org_id}_{file.filename}")
                upload_dir = os.path.join('static', 'uploads', 'logos')
                os.makedirs(upload_dir, exist_ok=True)
                file_path = os.path.join(upload_dir, filename)
                file.save(file_path)
                
                # Update db path
                org.logo_path = f"/static/uploads/logos/{filename}"
                session['org_logo'] = org.logo_path
                
        db.session.commit()
        flash("Organization settings updated successfully!", "success")
        return redirect(url_for('campus.settings'))
        
    # Ensure logo path is in session for the template
    if org.logo_path and 'org_logo' not in session:
        session['org_logo'] = org.logo_path
        
    return render_template('campus/settings.html', org=org)

