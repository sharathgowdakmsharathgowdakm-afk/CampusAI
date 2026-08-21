import os

orgs = ['college', 'institution']

for org in orgs:
    base_dir = f'templates/{org}'
    
    # 1. Update select_year.html
    f_path = f"{base_dir}/select_year.html"
    if os.path.exists(f_path):
        content = f"""{{% extends "base.html" %}}
{{% block title %}}{org.capitalize()} Dashboard - Select Year{{% endblock %}}
{{% block navbar_title %}}{org.capitalize()} Dashboard{{% endblock %}}
{{% block content %}}
<div class="page-title">Welcome to {org.capitalize()} Dashboard</div>
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header"><i class="fas fa-calendar"></i> Select Study Year for {{{{ course.name }}}}</div>
            <div class="card-body">
                <form action="/{org}/dashboard" method="GET">
                    <input type="hidden" name="course_id" value="{{{{ course.id }}}}">
                    <div class="mb-3">
                        <label class="form-label">Study Year</label>
                        <select name="year" class="form-select" required>
                            <option value="">-- Select Year --</option>
                            {{% for y in years %}}
                            <option value="{{{{ y }}}}">{{{{ y }}}}</option>
                            {{% endfor %}}
                        </select>
                    </div>
                    <button type="submit" class="btn btn-primary"><i class="fas fa-arrow-right"></i> Next</button>
                    <a href="/{org}/add-year?course_id={{{{ course.id }}}}" class="btn btn-success ms-2"><i class="fas fa-plus"></i> Add Year</a>
                </form>
            </div>
        </div>
    </div>
</div>
{{% endblock %}}
"""
        with open(f_path, 'w', encoding='utf-8') as f:
            f.write(content)

    # 2. Create add_year.html
    add_year_path = f"{base_dir}/add_year.html"
    add_year_content = f"""{{% extends "base.html" %}}
{{% block title %}}Add Year - Smart Attendance{{% endblock %}}
{{% block navbar_title %}}Add New Year{{% endblock %}}
{{% block content %}}
<div class="page-title">Add New Study Year</div>
<div class="row">
    <div class="col-md-8">
        <div class="card">
            <div class="card-header">
                <i class="fas fa-plus"></i> Create Study Year
            </div>
            <div class="card-body">
                <form method="POST">
                    <div class="mb-3">
                        <label class="form-label">Study Year Name *</label>
                        <input type="text" name="year_name" class="form-control" placeholder="e.g., First PUC, 2nd Year" required>
                    </div>
                    <button type="submit" class="btn btn-primary">
                        <i class="fas fa-save"></i> Create Year
                    </button>
                    <a href="/{org}/dashboard?course_id={{{{ course_id }}}}" class="btn btn-secondary ms-2">Cancel</a>
                </form>
            </div>
        </div>
    </div>
</div>
{{% endblock %}}
"""
    with open(add_year_path, 'w', encoding='utf-8') as f:
        f.write(add_year_content)

print("Updated templates for add-year flow.")

import re

app_py_path = 'app.py'
with open(app_py_path, 'r', encoding='utf-8') as f:
    app_content = f.read()

for org in orgs:
    if f"def {org}_add_year():" not in app_content:
        add_year_code = f"""
@app.route('/{org}/add-year', methods=['GET', 'POST'])
@org_required(['{org}'])
def {org}_add_year():
    course_id = request.args.get('course_id')
    if request.method == 'POST':
        year_name = request.form.get('year_name')
        if not year_name:
            flash('Year name is required', 'danger')
            return redirect(url_for('{org}_add_year', course_id=course_id))
        return redirect(url_for('{org}_dashboard', course_id=course_id, year=year_name))
    return render_template('{org}/add_year.html', course_id=course_id)
"""
        # Inject before `{org}_add_course`
        idx = app_content.find(f"@app.route('/{org}/add-course'")
        if idx != -1:
            app_content = app_content[:idx] + add_year_code + app_content[idx:]

with open(app_py_path, 'w', encoding='utf-8') as f:
    f.write(app_content)

print("Updated app.py with add-year routes.")
