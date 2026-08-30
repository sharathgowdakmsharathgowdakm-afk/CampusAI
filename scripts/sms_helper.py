"""
Absent Student Notification System
====================================
Sends SMS (Fast2SMS) and/or Email alerts when students are marked absent.

Environment Variables Required (.env):
  SMS_PROVIDER=fast2sms
  FAST2SMS_API_KEY=your_key_here

  SMTP_SERVER=smtp.gmail.com
  SMTP_PORT=465
  SMTP_USERNAME=your_email@gmail.com
  SMTP_PASSWORD=your_app_password
"""

import os
import ssl
import smtplib
from email.message import EmailMessage
from datetime import date as date_type

# Read from .env
SMS_PROVIDER = os.environ.get('SMS_PROVIDER', 'console')


def send_absent_sms(
    student_name: str,
    roll_number: str,
    phone: str,
    class_name: str = '',
    absence_date: date_type = None,
    student_email: str = ''
) -> bool:
    """
    Send an SMS and/or Email notification about a student's absence.

    Args:
        student_name:  Full name of the absent student.
        roll_number:   Student's roll number.
        phone:         Registered phone number (student or parent).
        class_name:    Optional class/section name.
        absence_date:  Date of absence (defaults to today).
        student_email: Optional student email for email notification.

    Returns:
        True if at least one notification was sent successfully.
    """
    absence_date = absence_date or date_type.today()
    formatted_date = absence_date.strftime('%d %B %Y')

    message = (
        f"Dear Parent/Guardian, this is an automated alert from CampusAI App. "
        f"Your ward {student_name} (Roll No: {roll_number}) "
    )
    if class_name:
        message += f"of {class_name} "
    message += (
        f"is marked ABSENT on {formatted_date}. "
        f"Please contact the institution for more information."
    )

    sms_sent = False
    email_sent = False

    # --- SMS Notification ---
    if phone:
        if SMS_PROVIDER == 'twilio':
            sms_sent = _send_via_twilio(phone, message)
        elif SMS_PROVIDER == 'fast2sms':
            sms_sent = _send_via_fast2sms(phone, message, student_name)
        else:
            sms_sent = _send_console_simulation(student_name, phone, message)
    else:
        print(f"[SMS SKIP] No phone number for {student_name} ({roll_number})")

    # --- Email Notification ---
    if student_email:
        email_sent = _send_absence_email(
            student_name=student_name,
            roll_number=roll_number,
            class_name=class_name,
            absence_date=formatted_date,
            to_email=student_email
        )

    return sms_sent or email_sent


def _send_absence_email(
    student_name: str,
    roll_number: str,
    class_name: str,
    absence_date: str,
    to_email: str
) -> bool:
    """Send an email notification about absence using configured SMTP."""
    smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com').strip()
    smtp_username = os.environ.get('SMTP_USERNAME', '').strip()
    smtp_password = os.environ.get('SMTP_PASSWORD', '').strip()

    if not smtp_username or not smtp_password:
        print(f"[EMAIL SKIP] SMTP credentials not configured.")
        return False

    subject = f"Absence Alert - {student_name} ({roll_number})"
    body = f"""\
Dear Parent/Guardian,

This is an automated notification from CampusAI App.

Student Name  : {student_name}
Roll Number   : {roll_number}
Class         : {class_name or 'N/A'}
Date of Absence: {absence_date}

Your ward was marked ABSENT for the above date. Please contact the institution for more information.

Regards,
CampusAI App - Attendance System
    """

    try:
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = smtp_username
        msg['To'] = to_email
        msg.set_content(body)

        context = ssl.create_default_context()
        try:
            with smtplib.SMTP_SSL(smtp_server, 465, context=context) as server:
                server.login(smtp_username, smtp_password)
                server.send_message(msg)
        except Exception:
            with smtplib.SMTP(smtp_server, 587) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(smtp_username, smtp_password)
                server.send_message(msg)

        print(f"[EMAIL SENT] Absence alert sent to {to_email} for {student_name}")
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] Failed to send to {to_email}: {e}")
        return False


def _send_console_simulation(name: str, phone: str, message: str) -> bool:
    """Simulate sending - prints to console. Safe for development."""
    print(f"\n{'='*60}")
    print(f"[SMS ALERT - ABSENT NOTIFICATION]")
    print(f"  To:      {phone}")
    print(f"  Student: {name}")
    print(f"  Msg:     {message}")
    print(f"{'='*60}\n")
    return True


def _send_via_twilio(phone: str, message: str) -> bool:
    """Send SMS via Twilio. Requires: pip install twilio"""
    try:
        from twilio.rest import Client
        account_sid = os.environ.get('TWILIO_ACCOUNT_SID')
        auth_token  = os.environ.get('TWILIO_AUTH_TOKEN')
        from_number = os.environ.get('TWILIO_FROM_NUMBER')

        if not all([account_sid, auth_token, from_number]):
            print("[SMS ERROR] Twilio credentials missing in .env")
            return False

        client = Client(account_sid, auth_token)
        client.messages.create(to=phone, from_=from_number, body=message)
        print(f"[SMS SENT via Twilio] To: {phone}")
        return True
    except Exception as e:
        print(f"[SMS ERROR - Twilio] {e}")
        return False


def _send_via_fast2sms(phone: str, message: str, name: str = '') -> bool:
    """Send SMS via Fast2SMS (India). Requires: pip install requests"""
    try:
        import requests
        api_key = os.environ.get('FAST2SMS_API_KEY')
        if not api_key:
            print("[SMS ERROR] FAST2SMS_API_KEY missing in .env")
            return False

        # Clean phone number - remove +91 prefix if present, keep only digits
        clean_phone = phone.strip().lstrip('+').replace(' ', '').replace('-', '')
        if clean_phone.startswith('91') and len(clean_phone) == 12:
            clean_phone = clean_phone[2:]  # Remove country code

        if len(clean_phone) != 10:
            print(f"[SMS SKIP] Invalid phone number format for {name}: {phone}")
            return False

        payload = {
            "route": "q",
            "message": message,
            "language": "english",
            "flash": 0,
            "numbers": clean_phone
        }
        headers = {
            "authorization": api_key,
            "Content-Type": "application/json"
        }
        response = requests.post(
            "https://www.fast2sms.com/dev/bulkV2",
            json=payload,
            headers=headers,
            timeout=10
        )
        result = response.json()
        if result.get('return') is True:
            print(f"[SMS SENT via Fast2SMS] To: {clean_phone} ({name})")
            return True
        else:
            print(f"[SMS ERROR - Fast2SMS] Response: {result}")
            return False
    except Exception as e:
        print(f"[SMS ERROR - Fast2SMS] {e}")
        return False
