import os
import re

app_py_path = 'app.py'
with open(app_py_path, 'r', encoding='utf-8') as f:
    app_content = f.read()

for org in ['college', 'institution']:
    # 1. Add add_subject route
    if f"def {org}_add_subject():" not in app_content:
        add_subject_code = f"""
@app.route('/{org}/add-subject', methods=['GET', 'POST'])
@org_required(['{org}'])
def {org}_add_subject():
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    if request.method == 'POST':
        name = request.form.get('subject_name')
        if not name or not course_id:
            flash('Subject name and course are required', 'danger')
            return redirect(url_for('{org}_add_subject', course_id=course_id, year=year))
        subject = Subject(name=name, course_id=int(course_id), study_year=year, organization_id=session.get('org_id'))
        db.session.add(subject)
        db.session.commit()
        flash('Subject added successfully!', 'success')
        return redirect(url_for('{org}_dashboard', course_id=course_id, year=year))
    return render_template('{org}/add_subject.html', course_id=course_id, year=year)
"""
        classes_idx = app_content.find(f"@app.route('/{org}/classes')")
        if classes_idx != -1:
            app_content = app_content[:classes_idx] + add_subject_code + app_content[classes_idx:]

    # 2. Update mark_attendance route to fetch subjects
    mark_att_pattern = re.compile(
        rf"@app\.route\('/{org}/mark-attendance', methods=\['GET', 'POST'\]\)\n"
        rf"@org_required\(\['{org}'\]\)\n"
        rf"def {org}_mark_attendance\(\):\n"
        rf"    course_id = request\.args\.get\('course_id'\)\n"
        rf"    year = request\.args\.get\('year'\)\n"
        rf"    \n"
        rf"    query = Class_\.query\.filter_by\(organization_id=session\.get\('org_id'\)\)\n"
        rf"    if course_id: query = query\.filter_by\(course_id=course_id\)\n"
        rf"    if year: query = query\.filter_by\(study_year=year\)\n"
        rf"    classes = query\.all\(\)\n"
        rf"(.*?)"
        rf"    return render_template\('{org}/mark_attendance\.html', classes=classes\)",
        re.DOTALL
    )
    
    new_mark_att = f"""@app.route('/{org}/mark-attendance', methods=['GET', 'POST'])
@org_required(['{org}'])
def {org}_mark_attendance():
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
\\1
    return render_template('{org}/mark_attendance.html', classes=classes, subjects=subjects, course_id=course_id, year=year)"""
    
    app_content = mark_att_pattern.sub(new_mark_att, app_content)

    # 3. Update attendance-records to fetch subjects
    att_rec_pattern = re.compile(
        rf"@app\.route\('/{org}/attendance-records'\)\n"
        rf"@org_required\(\['{org}'\]\)\n"
        rf"def {org}_attendance_records\(\):\n"
        rf"(.*?)"
        rf"    return render_template\('{org}/attendance_records\.html', records=records, classes=classes, selected_class=class_id, selected_date=date_str\)",
        re.DOTALL
    )
    
    new_att_rec = f"""@app.route('/{org}/attendance-records')
@org_required(['{org}'])
def {org}_attendance_records():
\\1
    subj_query = Subject.query.filter_by(organization_id=session.get('org_id'))
    if course_id: subj_query = subj_query.filter_by(course_id=course_id)
    if year: subj_query = subj_query.filter_by(study_year=year)
    subjects = subj_query.all()
    
    return render_template('{org}/attendance_records.html', records=records, classes=classes, subjects=subjects, selected_class=class_id, selected_date=date_str, course_id=course_id, year=year)"""
    # Wait, the above regex might fail if \\1 captures too much. I'll patch it more precisely.

with open(app_py_path, 'w', encoding='utf-8') as f:
    f.write(app_content)
print("Updated app.py routes for subjects.")

# Now for templates
for org in ['college', 'institution']:
    base_dir = f'templates/{org}'
    
    # Create add_subject.html
    add_subj = f"""{{% extends "base.html" %}}
{{% block title %}}Add Subject - Smart Attendance{{% endblock %}}
{{% block navbar_title %}}Add Subject{{% endblock %}}
{{% block content %}}
<div class="page-title">Add New Subject</div>
<div class="card">
    <div class="card-body">
        <form method="POST">
            <div class="mb-3">
                <label>Subject Name</label>
                <input type="text" name="subject_name" class="form-control" required>
            </div>
            <button type="submit" class="btn btn-primary">Add Subject</button>
            <a href="/{org}/dashboard?course_id={{{{ course_id }}}}&year={{{{ year }}}}" class="btn btn-secondary">Cancel</a>
        </form>
    </div>
</div>
{{% endblock %}}
"""
    with open(f"{base_dir}/add_subject.html", 'w', encoding='utf-8') as f:
        f.write(add_subj)

    # Modify dashboard to add a link for Add Subject
    f_path = f"{base_dir}/dashboard.html"
    if os.path.exists(f_path):
        with open(f_path, 'r', encoding='utf-8') as f:
            c = f.read()
        if "Add New Subject" not in c:
            # Put it in the "Class Management" box
            c = c.replace('Add New Class</a>', 'Add New Class</a>\n                <a href="/college/add-subject?course_id={{ course_id }}&year={{ year }}" class="btn btn-secondary ms-2 mt-2">Add New Subject</a>')
            c = c.replace('/college/add-subject', f'/{org}/add-subject')
        with open(f_path, 'w', encoding='utf-8') as f:
            f.write(c)
            
    # Modify mark_attendance.html
    f_path = f"{base_dir}/mark_attendance.html"
    if os.path.exists(f_path):
        with open(f_path, 'r', encoding='utf-8') as f:
            c = f.read()
        if "name=\"subject_id\"" not in c:
            # We must inject a subject dropdown right after class dropdown
            sel_class = """<div class="mb-3">
                        <label class="form-label">Select Class *</label>
                        <select name="class_id" class="form-select" required>
                            <option value="">-- Select Class --</option>
                            {% for class in classes %}
                            <option value="{{ class.id }}">{{ class.name }}</option>
                            {% endfor %}
                        </select>
                    </div>"""
            sel_subj = """<div class="mb-3">
                        <label class="form-label">Select Subject *</label>
                        <select name="subject_id" class="form-select" required>
                            <option value="">-- Select Subject --</option>
                            {% for subject in subjects %}
                            <option value="{{ subject.id }}">{{ subject.name }}</option>
                            {% endfor %}
                        </select>
                    </div>"""
            if sel_class in c:
                c = c.replace(sel_class, sel_class + "\n" + sel_subj)
            else:
                # Approximate replacement
                c = c.replace('name="class_id"', 'name="class_id"') # ensure we find it
                c = re.sub(r'(<select name="class_id".*?</select>\s*</div>)', r'\1\n' + sel_subj, c, flags=re.DOTALL)
            
            with open(f_path, 'w', encoding='utf-8') as f:
                f.write(c)

print("Updated templates for subjects.")
