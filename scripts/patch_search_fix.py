import os

for root, dirs, files in os.walk('templates'):
    for f in files:
        if f in ['face_register.html', 'mark_attendance.html']:
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()

            modified = False

            # 1. Remove onchange="filterStudents()" from classSelect HTML since Select2 handles it
            if 'onchange="filterStudents()"' in content:
                content = content.replace(
                    'onchange="filterStudents()"',
                    ''
                )
                modified = True

            # 2. In face_register: Remove the OLD vanilla JS filterStudents function
            # (the one that uses option.style.display - not the Select2 one)
            old_filter = """function filterStudents() {
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
}"""
            if old_filter in content:
                content = content.replace(old_filter, '')
                modified = True

            # 3. Wire Select2 change event to filterStudents inside the document.ready block
            # For face_register pages, add .on('change', ...) after classSelect.select2 init
            if 'face_register' in f and 'classSelect').select2(' in content and "on('change', window.filterStudents)" not in content:
                content = content.replace(
                    """    // Initialize Select2 on Class Select
    $('#classSelect').select2({
        theme: 'bootstrap-5',
        placeholder: "-- Select Class --"
    });""",
                    """    // Initialize Select2 on Class Select
    $('#classSelect').select2({
        theme: 'bootstrap-5',
        placeholder: "-- Select Class --"
    }).on('change', function() {
        if (window.filterStudents) window.filterStudents();
    });"""
                )
                modified = True

            if modified:
                with open(path, 'w', encoding='utf-8') as file:
                    file.write(content)
                print(f'Updated {path}')

print('Done!')
