"""Apply live-clock header patch to timetable.html"""
path = r'c:\Users\shara\OneDrive\Desktop\smartAttendence\attendence_app\templates\campus\timetable.html'
with open(path, encoding='utf-8') as f:
    content = f.read()

old = (
    '        <span class="badge-campus" style="background:rgba(255,255,255,0.25); color:#fff; font-weight:600; padding:4px 12px; border-radius:20px;">\n'
    '            {{ today_slots|length }} Periods Scheduled Today\n'
    '        </span>\n'
    '    </div>'
)

new = (
    '        <div style="display:flex; align-items:center; gap:12px;">\n'
    '            <span id="live-clock" style="font-family:monospace; font-weight:700; font-size:1.05rem; color:#fff; background:rgba(255,255,255,0.15); padding:4px 12px; border-radius:20px; letter-spacing:1px;">--:--:--</span>\n'
    '            <span class="badge-campus" style="background:rgba(255,255,255,0.25); color:#fff; font-weight:600; padding:4px 12px; border-radius:20px;">\n'
    '                {{ today_slots|length }} Periods Scheduled Today\n'
    '            </span>\n'
    '        </div>\n'
    '    </div>'
)

if old in content:
    content = content.replace(old, new, 1)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('Header updated: live-clock added.')
else:
    print('Pattern not found. Showing context:')
    idx = content.find('Periods Scheduled Today')
    print(repr(content[max(0, idx-300):idx+50]))
