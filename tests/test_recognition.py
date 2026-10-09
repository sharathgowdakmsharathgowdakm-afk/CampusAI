"""
Test the attendance recognition by capturing from webcam and posting to the server.
This simulates what the browser does when you click "Mark Attendance".
"""
import requests
import json
import cv2
import base64

# Capture a frame from webcam
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("ERROR: Cannot open webcam. Testing with a static image if available.")
    import sys
    sys.exit(1)

ret, frame = cap.read()
cap.release()

if not ret:
    print("ERROR: Failed to capture frame")
    import sys
    sys.exit(1)

# Encode as JPEG
_, buffer = cv2.imencode('.jpg', frame)
img_b64 = base64.b64encode(buffer).decode('utf-8')

print(f"Captured frame: {frame.shape}")
print(f"Base64 length: {len(img_b64)}")

# Test Class 1 attendance
url = "http://127.0.0.1:5000/school/mark-attendance"

# First, try to login to get a session
session = requests.Session()

# Try the login page
login_url = "http://127.0.0.1:5000/school/login"
try:
    r = session.get(login_url)
    print(f"Login page status: {r.status_code}")
except:
    print("Could not reach login page")

# Try posting attendance directly (may need session/login)
headers = {'Content-Type': 'application/json'}
payload = {
    'image': f'data:image/jpeg;base64,{img_b64}',
    'class_id': 1,
    'organization_id': 1
}

try:
    r = session.post(url, json=payload, timeout=30)
    print(f"\nAttendance Response (status={r.status_code}):")
    if r.status_code == 200:
        data = r.json()
        print(json.dumps(data, indent=2, default=str))
    else:
        print(r.text[:500])
except Exception as e:
    print(f"Error: {e}")
