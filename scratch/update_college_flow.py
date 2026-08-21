import os
import re

app_py_path = 'app.py'
with open(app_py_path, 'r', encoding='utf-8') as f:
    app_content = f.read()

orgs = ['college', 'institution']

for org in orgs:
    # 1. Update dashboard
    dashboard_pattern = re.compile(
        rf"@app\.route\('/{org}/dashboard'\)\n"
        rf"@org_required\(\['{org}'\]\)\n"
        rf"def {org}_dashboard\(\):\n"
        rf"(.*?)"
        rf"    return render_template\('{org}/dashboard\.html',.*?\)",
        re.DOTALL
    )
    
    new_dashboard = f"""@app.route('/{org}/dashboard')
@org_required(['{org}'])
def {org}_dashboard():
    org_id = session.get('org_id')
    courses = Course.query.filter_by(organization_id=org_id).all()
    
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    
    if not course_id:
        return render_template('{org}/select_course.html', courses=courses)
        
    course = Course.query.get(int(course_id))
    
    if not year:
        classes = Class_.query.filter_by(organization_id=org_id, course_id=course_id).all()
        years = sorted(list(set([c.academic_year for c in classes])))
        return render_template('{org}/select_year.html', course=course, years=years)
        
    classes = Class_.query.filter_by(organization_id=org_id, course_id=course_id, academic_year=year).all()
    total_classes = len(classes)
    class_ids = [c.id for c in classes]
    total_students = Student.query.filter(Student.class_id.in_(class_ids)).count() if class_ids else 0
    today_attendance = Attendance.query.filter_by(date=datetime.now().date()).filter(Attendance.class_id.in_(class_ids)).count() if class_ids else 0
    
    return render_template('{org}/dashboard.html',
                           total_classes=total_classes,
                           total_students=total_students,
                           today_attendance=today_attendance,
                           course=course,
                           year=year,
                           course_id=course_id)"""

    app_content = dashboard_pattern.sub(new_dashboard, app_content)

    # 2. Add course route if not exists
    if f"def {org}_add_course():" not in app_content:
        add_course_code = f"""

@app.route('/{org}/add-course', methods=['GET', 'POST'])
@org_required(['{org}'])
def {org}_add_course():
    if request.method == 'POST':
        name = request.form.get('course_name')
        if not name:
            flash('Course name is required', 'danger')
            return redirect(url_for('{org}_add_course'))
        course = Course(name=name, organization_id=session.get('org_id'))
        db.session.add(course)
        db.session.commit()
        flash('Course added successfully!', 'success')
        return redirect(url_for('{org}_dashboard'))
    return render_template('{org}/add_course.html')
"""
        # Append before {org}_classes
        classes_route_idx = app_content.find(f"@app.route('/{org}/classes')")
        if classes_route_idx != -1:
            app_content = app_content[:classes_route_idx] + add_course_code + app_content[classes_route_idx:]

    # 3. Update classes
    classes_pattern = re.compile(
        rf"@app\.route\('/{org}/classes'\)\n"
        rf"@org_required\(\['{org}'\]\)\n"
        rf"def {org}_classes\(\):\n"
        rf"(.*?)"
        rf"    return render_template\('{org}/classes\.html', classes=classes\)",
        re.DOTALL
    )
    
    new_classes = f"""@app.route('/{org}/classes')
@org_required(['{org}'])
def {org}_classes():
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    query = Class_.query.filter_by(organization_id=session.get('org_id'))
    if course_id:
        query = query.filter_by(course_id=course_id)
    if year:
        query = query.filter_by(academic_year=year)
    classes = query.all()
    for c in classes:
        c.student_count = len(c.students)
    return render_template('{org}/classes.html', classes=classes, course_id=course_id, year=year)"""
    
    app_content = classes_pattern.sub(new_classes, app_content)

    # 4. Update add-class
    add_class_pattern = re.compile(
        rf"@app\.route\('/{org}/add-class', methods=\['GET', 'POST'\]\)\n"
        rf"@org_required\(\['{org}'\]\)\n"
        rf"def {org}_add_class\(\):.*?"
        rf"    return render_template\('{org}/add_class\.html'\)",
        re.DOTALL
    )
    
    new_add_class = f"""@app.route('/{org}/add-class', methods=['GET', 'POST'])
@org_required(['{org}'])
def {org}_add_class():
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    courses = Course.query.filter_by(organization_id=session.get('org_id')).all()
    
    if request.method == 'POST':
        class_name = request.form.get('class_name')
        course_id_post = request.form.get('course_id')
        academic_year = request.form.get('academic_year')
        
        if not all([class_name, academic_year, course_id_post]):
            flash('All fields are required', 'danger')
            return redirect(url_for('{org}_add_class', course_id=course_id, year=year))
            
        class_ = Class_(name=class_name, academic_year=academic_year,
                        organization_id=session.get('org_id'), course_id=int(course_id_post))
        db.session.add(class_)
        db.session.commit()
        flash('Class added successfully!', 'success')
        return redirect(url_for('{org}_dashboard', course_id=course_id_post, year=academic_year))
        
    return render_template('{org}/add_class.html', courses=courses, selected_course=course_id, selected_year=year)"""
    
    app_content = add_class_pattern.sub(new_add_class, app_content)

with open(app_py_path, 'w', encoding='utf-8') as f:
    f.write(app_content)
print("Updated app.py with College/Institution flow successfully!")
