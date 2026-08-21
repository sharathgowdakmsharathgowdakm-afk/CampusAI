import re

with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update students functions
students_pattern = re.compile(
    r"@app\.route\('/(school|college|institution)/students'\)\n"
    r"@org_required\(\['(school|college|institution)'\]\)\n"
    r"def \1_students\(\):\n"
    r"    students = Student\.query\.filter_by\(organization_id=session\.get\('org_id'\)\)\.all\(\)\n"
    r"    return render_template\('\1/students\.html', students=students\)"
)

students_replacement = r"""@app.route('/\1/students')
@org_required(['\1'])
def \1_students():
    class_id = request.args.get('class_id')
    query = Student.query.filter_by(organization_id=session.get('org_id'))
    if class_id:
        query = query.filter_by(class_id=class_id)
    students = query.all()
    return render_template('\1/students.html', students=students)"""

content = students_pattern.sub(students_replacement, content)

# 2. Update face_register to pass classes
face_register_pattern = re.compile(
    r"(@app\.route\('/(school|college|institution)/face-register', methods=\['GET', 'POST'\]\)\n"
    r"@org_required\(\['(school|college|institution)'\]\)\n"
    r"def \2_face_register\(\):\n"
    r"    students = Student\.query\.filter_by(?:\(\n        organization_id=session\.get\('org_id'\)\n    \)|"
    r"\(organization_id=session\.get\('org_id'\)\))\.all\(\))"
)

def replace_face_register(match):
    return match.group(1).replace(
        "def " + match.group(2) + "_face_register():",
        "def " + match.group(2) + "_face_register():\n    classes = Class_.query.filter_by(organization_id=session.get('org_id')).all()"
    )

content = face_register_pattern.sub(replace_face_register, content)

face_register_return_pattern = re.compile(
    r"return render_template\('(school|college|institution)/face_register\.html', students=students\)"
)
content = face_register_return_pattern.sub(r"return render_template('\1/face_register.html', students=students, classes=classes)", content)

# 3. Update attendance-records to use filters
# school is multiline
school_attendance_pattern = re.compile(
    r"@app\.route\('/school/attendance-records'\)\n"
    r"@org_required\(\['school'\]\)\n"
    r"def school_attendance_records\(\):\n"
    r"    classes = Class_\.query\.filter_by\(organization_id=session\.get\('org_id'\)\)\.all\(\)\n"
    r"    records = \[\]\n\n"
    r"    for class_ in classes:\n"
    r"        attendances = Attendance\.query\.filter_by\(class_id=class_\.id\)\.all\(\)\n"
    r"        records\.extend\(attendances\)\n\n"
    r"    return render_template\('school/attendance_records\.html', records=records, classes=classes\)"
)

attendance_replacement_school = r"""@app.route('/school/attendance-records')
@org_required(['school'])
def school_attendance_records():
    classes = Class_.query.filter_by(organization_id=session.get('org_id')).all()
    class_id = request.args.get('class_id')
    date_str = request.args.get('date')

    query = Attendance.query.join(Class_).filter(Class_.organization_id == session.get('org_id'))
    if class_id:
        query = query.filter(Attendance.class_id == class_id)
    if date_str:
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            query = query.filter(Attendance.date == date_obj)
        except ValueError:
            pass

    records = query.order_by(Attendance.date.desc(), Attendance.time.desc()).all()
    return render_template('school/attendance_records.html', records=records, classes=classes, selected_class=class_id, selected_date=date_str)"""

content = school_attendance_pattern.sub(attendance_replacement_school, content)

# college and institution are single line list extends
other_attendance_pattern = re.compile(
    r"@app\.route\('/(college|institution)/attendance-records'\)\n"
    r"@org_required\(\['\1'\]\)\n"
    r"def \1_attendance_records\(\):\n"
    r"    classes = Class_\.query\.filter_by\(organization_id=session\.get\('org_id'\)\)\.all\(\)\n"
    r"    records = \[\]\n"
    r"    for class_ in classes:\n"
    r"        records\.extend\(Attendance\.query\.filter_by\(class_id=class_\.id\)\.all\(\)\)\n"
    r"    return render_template\('\1/attendance_records\.html', records=records, classes=classes\)"
)

def other_attendance_replace(match):
    org = match.group(1)
    return f"""@app.route('/{org}/attendance-records')
@org_required(['{org}'])
def {org}_attendance_records():
    classes = Class_.query.filter_by(organization_id=session.get('org_id')).all()
    class_id = request.args.get('class_id')
    date_str = request.args.get('date')

    query = Attendance.query.join(Class_).filter(Class_.organization_id == session.get('org_id'))
    if class_id:
        query = query.filter(Attendance.class_id == class_id)
    if date_str:
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            query = query.filter(Attendance.date == date_obj)
        except ValueError:
            pass

    records = query.order_by(Attendance.date.desc(), Attendance.time.desc()).all()
    return render_template('{org}/attendance_records.html', records=records, classes=classes, selected_class=class_id, selected_date=date_str)"""

content = other_attendance_pattern.sub(other_attendance_replace, content)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated app.py successfully!")
