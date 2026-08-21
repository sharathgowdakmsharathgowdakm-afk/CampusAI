import os

js_mark_attendance = """// Select2 Initialization
$(document).ready(function() {
    $('#classSelect').select2({
        theme: 'bootstrap-5',
        placeholder: '-- Select Class --'
    });
});"""

js_face_register = """// Select2 Initialization
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
});"""

for root, dirs, files in os.walk('templates'):
    for f in files:
        if f in ['face_register.html', 'mark_attendance.html']:
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            # Find the empty script tag in extra_js block
            if 'mark_attendance' in f:
                content = content.replace('<script>\n\n</script>', f'<script>\n{js_mark_attendance}\n</script>')
            else:
                content = content.replace('<script>\n\n</script>', f'<script>\n{js_face_register}\n</script>')
                
            with open(path, 'w', encoding='utf-8') as file:
                file.write(content)
            print(f'Fixed {path}')
print('Done!')
