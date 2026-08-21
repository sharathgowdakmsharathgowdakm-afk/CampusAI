import os

init_code = """// Select2 Initialization
$(document).ready(function() {
    $('#classSelect').select2({
        theme: 'bootstrap-5',
        placeholder: "-- Select Class --"
    });
});"""

init_code_face = """// Select2 Initialization
$(document).ready(function() {
    $('#classSelect').select2({
        theme: 'bootstrap-5',
        placeholder: "-- Select Class --"
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
        placeholder: "-- Select Student --"
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
});"""

for root, dirs, files in os.walk('templates'):
    for f in files:
        if f in ['face_register.html', 'mark_attendance.html']:
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            modified = False
            
            if 'mark_attendance' in f:
                if init_code in content:
                    content = content.replace(init_code, '')
                    
                    extra_js_block = """{% block extra_js %}
<script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js"></script>
<script>
""" + init_code + """
</script>
{% endblock %}"""
                    content = content.replace("{% block extra_js %}\n<script src=\"https://code.jquery.com/jquery-3.7.0.min.js\"></script>\n<script src=\"https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js\"></script>\n{% endblock %}", extra_js_block)
                    modified = True
            else:
                if init_code_face in content:
                    content = content.replace(init_code_face, '')
                    
                    extra_js_block = """{% block extra_js %}
<script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js"></script>
<script>
""" + init_code_face + """
</script>
{% endblock %}"""
                    content = content.replace("{% block extra_js %}\n<script src=\"https://code.jquery.com/jquery-3.7.0.min.js\"></script>\n<script src=\"https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js\"></script>\n{% endblock %}", extra_js_block)
                    modified = True
            
            if modified:
                with open(path, 'w', encoding='utf-8') as file:
                    file.write(content)
                print(f'Fixed {path}')
print('Done!')
