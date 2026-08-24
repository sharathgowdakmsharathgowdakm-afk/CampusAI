# CampusAI App

An advanced, production-ready Educational ERP that leverages modern **Face Recognition (MTCNN + dlib)** to automate attendance tracking for schools, colleges, and institutions.

## Features
- **Face Recognition:** High-accuracy multi-face detection using MTCNN and dlib.
- **School ERP:** Manage classes, students, and attendance specifically for K-12 schools.
- **College ERP:** Advanced course, semester, and batch management for universities.
- **Institution ERP:** Flexible organizational management for private institutes.
- **Attendance Analytics:** Real-time visual dashboards and downloadable PDF reports.
- **Student Portal:** Dedicated login for students to track their own attendance records.
- **Database Agnostic:** Seamlessly switch between SQLite (development) and MySQL (production).

---

## Installation

### Windows (Recommended for end-users)
The easiest way to install the CampusAI App on Windows is by using the official installer.

1. Go to the **Releases** page on GitHub.
2. Download the latest `SmartAttendanceSetup.exe`.
3. Double-click the installer and follow the wizard.
4. Launch the application from your Desktop or Start Menu!

### Linux / Mac (For developers & servers)
To run the application from source or deploy it to a server:

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/smart-attendance-system.git
cd smart-attendance-system

# 2. Create a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the application
python app.py
```

---

## Screenshots

*(Note: Add your actual screenshots here before publishing!)*

### Splash Screen
![Splash Screen](assets/splash.png)

### Dashboard Analytics
![Dashboard](assets/dashboard.png)

### Face Registration
![Face Registration](assets/face_register.png)

### Live Attendance Marking
![Mark Attendance](assets/mark_attendance.png)

---

## Deployment

This system is fully configured for cloud deployment.
- **Procfile** included for Heroku/Render/AWS.
- **Gunicorn** configured for production WSGI serving.
- See `.env.template` for migrating from SQLite to **MySQL/PostgreSQL**.

## Architecture & Tech Stack
- **Backend:** Python, Flask, SQLAlchemy, Flask-JWT-Extended
- **AI/ML:** OpenCV, MTCNN (Multi-task Cascaded Convolutional Networks), face_recognition (dlib)
- **Frontend:** HTML5, Bootstrap 5, Vanilla JS, Chart.js
- **Packaging:** PyInstaller, Inno Setup
