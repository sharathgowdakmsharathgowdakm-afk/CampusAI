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

# --- Additional API endpoints for face registration UI ---

@api_bp.route('/classes', methods=['GET'])
@jwt_required()
def get_classes():
    from app import Class_
    classes = Class_.query.all()
    result = [{'id': c.id, 'name': c.name, 'academic_year': c.academic_year, 'study_year': c.study_year} for c in classes]
    return jsonify({'classes': result}), 200

@api_bp.route('/classes/<int:class_id>/students', methods=['GET'])
@jwt_required()
def get_class_students(class_id):
    from app import Student
    students = Student.query.filter_by(class_id=class_id).all()
    result = [{'id': s.id, 'name': s.name, 'roll_number': s.roll_number, 'class_id': s.class_id} for s in students]
    return jsonify({'students': result}), 200

@api_bp.route('/register-face', methods=['POST'])
@jwt_required()
def register_face():
    """JWT-authenticated face registration (mobile/API clients).
    Accepts JSON: { student_id, images_base64: [data-URI, ...] }"""
    import base64, uuid, os
    from app import app, FaceEncoding, db
    import face_recognition

    data = request.get_json()
    student_id = data.get('student_id')
    images_b64 = data.get('images_base64', [])

    # Backward compat: also accept single image_base64
    if not images_b64 and data.get('image_base64'):
        images_b64 = [data['image_base64']]

    if not student_id or not images_b64:
        return jsonify({'success': False, 'error': 'Missing student_id or image data'}), 400

    success_count = 0
    for img_b64 in images_b64[:5]:
        try:
            if ',' in img_b64:
                img_b64 = img_b64.split(',', 1)[1]
            img_data = base64.b64decode(img_b64)
            filename = f"temp_{uuid.uuid4().hex}.jpg"
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            with open(temp_path, 'wb') as f:
                f.write(img_data)

            image = face_recognition.load_image_file(temp_path)
            locations = face_recognition.face_locations(image, model='hog')
            if not locations:
                os.remove(temp_path)
                continue
            encoding = face_recognition.face_encodings(image, known_face_locations=locations)[0]
            encoding_entry = FaceEncoding(student_id=student_id, encoding_data=encoding.tolist())
            db.session.add(encoding_entry)
            success_count += 1
            os.remove(temp_path)
        except Exception:
            continue

    if success_count == 0:
        return jsonify({'success': False, 'error': 'No faces detected in provided images'}), 400

    db.session.commit()
    return jsonify({'success': True, 'message': f'{success_count} face encoding(s) registered successfully'}), 200

