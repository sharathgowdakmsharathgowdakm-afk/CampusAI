import re
import os

with open('templates/school/face_register.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Remove the faulty JS in block content
js_pattern = r'// Select2 Initialization.*?\}\);\n'
content = re.sub(js_pattern, '', content, flags=re.DOTALL)

# Ensure extra_js has the script
if 'let allStudents = [];' not in content:
    js_face_register = """
<script>
// Select2 Initialization
$(document).ready(function() {
    $('#classSelect').select2({
        theme: 'bootstrap-5',
        placeholder: '-- Select Class --'
    });
    
    let allStudents = [];
    $('#studentSelect option').each(function() {
        if ($(this).val()) {
            allStudents.push({
                id: $(this).val(),
                text: $(this).text(),
                classId: $(this).attr('data-class-id')
            });
        }
    });

    $('#studentSelect').select2({
        theme: 'bootstrap-5',
        placeholder: '-- Select Student --'
    });

    window.filterStudents = function() {
        let classId = $('#classSelect').val();
        let $studentSelect = $('#studentSelect');
        
        $studentSelect.empty();
        $studentSelect.append(new Option('-- Select Student --', '', false, false));
        
        allStudents.forEach(function(student) {
            if (!classId || student.classId === classId) {
                let newOption = new Option(student.text, student.id, false, false);
                $(newOption).attr('data-class-id', student.classId);
                $studentSelect.append(newOption);
            }
        });
        
        $studentSelect.trigger('change');
    };
});
</script>
"""
    content = content.replace('{% block extra_js %}\n<script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>\n<script src="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js"></script>\n{% endblock %}', '{% block extra_js %}\n<script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>\n<script src="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js"></script>\n' + js_face_register + '{% endblock %}')

with open('templates/school/face_register.html', 'w', encoding='utf-8') as f:
    f.write(content)

with open('templates/school/mark_attendance.html', 'r', encoding='utf-8') as f:
    content2 = f.read()

content2 = re.sub(js_pattern, '', content2, flags=re.DOTALL)
if "$('#classSelect').select2({" not in content2:
    js_mark_attendance = """
<script>
// Select2 Initialization
$(document).ready(function() {
    $('#classSelect').select2({
        theme: 'bootstrap-5',
        placeholder: '-- Select Class --'
    });
});
</script>
"""
    content2 = content2.replace('{% block extra_js %}\n<script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>\n<script src="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js"></script>\n{% endblock %}', '{% block extra_js %}\n<script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>\n<script src="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js"></script>\n' + js_mark_attendance + '{% endblock %}')

with open('templates/school/mark_attendance.html', 'w', encoding='utf-8') as f:
    f.write(content2)

print('Fixed school templates')
