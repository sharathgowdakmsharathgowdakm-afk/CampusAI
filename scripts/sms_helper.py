"""
SMS Helper - Absent Student Notification System
================================================
Sends SMS alerts to parents/guardians when students are marked absent.

To switch from Console Simulation to a real SMS provider, update the
`SMS_PROVIDER` variable and fill in your API credentials in .env:

  TWILIO_ACCOUNT_SID=ACxxxxx
  TWILIO_AUTH_TOKEN=xxxxx
  TWILIO_FROM_NUMBER=+1234567890

  # OR for Fast2SMS (India):
  FAST2SMS_API_KEY=xxxxx
"""

import os
from datetime import date as date_type

# Change to 'twilio' or 'fast2sms' when you have API credentials
SMS_PROVIDER = os.environ.get('SMS_PROVIDER', 'console')


def send_absent_sms(student_name: str, roll_number: str, phone: str, class_name: str = '', absence_date: date_type = None) -> bool:
    """
    Send an SMS notification to the student/parent about absence.

    Args:
        student_name: Full name of the absent student.
        roll_number: Student's roll number.
        phone: Registered phone number (student or parent).
        class_name: Optional class/section name.
        absence_date: Date of absence (defaults to today).

    Returns:
        True if message was sent (or simulated), False if it failed.
    """
    if not phone:
        print(f"[SMS SKIP] No phone number registered for {student_name} ({roll_number})")
        return False

    absence_date = absence_date or date_type.today()
    formatted_date = absence_date.strftime('%d %B %Y')

    message = (
        f"Dear Parent/Guardian, this is an automated alert from your institution. "
        f"Your ward {student_name} (Roll No: {roll_number}) "
    )
    if class_name:
        message += f"of {class_name} "
    message += f"is marked ABSENT on {formatted_date}. Please contact the institution for more information."

    if SMS_PROVIDER == 'twilio':
        return _send_via_twilio(phone, message)
    elif SMS_PROVIDER == 'fast2sms':
        return _send_via_fast2sms(phone, message)
    else:
        return _send_console_simulation(student_name, phone, message)


def _send_console_simulation(name: str, phone: str, message: str) -> bool:
    """Simulate sending - prints to console. Safe for development."""
    print(f"\n{'='*60}")
    print(f"[SMS ALERT - ABSENT NOTIFICATION]")
    print(f"  To:   {phone}")
    print(f"  Student: {name}")
    print(f"  Msg:  {message}")
    print(f"{'='*60}\n")
    return True


def _send_via_twilio(phone: str, message: str) -> bool:
    """Send SMS via Twilio. Requires twilio package: pip install twilio"""
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


def _send_via_fast2sms(phone: str, message: str) -> bool:
    """Send SMS via Fast2SMS (India). Requires requests: pip install requests"""
    try:
        import requests
        api_key = os.environ.get('FAST2SMS_API_KEY')
        if not api_key:
            print("[SMS ERROR] FAST2SMS_API_KEY missing in .env")
            return False

        payload = {
            "route": "q",
            "message": message,
            "language": "english",
            "flash": 0,
            "numbers": phone.lstrip('+').replace(' ', '')
        }
        headers = {"authorization": api_key, "Content-Type": "application/json"}
        response = requests.post(
            "https://www.fast2sms.com/dev/bulkV2",
            json=payload,
            headers=headers,
            timeout=10
        )
        result = response.json()
        if result.get('return') is True:
            print(f"[SMS SENT via Fast2SMS] To: {phone}")
            return True
        else:
            print(f"[SMS ERROR - Fast2SMS] {result}")
            return False
    except Exception as e:
        print(f"[SMS ERROR - Fast2SMS] {e}")
        return False
