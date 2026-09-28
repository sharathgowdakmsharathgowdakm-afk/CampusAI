import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from app import app, db, User, Staff, Organization

def run_tests():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for test client

    client = app.test_client()

    print("=== Testing GET /login and GET /staff/login ===")
    res1 = client.get('/login')
    assert res1.status_code == 200, f"GET /login failed: {res1.status_code}"
    html1 = res1.data.decode('utf-8')
    assert 'HOD' in html1, "HOD missing from /login HTML"
    assert 'Admin' in html1, "Admin missing from /login HTML"
    assert 'Staff' in html1, "Staff missing from /login HTML"
    print("PASS: /login rendered successfully with Role-based options!")

    res2 = client.get('/staff/login')
    assert res2.status_code == 200, f"GET /staff/login failed: {res2.status_code}"
    html2 = res2.data.decode('utf-8')
    assert 'HOD' in html2, "HOD missing from /staff/login HTML"
    assert 'College' in html2, "College missing from /staff/login HTML"
    print("PASS: /staff/login rendered successfully with Org and Role-based options!")

    print("\n=== Testing School: HOD role restriction ===")
    # Trying HOD login on school org should be blocked
    res_school_hod = client.post('/login', data={
        'org_type': 'school',
        'role': 'hod',
        'username': 'any_user',
        'password': 'any_password'
    }, follow_redirects=True)
    assert 'HOD role is only available for College and Institutions' in res_school_hod.data.decode('utf-8')
    print("PASS: School HOD login properly blocked on /login!")

    res_staff_school_hod = client.post('/staff/login', data={
        'org_type': 'school',
        'role': 'hod',
        'email': 'any_user',
        'password': 'any_password'
    }, follow_redirects=True)
    assert 'HOD role is only available for College and Institutions' in res_staff_school_hod.data.decode('utf-8')
    print("PASS: School HOD login properly blocked on /staff/login!")

    print("\n=== Testing College: HOD Login on /staff/login ===")
    res_college_hod = client.post('/staff/login', data={
        'org_type': 'college',
        'role': 'hod',
        'email': 'hod_college@example.com',
        'password': 'hod123'
    }, follow_redirects=False)
    assert res_college_hod.status_code in [302, 200], f"HOD login status: {res_college_hod.status_code}"
    with client.session_transaction() as sess:
        assert sess.get('role') == 'hod', f"Expected role 'hod', got {sess.get('role')}"
        assert sess.get('is_hod') is True, "Expected is_hod=True"
        assert sess.get('org_type') == 'college', f"Expected org_type 'college', got {sess.get('org_type')}"
        print(f"PASS: College HOD logged in! Session role={sess.get('role')}, org_type={sess.get('org_type')}, staff_id={sess.get('staff_id')}")

    print("\n=== Testing College: Staff Login on /staff/login ===")
    res_college_staff = client.post('/staff/login', data={
        'org_type': 'college',
        'role': 'staff',
        'email': 'staff_college@example.com',
        'password': 'staff123'
    }, follow_redirects=False)
    assert res_college_staff.status_code in [302, 200], f"Staff login status: {res_college_staff.status_code}"
    with client.session_transaction() as sess:
        assert sess.get('role') == 'staff', f"Expected role 'staff', got {sess.get('role')}"
        assert sess.get('org_type') == 'college', f"Expected org_type 'college', got {sess.get('org_type')}"
        print(f"PASS: College Staff logged in! Session role={sess.get('role')}, org_type={sess.get('org_type')}")

    print("\n=== Testing Institution: HOD Login on /login ===")
    res_inst_hod = client.post('/login', data={
        'org_type': 'institution',
        'role': 'hod',
        'username': 'hod_inst@example.com',
        'password': 'hod123'
    }, follow_redirects=False)
    assert res_inst_hod.status_code in [302, 200], f"Inst HOD login status: {res_inst_hod.status_code}"
    with client.session_transaction() as sess:
        assert sess.get('role') == 'hod', f"Expected role 'hod', got {sess.get('role')}"
        assert sess.get('org_type') == 'institution', f"Expected org_type 'institution', got {sess.get('org_type')}"
        print(f"PASS: Institution HOD logged in via /login! Session role={sess.get('role')}, org_type={sess.get('org_type')}")

    print("\n=== ALL TESTS PASSED SUCCESSFULLY! ===")

if __name__ == '__main__':
    run_tests()
