import sys, os
sys.path.insert(0, os.path.abspath('.'))
from app import app

with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'smvit_school'
        sess['org_type'] = 'school'
        sess['org_id'] = 1
        sess['org_name'] = 'CampusAI School'
    
    r = c.get('/school/academic-calendar')
    html = r.data.decode('utf-8')
    print("Status:", r.status_code)
    print("Length:", len(html))
    print("Has 'mobile-event-card':", 'mobile-event-card' in html)
    print("Has 'mobile-date-tile':", 'mobile-date-tile' in html)
    print("Has 'filter-pills-container':", 'filter-pills-container' in html)
    print("Has 'stat-summary-card':", 'stat-summary-card' in html)
    print("Has 'calendar-search-input':", 'calendar-search-input' in html)
    print("Has 'desktopEventsTable':", 'desktopEventsTable' in html)
    
    # Save output to scratch/rendered_calendar.html so we can test it with Headless Edge!
    with open('scratch/rendered_calendar.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("Saved rendered HTML to scratch/rendered_calendar.html")
