import re

app_py_path = 'app.py'
with open(app_py_path, 'r', encoding='utf-8') as f:
    app_content = f.read()

orgs = ['college', 'institution']

for org in orgs:
    # Fix dashboard
    pattern = re.compile(
        rf"@app\.route\('/{org}/dashboard'\)\n"
        rf"@org_required\(\['{org}'\]\)\n"
        rf"def {org}_dashboard\(\):\n"
        rf"(.*?)"
        rf"    if not course_id:\n"
        rf"        return render_template\('{org}/select_course\.html', courses=courses\)\n\s*"
        rf"    course = Course\.query\.get\(int\(course_id\)\)",
        re.DOTALL
    )
    
    replacement = f"""@app.route('/{org}/dashboard')
@org_required(['{org}'])
def {org}_dashboard():
    org_id = session.get('org_id')
    courses = Course.query.filter_by(organization_id=org_id).all()
    
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    
    if not course_id or course_id == 'None':
        return render_template('{org}/select_course.html', courses=courses)
        
    try:
        course = Course.query.get(int(course_id))
    except (ValueError, TypeError):
        flash("Invalid course selection.", "danger")
        return redirect(url_for('{org}_dashboard'))
        
    if not course:
        flash("Course not found.", "danger")
        return redirect(url_for('{org}_dashboard'))"""

    app_content = pattern.sub(replacement, app_content)

    # Fix add_class
    add_class_pattern = re.compile(
        rf"@app\.route\('/{org}/add-class', methods=\['GET', 'POST'\]\)\n"
        rf"@org_required\(\['{org}'\]\)\n"
        rf"def {org}_add_class\(\):\n"
        rf"    course_id = request\.args\.get\('course_id'\)\n"
        rf"    year = request\.args\.get\('year'\)"
    )
    
    new_add_class = f"""@app.route('/{org}/add-class', methods=['GET', 'POST'])
@org_required(['{org}'])
def {org}_add_class():
    course_id = request.args.get('course_id')
    year = request.args.get('year')
    if course_id == 'None': course_id = None
    if year == 'None': year = None"""
    app_content = add_class_pattern.sub(new_add_class, app_content)

with open(app_py_path, 'w', encoding='utf-8') as f:
    f.write(app_content)
print("Added safeguards against invalid course_id.")
