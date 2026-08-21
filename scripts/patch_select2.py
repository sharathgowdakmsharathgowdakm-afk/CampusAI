import os

css_insert = '''{% block extra_css %}
<!-- Select2 CSS -->
<link href="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css" rel="stylesheet" />
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/select2-bootstrap-5-theme@1.3.0/dist/select2-bootstrap-5-theme.min.css" />
<style>'''

js_mark_attendance = '''// Select2 Initialization
$(document).ready(function() {
    $('#classSelect').select2({
        theme: 'bootstrap-5',
        placeholder: "-- Select Class --"
    });
});
</script>
{% endblock %}

{% block extra_js %}
<script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js"></script>
{% endblock %}'''

js_face_register = '''// Select2 Initialization
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
});
</script>
{% endblock %}

{% block extra_js %}
<script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js"></script>
{% endblock %}'''

for root, dirs, files in os.walk('templates'):
    for f in files:
        if f in ['face_register.html', 'mark_attendance.html']:
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            modified = False
            # Replace CSS
            if '<!-- Select2 CSS -->' not in content:
                content = content.replace('{% block extra_css %}\n<style>', css_insert)
                modified = True
            
            # Replace JS
            if 'Select2 Initialization' not in content:
                if 'mark_attendance' in f:
                    content = content.replace('</script>\n{% endblock %}', js_mark_attendance)
                else:
                    content = content.replace('</script>\n{% endblock %}', js_face_register)
                modified = True
                    
            if modified:
                with open(path, 'w', encoding='utf-8') as file:
                    file.write(content)
                print(f'Updated {path}')
print('Done!')
