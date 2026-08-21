import re

app_py_path = 'app.py'
with open(app_py_path, 'r', encoding='utf-8') as f:
    app_content = f.read()

for org in ['college', 'institution']:
    # Fix mark_attendance POST
    pattern = re.compile(
        rf"@app\.route\('/{org}/mark-attendance', methods=\['GET', 'POST'\]\)\n"
        rf"@org_required\(\['{org}'\]\)\n"
        rf"def {org}_mark_attendance\(\):(.*?)"
        rf"        class_id = request\.form\.get\('class_id', ''\)\n"
        rf"        if not class_id:\n"
        rf"            return jsonify\(\{{'error': 'Class not selected'\}}\), 400\n"
        rf"(.*?)existing = Attendance\.query\.filter_by\(\s*"
        rf"student_id=student\.id, date=datetime\.now\(\)\.date\(\)\)\.first\(\)\s*"
        rf"if not existing:\s*"
        rf"attendance = Attendance\(\s*"
        rf"student_id=student\.id, class_id=int\(class_id\),\s*"
        rf"date=datetime\.now\(\)\.date\(\), time=datetime\.now\(\)\.time\(\),\s*"
        rf"status='present'\)",
        re.DOTALL
    )
    
    replacement = f"""@app.route('/{org}/mark-attendance', methods=['GET', 'POST'])
@org_required(['{org}'])
def {org}_mark_attendance():\\1        class_id = request.form.get('class_id', '')
        subject_id = request.form.get('subject_id', '')
        if not class_id:
            return jsonify({{'error': 'Class not selected'}}), 400
        if not subject_id:
            return jsonify({{'error': 'Subject not selected'}}), 400
\\2existing = Attendance.query.filter_by(
                                    student_id=student.id, date=datetime.now().date(), subject_id=int(subject_id)).first()
                                if not existing:
                                    attendance = Attendance(
                                        student_id=student.id, class_id=int(class_id), subject_id=int(subject_id),
                                        date=datetime.now().date(), time=datetime.now().time(),
                                        status='present')"""
    
    app_content = pattern.sub(replacement, app_content)

with open(app_py_path, 'w', encoding='utf-8') as f:
    f.write(app_content)
print("Updated mark attendance subject logic.")

# Modify mark_attendance.html to add `subject_id` to formData if they use AJAX
import os
for org in ['college', 'institution']:
    f_path = f"templates/{org}/mark_attendance.html"
    if os.path.exists(f_path):
        with open(f_path, 'r', encoding='utf-8') as f:
            c = f.read()
        
        # Look for JavaScript that submits class_id and add subject_id
        if "formData.append('class_id'" in c and "formData.append('subject_id'" not in c:
            c = c.replace(
                "formData.append('class_id', document.querySelector('select[name=\"class_id\"]').value);",
                "formData.append('class_id', document.querySelector('select[name=\"class_id\"]').value);\n            formData.append('subject_id', document.querySelector('select[name=\"subject_id\"]').value);"
            )
        
        with open(f_path, 'w', encoding='utf-8') as f:
            f.write(c)
print("Updated mark attendance template JS.")
