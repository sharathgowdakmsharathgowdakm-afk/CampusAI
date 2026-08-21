import os
import re

orgs = ['school', 'college', 'institution']
base_dir = 'templates'

for org in orgs:
    # 1. Update classes.html
    classes_path = os.path.join(base_dir, org, 'classes.html')
    if os.path.exists(classes_path):
        with open(classes_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replace <td><strong>{{ class.name }}</strong></td> with link
        content = content.replace(
            "<td><strong>{{ class.name }}</strong></td>",
            f"""<td><a href="/{org}/students?class_id={{{{ class.id }}}}" style="text-decoration: none;"><strong>{{{{ class.name }}}}</strong></a></td>"""
        )
        
        with open(classes_path, 'w', encoding='utf-8') as f:
            f.write(content)

    # 2. Update face_register.html
    face_reg_path = os.path.join(base_dir, org, 'face_register.html')
    if os.path.exists(face_reg_path):
        with open(face_reg_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Insert class select before student select
        class_select_html = """
                <!-- Class Select -->
                <div class="mb-4">
                    <label class="form-label fw-semibold">Select Class <span class="text-danger">*</span></label>
                    <select id="classSelect" class="form-select form-select-lg" required onchange="filterStudents()">
                        <option value="">-- Select Class --</option>
                        {% for class in classes %}
                        <option value="{{ class.id }}">{{ class.name }}</option>
                        {% endfor %}
                    </select>
                </div>
"""
        if '<!-- Class Select -->' not in content:
            content = content.replace(
                "<!-- Student Select -->",
                class_select_html + "\n                <!-- Student Select -->"
            )

            # Update student options to include data-class-id
            content = content.replace(
                """<option value="{{ student.id }}">{{ student.name }} &nbsp;({{ student.roll_number }})</option>""",
                """<option value="{{ student.id }}" data-class-id="{{ student.class_id }}">{{ student.name }} &nbsp;({{ student.roll_number }})</option>"""
            )

            # Add filterStudents script
            filter_script = """
function filterStudents() {
    const classId = document.getElementById('classSelect').value;
    const studentSelect = document.getElementById('studentSelect');
    studentSelect.value = ''; // Reset student selection
    const options = studentSelect.querySelectorAll('option[data-class-id]');
    
    options.forEach(option => {
        if (!classId || option.getAttribute('data-class-id') === classId) {
            option.style.display = '';
        } else {
            option.style.display = 'none';
        }
    });
}
"""
            content = content.replace("let stream = null;", filter_script + "\nlet stream = null;")
        
        with open(face_reg_path, 'w', encoding='utf-8') as f:
            f.write(content)

    # 3. Update reports.html
    reports_path = os.path.join(base_dir, org, 'reports.html')
    if os.path.exists(reports_path):
        with open(reports_path, 'r', encoding='utf-8') as f:
            content = f.read()

        class_select_html_report = """
                    <div class="mb-3">
                        <label class="form-label">Select Class</label>
                        <select id="classSelectReport" class="form-select" onchange="filterReportStudents()">
                            <option value="">-- All Classes --</option>
                            {% for class in classes %}
                            <option value="{{ class.id }}">{{ class.name }}</option>
                            {% endfor %}
                        </select>
                    </div>
"""
        if 'id="classSelectReport"' not in content:
            content = content.replace(
                """<div class="mb-3">
                        <label class="form-label">Select Student *</label>""",
                class_select_html_report + """
                    <div class="mb-3">
                        <label class="form-label">Select Student *</label>"""
            )

            content = content.replace(
                """<option value="{{ student.id }}">{{ student.name }} ({{ student.roll_number }}) - {{ student.class_.name }}</option>""",
                """<option value="{{ student.id }}" data-class-id="{{ student.class_id }}">{{ student.name }} ({{ student.roll_number }}) - {{ student.class_.name }}</option>"""
            )

            filter_script_report = """
{% block extra_js %}
<script>
function filterReportStudents() {
    const classId = document.getElementById('classSelectReport').value;
    const studentSelect = document.querySelector('select[name="student_id"]');
    studentSelect.value = ''; // Reset
    const options = studentSelect.querySelectorAll('option[data-class-id]');
    
    options.forEach(option => {
        if (!classId || option.getAttribute('data-class-id') === classId) {
            option.style.display = '';
        } else {
            option.style.display = 'none';
        }
    });
}
</script>
{% endblock %}
"""
            if '{% block extra_js %}' not in content:
                content += filter_script_report

        with open(reports_path, 'w', encoding='utf-8') as f:
            f.write(content)

print("Updated HTML templates successfully!")
