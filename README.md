# CampusAI – Smart Attendance System & Educational ERP

An enterprise-grade Educational ERP and Biometrics platform powered by deep learning face recognition (**SCRFD + ArcFace**), designed for high-speed multi-face attendance tracking across schools, colleges, and educational institutions.

---

## 🌟 Key Features

### 1. High-Performance Multi-Face Attendance Pipeline
- **SCRFD Detection (InsightFace):** Ultra-lightweight, high-accuracy multi-face detection supporting classroom crowd photos with up to 100+ faces in a single capture.
- **ArcFace Feature Embeddings:** 512-dimensional normalized embeddings for state-of-the-art face verification with cosine similarity matching.
- **Biometric Quality Filtering:** Real-time pre-filtering on Laplacian sharpness, luminance brightness, landmark pose (yaw/roll), and minimum resolution before feature extraction.
- **Dual-Model & Centroid-Based Matching:**
  - Aggregates multi-angle registrations into student centroid vectors to eliminate lighting/pose variance.
  - Backwards-compatible hybrid support for both 512-d ArcFace vectors and legacy 128-d biometric encodings without requiring students to re-register.
- **Strict Class-Wise & Organization Isolation:** Recognition strictly filters against students enrolled in the selected class and tenant, completely preventing identity cross-over between different classes.
- **Extended Detection Modes:** Distance-adaptive resolution scaling for 50m (standard classroom) and 100m (extended crowd/hall) detection ranges.
- **Automated Absence Alerts:** Sends instant SMS/email alerts to parents or guardians when a student is marked absent.

### 2. Multi-Tier Educational ERP
- **School ERP:** Tailored for K-12 schools (Class & Section management, student records, timetable schedules).
- **College ERP:** Designed for colleges and universities (Degree programs, departments, study years, semesters).
- **Institution ERP:** Flexible structure for coaching institutes, training academies, and corporate learning centers.

### 3. Comprehensive Portals & Dashboards
- **Admin Portal:** Comprehensive oversight of classes, courses, staff members, academic calendars, and biometric registrations.
- **Staff/Faculty Portal:** Allows teachers to mark attendance via webcam/uploaded classroom photos, view timetable schedules, and manage student leave applications.
- **Student Portal & Dashboard:**
  - Real-time attendance percentage with Safe Standing (≥75%) vs Shortage warnings.
  - **Live Face Biometric Status & Counts:** Direct indicators showing verified registration status and registered sample counts.
  - Daily timetable period sequence and assignment submissions.
- **Students Management Pages:** Complete student rosters with live registration ratio badges (e.g. `18/18 Faces Registered`) and per-student verification status chips.

### 4. Advanced ERP Modules
- **Timetable & Auto-Schedule:** Auto-fills subjects during attendance based on day-of-week and scheduled timetable slots.
- **Leave Management:** Online workflow for applying, reviewing, and approving student and staff leave requests.
- **Fee Management:** Track due dates, fee structures, receipts, and outstanding dues.
- **Learning Management System (LMS):** Course materials, assignments, and academic tracking.

---

## 📐 Face Recognition Architecture

```text
Classroom Camera / Upload
           ↓
    SCRFD Detector (ONNX)
   [Multi-face detection & 5-point landmarks]
           ↓
    Face Quality Filter
   [Blur, Brightness, Pose Angle, Min Box Size]
           ↓
    ArcFace Extractor (ONNX)
   [512-d Normalised Biometric Embeddings]
           ↓
   Class-Scoped Gallery Matcher
   [Strict (org_id, class_id) Isolation + Centroid Search]
           ↓
   Deduplication & Verification
           ↓
   Attendance Persistence & Absence SMS Alerts
```

---

## 🛠 Tech Stack

- **Backend:** Python 3.10+, Flask, Flask-SQLAlchemy, SQLite (default) / MySQL / PostgreSQL
- **AI / Computer Vision:**
  - SCRFD (10G model, ONNX Runtime)
  - ArcFace (ResNet50 / w600k_r50, ONNX Runtime)
  - OpenCV (`cv2`)
  - dlib / `face_recognition` (Hybrid legacy support)
  - NumPy, SciPy
- **Frontend:** HTML5, Bootstrap 5, Vanilla JavaScript, Chart.js, Select2
- **Notification Services:** SMTP (Email), Fast2SMS API

---

## 📁 Project Directory Structure

```text
attendence_app/
├── app.py                     # Main application entry point & route controllers
├── create_tables.py           # Database table initialization script
├── face_api/                  # SCRFD + ArcFace Biometrics Engine
│   ├── detector.py            # SCRFD detector (ONNX)
│   ├── recognizer.py          # ArcFace feature extractor (ONNX)
│   ├── quality.py             # Face crop quality filter
│   ├── matcher.py             # Cosine & Euclidean similarity search
│   ├── embedding_store.py     # Class-scoped gallery & centroid cache
│   ├── attendance.py          # Attendance orchestration & face registration
│   └── config.py              # Biometric thresholds & model configurations
├── face_models/               # ONNX model weights (det_10g.onnx, w600k_r50.onnx)
├── face_encodings/            # Registered biometric files
├── instance/                  # SQLite database storage (attendance.db)
├── static/                    # CSS stylesheets, UI JavaScript, branding assets
├── templates/                 # Jinja2 HTML templates
│   ├── school/                # School ERP views (students, mark_attendance, dashboard)
│   ├── college/               # College ERP views
│   ├── institution/           # Institution ERP views
│   └── student/               # Student portal & dashboard views
├── tests/                     # Test suites, benchmarks, and diagnostic utilities
│   ├── benchmark_face_recognition.py
│   ├── test_biometrics_upgrade.py
│   ├── test_recognition.py
│   ├── migrate_face_encodings.py
│   └── debug_encodings.py
└── uploads/                   # Temporary attendance uploads and student photos
```

---

## 🚀 Setup & Quick Start

### 1. Prerequisites
- Python 3.10 or higher
- C++ Build Tools (required if installing dlib from source on Windows)
- Virtual environment recommended

### 2. Installation

```bash
# 1. Clone repository
git clone https://github.com/yourusername/campusai-app.git
cd campusai-app

# 2. Create virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Verify Face Recognition Models
# Ensure 'det_10g.onnx' and 'w600k_r50.onnx' exist in the face_models/ folder.
```

### 3. Environment Configuration (`.env`)

Copy `.env.template` to `.env` and configure your credentials:

```env
SECRET_KEY=your_secret_key_here

# Notification Provider: 'email', 'fast2sms', or 'console'
SMS_PROVIDER=email

# Fast2SMS API (for SMS notifications)
FAST2SMS_API_KEY=your_fast2sms_api_key

# SMTP Configuration (for automated email alerts)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=465
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
```

### 4. Running the Application

```bash
# Initialize database tables (if starting fresh)
python create_tables.py

# Launch the Flask application
python app.py
```

The application will be accessible at:
```text
http://127.0.0.1:5000/
```

---

## 🧪 Running Tests & Diagnostics

All diagnostic and benchmark scripts are located in the `tests/` directory:

```bash
# Run the biometrics upgrade verification suite
python tests/test_biometrics_upgrade.py

# Run speed and accuracy benchmarks
python tests/benchmark_face_recognition.py

# Inspect database face encoding distributions
python tests/debug_encodings.py
```

---

## 📄 License
This project is proprietary and intended for institutional educational attendance management.
