# CampusAI App

An advanced, production-ready Educational ERP that leverages modern **Face Recognition (MTCNN + dlib)** to automate attendance tracking for schools, colleges, and institutions. 

## 🌟 Key Features

### 1. Smart Attendance via Face Recognition
- **High-Accuracy Detection:** Multi-face detection and recognition using MTCNN and dlib.
- **Precision Tracking:** Accurately logs exact check-in times (e.g., `10:30:45 AM`) in the database and across all dashboards.
- **Automated Absence Alerts:** Instantly sends out automated email and SMS notifications to parents/guardians when a student is marked absent.

### 2. Multi-Tier Organization Management
- **School ERP:** Manage classes, students, and attendance specifically tailored for K-12 schools.
- **College ERP:** Advanced course, semester, and batch management for universities.
- **Institution ERP:** Flexible organizational management for private institutes and coaching centers.

### 3. Comprehensive Portals
- **Admin Portal:** Complete overview of the organization, managing users, courses, and settings.
- **Staff/Faculty Portal:** Dashboard for teachers to mark attendance, manage assignments, and view class analytics.
- **Student Portal:** Dedicated login for students to track their own attendance records, view assignments, and check fee dues.
- **Parent Portal (Upcoming/Partial):** Insights into ward attendance and academic progress.

### 4. Advanced ERP Modules
- **Leave Applications:** End-to-end leave management for staff and students.
- **Fee Management:** Track due dates, view fee status, and generate alerts.
- **LMS (Learning Management System):** Centralized hub for courses, assignments, and study materials.
- **Interactive Dashboards:** Real-time visual analytics and charts for deep insights into attendance and performance.

### 5. Technical Flexibility
- **Database Agnostic:** Seamlessly switch between SQLite (development) and MySQL/PostgreSQL (production).
- **Responsive UI:** Modern, mobile-responsive interface utilizing custom CSS, Bootstrap 5, and interactive JavaScript.

---

## 🚀 Setup & Installation

### Windows (Recommended for end-users)
The easiest way to install the CampusAI App on Windows is by using the official installer.

1. Go to the **Releases** page on GitHub.
2. Download the latest `CampusAISetup.exe`.
3. Double-click the installer and follow the wizard.
4. Launch the application from your Desktop or Start Menu!

### Linux / Mac (For developers & servers)
To run the application from source or deploy it to a server:

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/campusai-app.git
cd campusai-app

# 2. Create a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate

# 3. Install dependencies
# Note: You may need CMake and C++ build tools installed for dlib
pip install -r requirements.txt

# 4. Environment Configuration
cp .env.template .env
# Edit .env with your SMTP (Email) credentials and Fast2SMS API key

# 5. Start the application
python app.py
```

---

## ⚙️ Environment Variables (`.env`)

To utilize the notification features, configure the following in your `.env` file:

```env
# Notification Preferences (email or fast2sms or console)
SMS_PROVIDER=email

# Fast2SMS Configuration (if using SMS)
FAST2SMS_API_KEY=your_api_key

# SMTP Configuration (for Email Notifications)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=465
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
```

---

## 📸 Screenshots

*(Note: Add your actual screenshots here before publishing!)*

- **Splash Screen:** `assets/splash.png`
- **Dashboard Analytics:** `assets/dashboard.png`
- **Face Registration:** `assets/face_register.png`
- **Live Attendance Marking:** `assets/mark_attendance.png`

---

## ☁️ Deployment

This system is fully configured for cloud deployment.
- **Procfile** included for Heroku/Render/AWS.
- **Gunicorn** configured for production WSGI serving.
- See `.env.template` for migrating from SQLite to **MySQL/PostgreSQL**.

## 🛠 Architecture & Tech Stack
- **Backend:** Python, Flask, SQLAlchemy, Flask-JWT-Extended
- **AI/ML:** OpenCV, MTCNN (Multi-task Cascaded Convolutional Networks), face_recognition (dlib)
- **Frontend:** HTML5, Bootstrap 5, Vanilla JS, Chart.js
- **Packaging:** PyInstaller, Inno Setup
