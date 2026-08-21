import os
import re

app_py_path = 'app.py'
with open(app_py_path, 'r', encoding='utf-8') as f:
    app_content = f.read()

for org in ['college', 'institution']:
    # Update dashboard logic to also pull years from Subject table
    pattern = re.compile(
        rf"classes = Class_\.query\.filter_by\(organization_id=org_id, course_id=course_id\)\.all\(\)\n"
        rf"        years = sorted\(list\(set\(\[c\.study_year for c in classes if c\.study_year\]\)\)\)"
    )
    replacement = f"""classes = Class_.query.filter_by(organization_id=org_id, course_id=course_id).all()
        subjects = Subject.query.filter_by(organization_id=org_id, course_id=course_id).all()
        class_years = [c.study_year for c in classes if c.study_year]
        subj_years = [s.study_year for s in subjects if s.study_year]
        years = sorted(list(set(class_years + subj_years)))"""
    app_content = pattern.sub(replacement, app_content)

with open(app_py_path, 'w', encoding='utf-8') as f:
    f.write(app_content)
print("Updated app.py dashboard logic for years.")

# Update select_year.html for both
for org in ['college', 'institution']:
    base_dir = f'templates/{org}'
    f_path = f"{base_dir}/select_year.html"
    if os.path.exists(f_path):
        with open(f_path, 'r', encoding='utf-8') as f:
            c = f.read()
        
        # Add the explicit 'Add Year' inline form
        if "Or Start a New Year" not in c:
            new_form = f"""
                    <hr class="my-4">
                    <h6 class="text-muted mb-3">Or Start a New Year:</h6>
                    <form action="/{org}/dashboard" method="GET" class="d-flex align-items-center">
                        <input type="hidden" name="course_id" value="{{{{ course.id }}}}">
                        <input type="text" name="year" class="form-control me-2" placeholder="e.g. First PUC" required>
                        <button type="submit" class="btn btn-success text-nowrap"><i class="fas fa-plus"></i> Add Year</button>
                    </form>
"""
            # Inject before the closing card-body
            c = c.replace('            </div>\n        </div>\n    </div>\n</div>', new_form + '            </div>\n        </div>\n    </div>\n</div>')
            
            # Remove the "Add New Class & Year" button from the first form since it's redundant now
            c = c.replace(f'<a href="/{org}/add-class?course_id={{{{ course.id }}}}" class="btn btn-success ms-2"><i class="fas fa-plus"></i> Add New Class & Year</a>', '')

            with open(f_path, 'w', encoding='utf-8') as f:
                f.write(c)

print("Updated select_year.html to include Add Year forms.")
