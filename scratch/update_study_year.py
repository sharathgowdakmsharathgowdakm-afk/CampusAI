import re

app_py_path = 'app.py'
with open(app_py_path, 'r', encoding='utf-8') as f:
    app_content = f.read()

# Replace Class_.academic_year == year with Class_.study_year == year
app_content = re.sub(r'Class_\.academic_year == year', r'Class_.study_year == year', app_content)
app_content = re.sub(r'academic_year=year\)', r'study_year=year)', app_content)

# Update college_add_class and institution_add_class
def update_add_class(org):
    global app_content
    pattern = re.compile(
        rf"academic_year = request\.form\.get\('academic_year'\)(.*?)"
        rf"class_ = Class_\(name=class_name, academic_year=academic_year,",
        re.DOTALL
    )
    replacement = r"study_year = request.form.get('study_year')\1class_ = Class_(name=class_name, academic_year='2023-2024', study_year=study_year,"
    
    # Also change 'academic_year' in `if not all([..., academic_year, ...])`
    app_content = pattern.sub(replacement, app_content)
    # Fix the `not all` list
    pattern2 = re.compile(rf"if not all\(\[class_name, academic_year, course_id_post\]\):")
    replacement2 = r"if not all([class_name, study_year, course_id_post]):"
    app_content = pattern2.sub(replacement2, app_content)

    # In dashboard: `years = sorted(list(set([c.academic_year for c in classes])))`
    pattern3 = re.compile(rf"years = sorted\(list\(set\(\[c\.academic_year for c in classes\]\)\)\)")
    replacement3 = r"years = sorted(list(set([c.study_year for c in classes if c.study_year])))"
    app_content = pattern3.sub(replacement3, app_content)

update_add_class('college')
update_add_class('institution')

with open(app_py_path, 'w', encoding='utf-8') as f:
    f.write(app_content)
print("Updated app.py for study_year.")

# Update templates
import os
for org in ['college', 'institution']:
    base_dir = f'templates/{org}'
    
    # Update select_year.html
    f_path = f"{base_dir}/select_year.html"
    if os.path.exists(f_path):
        with open(f_path, 'r', encoding='utf-8') as f:
            c = f.read()
        c = c.replace('Academic Year', 'Study Year (e.g. First PUC)')
        with open(f_path, 'w', encoding='utf-8') as f:
            f.write(c)
            
    # Update add_class.html
    f_path = f"{base_dir}/add_class.html"
    if os.path.exists(f_path):
        with open(f_path, 'r', encoding='utf-8') as f:
            c = f.read()
        c = c.replace('name="academic_year"', 'name="study_year"')
        c = c.replace('Academic Year', 'Study Year')
        c = c.replace('e.g., 2023-2024', 'e.g., First PUC')
        with open(f_path, 'w', encoding='utf-8') as f:
            f.write(c)

print("Updated templates for study_year.")
