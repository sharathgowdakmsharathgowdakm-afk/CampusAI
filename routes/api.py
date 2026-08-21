from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from datetime import datetime

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/login', methods=['POST'])
def api_login():
    from app import Student
    data = request.get_json()
    if not data or not data.get('roll_number') or not data.get('password'):
        return jsonify({"error": "Missing roll_number or password"}), 400
        
    student = Student.query.filter_by(roll_number=data.get('roll_number')).first()
    
    # In a real app, use check_password_hash. If not hashed, compare directly.
    # We will assume they are hashed, or fall back to plaintext for old records.
    if not student:
        return jsonify({"error": "Invalid credentials"}), 401
        
    if student.password != data.get('password') and not check_password_hash(student.password, data.get('password')):
        return jsonify({"error": "Invalid credentials"}), 401
        
    access_token = create_access_token(identity=str(student.id))
    return jsonify({
        "access_token": access_token,
        "student": {
            "id": student.id,
            "name": student.name,
            "roll_number": student.roll_number,
            "email": student.email,
            "class_id": student.class_id
        }
    }), 200

@api_bp.route('/attendance/daily', methods=['GET'])
@jwt_required()
def get_daily_attendance():
    from app import Attendance, Subject
    student_id = get_jwt_identity()
    
    # Get recent attendance
    records = Attendance.query.filter_by(student_id=student_id).order_by(Attendance.date.desc()).limit(30).all()
    
    result = []
    for r in records:
        subj_name = None
        if r.subject_id:
            subj = Subject.query.get(r.subject_id)
            if subj:
                subj_name = subj.name
                
        result.append({
            "date": r.date.strftime("%Y-%m-%d"),
            "time": r.time.strftime("%H:%M:%S") if r.time else None,
            "status": r.status,
            "subject": subj_name
        })
        
    return jsonify({"attendance": result}), 200

