import os

orgs = ['college', 'institution']

for org in orgs:
    base_dir = f'templates/{org}'
    os.makedirs(base_dir, exist_ok=True)
    
    # 1. Create select_course.html
    select_course_html = f"""{{% extends "base.html" %}}
{{% block title %}}{org.capitalize()} Dashboard - Select Course{{% endblock %}}
{{% block navbar_title %}}{org.capitalize()} Dashboard{{% endblock %}}
{{% block content %}}
<div class="page-title">Welcome to {org.capitalize()} Dashboard</div>
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header"><i class="fas fa-book"></i> Select a Course</div>
            <div class="card-body">
                <form action="/{org}/dashboard" method="GET">
                    <div class="mb-3">
                        <label class="form-label">Course</label>
                        <select name="course_id" class="form-select" required>
                            <option value="">-- Select Course --</option>
                            {{% for course in courses %}}
                            <option value="{{{{ course.id }}}}">{{{{ course.name }}}}</option>
                            {{% endfor %}}
                        </select>
                    </div>
                    <button type="submit" class="btn btn-primary"><i class="fas fa-arrow-right"></i> Next</button>
                    <a href="/{org}/add-course" class="btn btn-success ms-2"><i class="fas fa-plus"></i> Add Course</a>
                </form>
            </div>
        </div>
    </div>
</div>
{{% endblock %}}
"""
    with open(f"{base_dir}/select_course.html", "w", encoding="utf-8") as f:
        f.write(select_course_html)

    # 2. Create select_year.html
    select_year_html = f"""{{% extends "base.html" %}}
{{% block title %}}{org.capitalize()} Dashboard - Select Year{{% endblock %}}
{{% block navbar_title %}}{org.capitalize()} Dashboard{{% endblock %}}
{{% block content %}}
<div class="page-title">Welcome to {org.capitalize()} Dashboard</div>
<div class="row justify-content-center">
    <div class="col-md-6">
        <div class="card">
            <div class="card-header"><i class="fas fa-calendar"></i> Select Academic Year for {{{{ course.name }}}}</div>
            <div class="card-body">
                <form action="/{org}/dashboard" method="GET">
                    <input type="hidden" name="course_id" value="{{{{ course.id }}}}">
                    <div class="mb-3">
                        <label class="form-label">Academic Year</label>
                        <select name="year" class="form-select" required>
                            <option value="">-- Select Year --</option>
                            {{% for y in years %}}
                            <option value="{{{{ y }}}}">{{{{ y }}}}</option>
                            {{% endfor %}}
                        </select>
                    </div>
                    <button type="submit" class="btn btn-primary"><i class="fas fa-arrow-right"></i> Go to Dashboard</button>
                    <a href="/{org}/add-class?course_id={{{{ course.id }}}}" class="btn btn-success ms-2"><i class="fas fa-plus"></i> Add New Class & Year</a>
                </form>
            </div>
        </div>
    </div>
</div>
{{% endblock %}}
"""
    with open(f"{base_dir}/select_year.html", "w", encoding="utf-8") as f:
        f.write(select_year_html)

    # 3. Update add_class.html
    add_class_path = f"{base_dir}/add_class.html"
    if os.path.exists(add_class_path):
        with open(add_class_path, "r", encoding="utf-8") as f:
            add_class_content = f.read()
        
        # Replace the form fields
        new_form = f"""
                    <div class="mb-3">
                        <label class="form-label">Course *</label>
                        <select name="course_id" class="form-select" required>
                            <option value="">-- Select Course --</option>
                            {{% for course in courses %}}
                            <option value="{{{{ course.id }}}}" {{% if selected_course == course.id|string %}}selected{{% endif %}}>{{{{ course.name }}}}</option>
                            {{% endfor %}}
                        </select>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Class Name *</label>
                        <input type="text" name="class_name" class="form-control" placeholder="e.g., Section A" required>
                    </div>
                    <div class="mb-3">
                        <label class="form-label">Academic Year *</label>
                        <input type="text" name="academic_year" class="form-control" placeholder="e.g., 2023-2024" value="{{{{ selected_year or '' }}}}" required>
                    </div>
"""
        # A simple replacement of the inputs
        if "name=\"class_name\"" in add_class_content and "name=\"course_id\"" not in add_class_content:
            start_idx = add_class_content.find('<div class="mb-3">')
            end_idx = add_class_content.find('<button type="submit"')
            if start_idx != -1 and end_idx != -1:
                add_class_content = add_class_content[:start_idx] + new_form + add_class_content[end_idx:]
                with open(add_class_path, "w", encoding="utf-8") as f:
                    f.write(add_class_content)

    # 4. Update dashboard.html to include params in links
    dashboard_path = f"{base_dir}/dashboard.html"
    if os.path.exists(dashboard_path):
        with open(dashboard_path, "r", encoding="utf-8") as f:
            dash_content = f.read()
        
        # We need to append ?course_id={{ course_id }}&year={{ year }} to all links like href="/{org}/..."
        import re
        def replace_link(match):
            href = match.group(1)
            if '?' in href:
                return f'href="{href}&course_id={{{{ course_id }}}}&year={{{{ year }}}}"'
            else:
                return f'href="{href}?course_id={{{{ course_id }}}}&year={{{{ year }}}}"'
                
        dash_content = re.sub(rf'href="(\/{org}\/[a-zA-Z0-9_-]+)"', replace_link, dash_content)
        
        # Add a back button to change course/year
        if "Change Course/Year" not in dash_content:
            header = f"""<div class="page-title">
    Welcome to {org.capitalize()} Dashboard 
    <span style="font-size: 1rem; margin-left: 20px;">
        <span class="badge bg-secondary">{{{{ course.name }}}} | {{{{ year }}}}</span>
        <a href="/{org}/dashboard" class="btn btn-sm btn-outline-primary ms-2"><i class="fas fa-edit"></i> Change Course/Year</a>
    </span>
</div>"""
            dash_content = re.sub(r'<div class="page-title">.*?</div>', header, dash_content, flags=re.DOTALL)
            
        with open(dashboard_path, "w", encoding="utf-8") as f:
            f.write(dash_content)

    # 5. Update classes.html to preserve params
    classes_path = f"{base_dir}/classes.html"
    if os.path.exists(classes_path):
        with open(classes_path, "r", encoding="utf-8") as f:
            cls_content = f.read()
        
        def replace_classes_link(match):
            href = match.group(1)
            if 'add-class' in href:
                return f'href="/{org}/add-class?course_id={{{{ course_id }}}}&year={{{{ year }}}}"'
            return match.group(0)
            
        cls_content = re.sub(rf'href="(\/{org}\/add-class)"', replace_classes_link, cls_content)
        
        with open(classes_path, "w", encoding="utf-8") as f:
            f.write(cls_content)

print("Updated HTML templates for College/Institution flow successfully!")
