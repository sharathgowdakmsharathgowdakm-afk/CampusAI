import os
import re

app_py_path = 'app.py'
with open(app_py_path, 'r', encoding='utf-8') as f:
    app_content = f.read()

orgs = ['school', 'college', 'institution']

def get_report_replacement(org):
    return f"""@app.route('/{org}/reports', methods=['GET', 'POST'])
@org_required(['{org}'])
def {org}_reports():
    if request.method == 'POST':
        report_type = request.form.get('report_type', 'student')
        student_id = request.form.get('student_id')
        class_id = request.form.get('class_id')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        title_style = ParagraphStyle('CustomTitle', parent=getSampleStyleSheet()['Heading1'],
                                     fontSize=16, spaceAfter=30)
        
        if report_type == 'class':
            elements.append(Paragraph("Class Attendance Report", title_style))
            if class_id:
                class_ = Class_.query.get(int(class_id))
                elements.append(Paragraph(f"Class: {{class_.name}}", getSampleStyleSheet()['Normal']))
                if start_date and end_date:
                    elements.append(Paragraph(f"Period: {{start_date}} to {{end_date}}", getSampleStyleSheet()['Normal']))
                elements.append(Spacer(1, 0.2*inch))
                
                data = [['Date', 'Time', 'Student', 'Roll No', 'Status']]
                attendances = Attendance.query.filter_by(class_id=int(class_id))
                if start_date and end_date:
                    attendances = attendances.filter(Attendance.date.between(start_date, end_date))
                
                attendances = attendances.join(Student).order_by(Attendance.date.desc(), Student.name).all()
                for att in attendances:
                    data.append([str(att.date), str(att.time), att.student.name, att.student.roll_number, att.status])
        else:
            elements.append(Paragraph("Student Attendance Report", title_style))
            if student_id:
                student = Student.query.get(int(student_id))
                elements.append(Paragraph(f"Student: {{student.name}}", getSampleStyleSheet()['Normal']))
                elements.append(Paragraph(f"Roll Number: {{student.roll_number}}", getSampleStyleSheet()['Normal']))
                if start_date and end_date:
                    elements.append(Paragraph(f"Period: {{start_date}} to {{end_date}}", getSampleStyleSheet()['Normal']))
                elements.append(Spacer(1, 0.2*inch))
                
                data = [['Date', 'Time', 'Status']]
                attendances = Attendance.query.filter_by(student_id=int(student_id))
                if start_date and end_date:
                    attendances = attendances.filter(Attendance.date.between(start_date, end_date))
                for att in attendances.order_by(Attendance.date.desc()).all():
                    data.append([str(att.date), str(att.time), att.status])

        if len(data) > 1:
            table = Table(data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.grey),
                ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,0), 10 if report_type == 'class' else 12),
                ('BOTTOMPADDING', (0,0), (-1,0), 12),
                ('BACKGROUND', (0,1), (-1,-1), colors.beige),
                ('GRID', (0,0), (-1,-1), 1, colors.black)
            ]))
            elements.append(table)
        else:
            elements.append(Paragraph("No attendance records found.", getSampleStyleSheet()['Normal']))

        doc.build(elements)
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name='attendance_report.pdf',
                         mimetype='application/pdf')
    
    students = Student.query.filter_by(organization_id=session.get('org_id')).all()
    classes = Class_.query.filter_by(organization_id=session.get('org_id')).all()
    return render_template('{org}/reports.html', students=students, classes=classes)"""

for org in orgs:
    # We need to replace the entire def org_reports(): ... up to return render_template(...)
    # Since regex can be tricky with large multiline, we'll use a specific regex
    pattern = re.compile(
        rf"@app\.route\('/{org}/reports', methods=\['GET', 'POST'\]\)\n"
        rf"@org_required\(\['{org}'\]\)\n"
        rf"def {org}_reports\(\):.*?"
        rf"    return render_template\('{org}/reports\.html', students=students, classes=classes\)",
        re.DOTALL
    )
    # Check if matched
    if pattern.search(app_content):
        app_content = pattern.sub(get_report_replacement(org), app_content)
    else:
        print(f"Warning: Could not match {org}_reports in app.py")

with open(app_py_path, 'w', encoding='utf-8') as f:
    f.write(app_content)
print("Updated app.py with class-wise reporting")

# Update HTML templates
for org in orgs:
    html_path = f"templates/{org}/reports.html"
    if not os.path.exists(html_path):
        continue
    
    with open(html_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    # We want to replace the form content up to the first button or date fields
    # Let's completely replace the form inner HTML before the submit button
    
    # Standardize to use start_date and end_date instead of academic_year
    form_start = html.find('<form method="POST">') + len('<form method="POST">')
    form_end = html.find('<button type="submit"', form_start)
    
    new_form_content = """
                    <div class="mb-3">
                        <label class="form-label">Report Type *</label>
                        <div class="form-check">
                            <input class="form-check-input" type="radio" name="report_type" id="reportStudent" value="student" checked onchange="toggleReportType()">
                            <label class="form-check-label" for="reportStudent">Student-wise</label>
                        </div>
                        <div class="form-check">
                            <input class="form-check-input" type="radio" name="report_type" id="reportClass" value="class" onchange="toggleReportType()">
                            <label class="form-check-label" for="reportClass">Class-wise</label>
                        </div>
                    </div>

                    <div class="mb-3" id="classSelectDiv">
                        <label class="form-label">Select Class *</label>
                        <select name="class_id" id="classSelectReport" class="form-select" onchange="filterReportStudents()" required>
                            <option value="">-- Select Class --</option>
                            {% for class in classes %}
                            <option value="{{ class.id }}">{{ class.name }}</option>
                            {% endfor %}
                        </select>
                    </div>

                    <div class="mb-3" id="studentSelectDiv">
                        <label class="form-label">Select Student *</label>
                        <select name="student_id" id="studentSelect" class="form-select" required>
                            <option value="">-- Select Student --</option>
                            {% for student in students %}
                            <option value="{{ student.id }}" data-class-id="{{ student.class_id }}">{{ student.name }} ({{ student.roll_number }}) - {{ student.class_.name }}</option>
                            {% endfor %}
                        </select>
                    </div>
                    
                    <div class="row">
                        <div class="col-md-6 mb-3">
                            <label class="form-label">Start Date</label>
                            <input type="date" name="start_date" class="form-control">
                        </div>
                        <div class="col-md-6 mb-3">
                            <label class="form-label">End Date</label>
                            <input type="date" name="end_date" class="form-control">
                        </div>
                    </div>
                    
                    """
    html = html[:form_start] + new_form_content + html[form_end:]
    
    # Insert toggleReportType JS
    toggle_script = """
function toggleReportType() {
    const isClassWise = document.getElementById('reportClass').checked;
    const studentSelectDiv = document.getElementById('studentSelectDiv');
    const studentSelect = document.getElementById('studentSelect');
    
    if (isClassWise) {
        studentSelectDiv.style.display = 'none';
        studentSelect.removeAttribute('required');
    } else {
        studentSelectDiv.style.display = 'block';
        studentSelect.setAttribute('required', 'required');
    }
}

// Call on load to set initial state
document.addEventListener('DOMContentLoaded', function() {
    toggleReportType();
});
"""
    if "function toggleReportType" not in html:
        html = html.replace("</script>", toggle_script + "\n</script>")
    
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
        
print("Updated html templates for reports")
