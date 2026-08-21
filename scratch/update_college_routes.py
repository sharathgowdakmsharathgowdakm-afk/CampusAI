import re

app_py_path = 'app.py'
with open(app_py_path, 'r', encoding='utf-8') as f:
    app_content = f.read()

orgs = ['college', 'institution']

for org in orgs:
    # 1. Update students
    students_pattern = re.compile(
        rf"@app\.route\('/{org}/students'\)\n"
        rf"@org_required\(\['{org}'\]\)\n"
        rf"def {org}_students\(\):\n"
        rf"    class_id = request\.args\.get\('class_id'\)\n"
        rf"    query = Student\.query\.filter_by\(organization_id=session\.get\('org_id'\)\)\n"
        rf"    if class_id:\n"
        rf"        query = query\.filter_by\(class_id=class_id\)\n"
        rf"    students = query\.all\(\)\n"
        rf"    return render_template\('{org}/students\.html', students=students\)"
    )
    
    new_students = f"""@app.route('/{org}/students')
@org_required(['{org}'])
def {org}_students():
    class_id = request.args.get('class_id')
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    
    query = Student.query.join(Class_).filter(Student.organization_id == session.get('org_id'))
    if class_id:
        query = query.filter(Student.class_id == class_id)
    if course_id:
        query = query.filter(Class_.course_id == course_id)
    if year:
        query = query.filter(Class_.academic_year == year)
        
    students = query.all()
    return render_template('{org}/students.html', students=students, course_id=course_id, year=year)"""
    app_content = students_pattern.sub(new_students, app_content)

    # 2. Update add-student
    add_student_pattern = re.compile(
        rf"@app\.route\('/{org}/add-student', methods=\['GET', 'POST'\]\)\n"
        rf"@org_required\(\['{org}'\]\)\n"
        rf"def {org}_add_student\(\):\n"
        rf"    classes = Class_\.query\.filter_by\(organization_id=session\.get\('org_id'\)\)\.all\(\)"
    )
    new_add_student = f"""@app.route('/{org}/add-student', methods=['GET', 'POST'])
@org_required(['{org}'])
def {org}_add_student():
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    
    query = Class_.query.filter_by(organization_id=session.get('org_id'))
    if course_id: query = query.filter_by(course_id=course_id)
    if year: query = query.filter_by(academic_year=year)
    classes = query.all()"""
    app_content = add_student_pattern.sub(new_add_student, app_content)
    
    # 3. Update face-register
    face_reg_pattern = re.compile(
        rf"@app\.route\('/{org}/face-register', methods=\['GET', 'POST'\]\)\n"
        rf"@org_required\(\['{org}'\]\)\n"
        rf"def {org}_face_register\(\):\n"
        rf"    classes = Class_\.query\.filter_by\(organization_id=session\.get\('org_id'\)\)\.all\(\)\n"
        rf"    students = Student\.query\.filter_by\(organization_id=session\.get\('org_id'\)\)\.all\(\)"
    )
    new_face_reg = f"""@app.route('/{org}/face-register', methods=['GET', 'POST'])
@org_required(['{org}'])
def {org}_face_register():
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    
    cls_query = Class_.query.filter_by(organization_id=session.get('org_id'))
    if course_id: cls_query = cls_query.filter_by(course_id=course_id)
    if year: cls_query = cls_query.filter_by(academic_year=year)
    classes = cls_query.all()
    class_ids = [c.id for c in classes]
    
    if class_ids:
        students = Student.query.filter(Student.class_id.in_(class_ids)).all()
    else:
        students = []"""
    app_content = face_reg_pattern.sub(new_face_reg, app_content)

    # 4. Update mark-attendance
    mark_att_pattern = re.compile(
        rf"@app\.route\('/{org}/mark-attendance', methods=\['GET', 'POST'\]\)\n"
        rf"@org_required\(\['{org}'\]\)\n"
        rf"def {org}_mark_attendance\(\):\n"
        rf"    classes = Class_\.query\.filter_by\(organization_id=session\.get\('org_id'\)\)\.all\(\)"
    )
    new_mark_att = f"""@app.route('/{org}/mark-attendance', methods=['GET', 'POST'])
@org_required(['{org}'])
def {org}_mark_attendance():
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    
    query = Class_.query.filter_by(organization_id=session.get('org_id'))
    if course_id: query = query.filter_by(course_id=course_id)
    if year: query = query.filter_by(academic_year=year)
    classes = query.all()"""
    app_content = mark_att_pattern.sub(new_mark_att, app_content)

    # 5. Update attendance-records
    att_rec_pattern = re.compile(
        rf"@app\.route\('/{org}/attendance-records'\)\n"
        rf"@org_required\(\['{org}'\]\)\n"
        rf"def {org}_attendance_records\(\):\n"
        rf"    classes = Class_\.query\.filter_by\(organization_id=session\.get\('org_id'\)\)\.all\(\)"
    )
    new_att_rec = f"""@app.route('/{org}/attendance-records')
@org_required(['{org}'])
def {org}_attendance_records():
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    
    cls_query = Class_.query.filter_by(organization_id=session.get('org_id'))
    if course_id: cls_query = cls_query.filter_by(course_id=course_id)
    if year: cls_query = cls_query.filter_by(academic_year=year)
    classes = cls_query.all()"""
    app_content = att_rec_pattern.sub(new_att_rec, app_content)

    # 6. Update reports
    reports_pattern = re.compile(
        rf"    students = Student\.query\.filter_by\(organization_id=session\.get\('org_id'\)\)\.all\(\)\n"
        rf"    classes = Class_\.query\.filter_by\(organization_id=session\.get\('org_id'\)\)\.all\(\)\n"
        rf"    return render_template\('{org}/reports\.html', students=students, classes=classes\)"
    )
    new_reports = f"""    course_id = request.args.get('course_id')
    year = request.args.get('year')
    cls_query = Class_.query.filter_by(organization_id=session.get('org_id'))
    if course_id: cls_query = cls_query.filter_by(course_id=course_id)
    if year: cls_query = cls_query.filter_by(academic_year=year)
    classes = cls_query.all()
    class_ids = [c.id for c in classes]
    if class_ids:
        students = Student.query.filter(Student.class_id.in_(class_ids)).all()
    else:
        students = []
    return render_template('{org}/reports.html', students=students, classes=classes)"""
    app_content = reports_pattern.sub(new_reports, app_content)

with open(app_py_path, 'w', encoding='utf-8') as f:
    f.write(app_content)

print("Updated app.py with correct cascading filters for College/Institution flow.")
