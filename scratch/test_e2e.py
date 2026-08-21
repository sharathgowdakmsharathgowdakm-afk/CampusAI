"""
Step 1: End-to-End System Verification Script
Tests all major flows: Login, Dashboard, Classes, Students, Face Register, Attendance, Reports, Student Portal
"""
import requests
import sys

BASE = "http://127.0.0.1:5000"
s = requests.Session()

results = []

def test(name, condition, detail=""):
    status = "[PASS]" if condition else "[FAIL]"
    results.append((name, status, detail))
    print(f"  {status}: {name}" + (f" -- {detail}" if detail else ""))

print("=" * 60)
print("STEP 1: COMPLETE SYSTEM VERIFICATION")
print("=" * 60)

# ── 1. Splash Page ──
print("\n[1] Splash Page")
r = s.get(f"{BASE}/")
test("Splash page loads", r.status_code == 200)
test("Title present", "Smart Attendance" in r.text)

# ── 2. Login Page ──
print("\n[2] Login Page")
r = s.get(f"{BASE}/login")
test("Login page loads", r.status_code == 200)
test("Login form present", "username" in r.text.lower() and "password" in r.text.lower())

# ── 3. School Login ──
print("\n[3] School Login")
# Extract CSRF token
import re
csrf_match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text)
csrf = csrf_match.group(1) if csrf_match else ""
login_data = {
    "org_type": "school",
    "username": "smvit_school",
    "password": "school123",
    "csrf_token": csrf
}
r = s.post(f"{BASE}/login", data=login_data, allow_redirects=True)
test("School login succeeds", r.status_code == 200, f"Redirected to: {r.url}")
test("Dashboard content loads", "dashboard" in r.url.lower() or "Dashboard" in r.text or "Total Students" in r.text)

# ── 4. School Dashboard ──
print("\n[4] School Dashboard")
r = s.get(f"{BASE}/school/dashboard")
test("Dashboard page loads", r.status_code == 200)
test("Total Students stat", "Total Students" in r.text)
test("Total Classes stat", "Total Classes" in r.text)
test("Today's Attendance stat", "Attendance" in r.text)
test("Analytics chart canvas", "attendanceChart" in r.text)

# ── 5. School Classes ──
print("\n[5] School Classes")
r = s.get(f"{BASE}/school/classes")
test("Classes page loads", r.status_code == 200)

# ── 6. Add Class Page ──
print("\n[6] Add Class Page")
r = s.get(f"{BASE}/school/add-class")
test("Add class page loads", r.status_code == 200)

# ── 7. Students Page ──
print("\n[7] Students Page")
r = s.get(f"{BASE}/school/students")
test("Students page loads", r.status_code == 200)

# ── 8. Add Student Page ──
print("\n[8] Add Student Page")
r = s.get(f"{BASE}/school/add-student")
test("Add student page loads", r.status_code == 200)

# ── 9. Face Registration Page ──
print("\n[9] Face Registration Page")
r = s.get(f"{BASE}/school/face-register")
test("Face register page loads", r.status_code == 200)
test("Camera/Upload UI present", "cameraSection" in r.text or "uploadSection" in r.text)
test("Multi-pose UI present", "poseInstruction" in r.text or "Capture 5 Poses" in r.text or "startMultiCapture" in r.text)

# ── 10. Mark Attendance Page ──
print("\n[10] Mark Attendance Page")
r = s.get(f"{BASE}/school/mark-attendance")
test("Mark attendance page loads", r.status_code == 200)

# ── 11. Attendance Records ──
print("\n[11] Attendance Records")
r = s.get(f"{BASE}/school/attendance-records")
test("Attendance records page loads", r.status_code == 200)

# ── 12. Reports Page ──
print("\n[12] Reports Page")
r = s.get(f"{BASE}/school/reports")
test("Reports page loads", r.status_code == 200)

# ── 13. Analytics Data Endpoint ──
print("\n[13] Analytics Data API")
r = s.get(f"{BASE}/analytics-data")
test("Analytics endpoint responds", r.status_code == 200)
try:
    j = r.json()
    test("Returns labels", "labels" in j, f"labels={j.get('labels')}")
    test("Returns attendance_data", "attendance_data" in j)
except Exception as e:
    test("JSON parsing", False, str(e))

# ── 14. Logout & College Login ──
print("\n[14] College Login")
r = s.get(f"{BASE}/login")
csrf_match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text)
csrf = csrf_match.group(1) if csrf_match else ""
r = s.post(f"{BASE}/login", data={
    "org_type": "college", "username": "smvit_college", "password": "college123", "csrf_token": csrf
}, allow_redirects=True)
test("College login succeeds", r.status_code == 200, f"URL: {r.url}")

# ── 15. College Dashboard ──
print("\n[15] College Dashboard")
r = s.get(f"{BASE}/college/dashboard")
test("College dashboard loads", r.status_code == 200)

# ── 16. Institution Login ──
print("\n[16] Institution Login")
r = s.get(f"{BASE}/login")
csrf_match = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text)
csrf = csrf_match.group(1) if csrf_match else ""
r = s.post(f"{BASE}/login", data={
    "org_type": "institution", "username": "smvit_institution", "password": "institution123", "csrf_token": csrf
}, allow_redirects=True)
test("Institution login succeeds", r.status_code == 200, f"URL: {r.url}")

# ── 17. Institution Dashboard ──
print("\n[17] Institution Dashboard")
r = s.get(f"{BASE}/institution/dashboard")
test("Institution dashboard loads", r.status_code == 200)

# ── 18. Student Portal ──
print("\n[18] Student Portal")
r = s.get(f"{BASE}/student/login")
test("Student login page loads", r.status_code == 200)
test("Student login form present", "Roll Number" in r.text or "roll_number" in r.text)

# ── Summary ──
print("\n" + "=" * 60)
passed = sum(1 for _, s, _ in results if "PASS" in s)
failed = sum(1 for _, s, _ in results if "FAIL" in s)
print(f"RESULTS: {passed} passed, {failed} failed out of {len(results)} tests")
if failed > 0:
    print("\nFailed tests:")
    for name, status, detail in results:
        if "FAIL" in status:
            print(f"  ❌ {name}: {detail}")
print("=" * 60)
