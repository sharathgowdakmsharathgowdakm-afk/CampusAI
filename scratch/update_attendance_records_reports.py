import os
import re

app_py_path = 'app.py'
with open(app_py_path, 'r', encoding='utf-8') as f:
    app_content = f.read()

for org in ['college', 'institution']:
    # Update reports PDF to show subject
    # In reports, we iterate over attendances
    # `data = [['Date', 'Time', 'Student', 'Roll No', 'Status']]`
    # -> `data = [['Date', 'Time', 'Student', 'Roll No', 'Subject', 'Status']]`
    
    # For class-wise report
    pattern_class_report = re.compile(
        rf"(if report_type == 'class':.*?data = \[\['Date', 'Time', 'Student', 'Roll No')(', 'Status'\]\])",
        re.DOTALL
    )
    app_content = pattern_class_report.sub(r"\1, 'Subject'\2", app_content)
    
    pattern_class_append = re.compile(
        rf"(data\.append\(\[str\(att\.date\), str\(att\.time\), att\.student\.name, att\.student\.roll_number)(, att\.status\]\))"
    )
    app_content = pattern_class_append.sub(r"\1, att.subject.name if att.subject else '-'\2", app_content)
    
    # For student-wise report
    pattern_student_report = re.compile(
        rf"(else:.*?data = \[\['Date', 'Time')(', 'Status'\]\])",
        re.DOTALL
    )
    app_content = pattern_student_report.sub(r"\1, 'Subject'\2", app_content)
    
    pattern_student_append = re.compile(
        rf"(data\.append\(\[str\(att\.date\), str\(att\.time\))(', att\.status\]\))"
    )
    app_content = pattern_student_append.sub(r"\1, att.subject.name if att.subject else '-'\2", app_content)

with open(app_py_path, 'w', encoding='utf-8') as f:
    f.write(app_content)
print("Updated app.py PDF report headers to include Subject.")

for org in ['college', 'institution']:
    base_dir = f'templates/{org}'
    
    # 1. Update attendance_records.html
    f_path = f"{base_dir}/attendance_records.html"
    if os.path.exists(f_path):
        with open(f_path, 'r', encoding='utf-8') as f:
            c = f.read()
        
        # Add a Subject column in the table header
        if "<th>Time</th>" in c and "<th>Subject</th>" not in c:
            c = c.replace('<th>Time</th>', '<th>Time</th>\n                                    <th>Subject</th>')
        
        # Add Subject data
        if "<td>{{ record.time }}</td>" in c and "record.subject.name" not in c:
            c = c.replace(
                '<td>{{ record.time }}</td>',
                '<td>{{ record.time }}</td>\n                                    <td>{{ record.subject.name if record.subject else "-" }}</td>'
            )
            
        with open(f_path, 'w', encoding='utf-8') as f:
            f.write(c)

print("Updated attendance_records.html to display Subject column.")
