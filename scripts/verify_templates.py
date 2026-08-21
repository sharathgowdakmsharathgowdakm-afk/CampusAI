import os

for root, dirs, files in os.walk('templates'):
    for f in files:
        if f in ['face_register.html', 'mark_attendance.html']:
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            print(f'--- {path} ---')
            print('  onchange=filterStudents:', 'onchange="filterStudents()"' in content)
            print('  old vanilla filterStudents:', 'option.style.display' in content)
            print('  Select2 init:', "classSelect').select2(" in content)
            print('  select2.min.css:', 'select2.min.css' in content)
            print('  CCTV option:', 'Camera Source' in content)
            print()
