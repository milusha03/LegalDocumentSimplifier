# backend_app/email_utils.py
import smtplib
from email.mime.text import MIMEText

def send_otp_email(recipient_email, otp_code):
    sender_email = "milushasilva03@gmail.com"
    sender_password = "czaf eghv garg nctb"

    msg = MIMEText(f"Your OTP code is: {otp_code}")
    msg["Subject"] = "Your Legal Simplifier OTP"
    msg["From"] = sender_email
    msg["To"] = recipient_email

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender_email, sender_password)
        server.send_message(msg)
