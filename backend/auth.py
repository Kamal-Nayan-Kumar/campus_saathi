import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import random
import string
import os
import time
import json
import firebase_admin
from firebase_admin import credentials, firestore

class AuthManager:
    def __init__(self):
        self.sender_email = os.getenv("SENDER_EMAIL")
        self.sender_password = os.getenv("SENDER_PASSWORD")
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", 587))
        
        # Parse list of allowed admin emails
        admin_emails_str = os.getenv("ADMIN_EMAILS", "")
        self.admin_emails = [e.strip() for e in admin_emails_str.split(",") if e.strip()]
        
        # Initialize Firebase
        if not firebase_admin._apps:
            cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
            if cred_path and os.path.exists(cred_path):
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
            else:
                cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
                if cred_json:
                    cred_dict = json.loads(cred_json)
                    cred = credentials.Certificate(cred_dict)
                    firebase_admin.initialize_app(cred)
                else:
                    firebase_admin.initialize_app()
        
        self.db = firestore.client()

    def generate_otp(self):
        return ''.join(random.choices(string.digits, k=6))

    def _send_email(self, to_email, subject, body):
        """Helper to send emails robustly using SSL or TLS based on configuration."""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            # Logic to handle different ports
            if self.smtp_port == 465:
                # Use SSL directly (Preferred for Production/Render)
                server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
            else:
                # Use standard TLS
                server = smtplib.SMTP(self.smtp_server, self.smtp_port)
                server.starttls()

            server.login(self.sender_email, self.sender_password)
            server.send_message(msg)
            server.quit()
            return True, None
        except Exception as e:
            print(f"Email Error: {e}")
            return False, str(e)

    def send_otp(self, user_telegram_id, email):
        if not email.endswith("@iiitdwd.ac.in"):
            return False, "❌ Please use your official college email (@iiitdwd.ac.in)"

        otp = self.generate_otp()
        
        try:
            doc_ref = self.db.collection('otp_requests').document(str(user_telegram_id))
            doc_ref.set({
                'otp': otp,
                'email': email,
                'timestamp': time.time()
            })

            subject = "Campus Saathi Verification Code"
            body = f"Your verification code for Campus Saathi is: {otp}\n\nThis code expires in 10 minutes."
            
            success, error = self._send_email(email, subject, body)
            
            if success:
                return True, "✅ OTP sent to your email. Please enter it here."
            else:
                return False, f"❌ Failed to send email: {error}"

        except Exception as e:
            print(f"Auth Error: {e}")
            return False, "❌ Failed to process request."

    def verify_otp(self, user_telegram_id, code):
        doc_ref = self.db.collection('otp_requests').document(str(user_telegram_id))
        doc = doc_ref.get()
        
        if not doc.exists:
            return False, "❌ No OTP request found. Use /start again."

        record = doc.to_dict()

        if time.time() - record['timestamp'] > 600:
            doc_ref.delete()
            return False, "❌ OTP expired. Please request a new one."

        if record['otp'] == code.strip():
            role = 'admin' if record.get('is_admin_request') else 'student'
            user_ref = self.db.collection('users').document(str(user_telegram_id))
            user_ref.set({
                'email': record['email'],
                'verified_at': time.time(),
                'role': role
            })
            doc_ref.delete()
            return True, f"✅ Verification Successful! Access granted as {role}."
        
        return False, "❌ Invalid OTP. Please try again."

    def is_verified(self, user_telegram_id):
        doc = self.db.collection('users').document(str(user_telegram_id)).get()
        return doc.exists

    def verify_admin(self, user_telegram_id, email):
        if email not in self.admin_emails:
            return False, "❌ You are not authorized as an Admin (Email not in whitelist)."
        
        otp = self.generate_otp()
        try:
            doc_ref = self.db.collection('otp_requests').document(str(user_telegram_id))
            doc_ref.set({
                'otp': otp,
                'email': email,
                'timestamp': time.time(),
                'is_admin_request': True
            })

            subject = "Campus Saathi Admin Verification"
            body = f"Admin Verification Code: {otp}"

            success, error = self._send_email(email, subject, body)

            if success:
                return True, "✅ Admin OTP sent."
            else:
                return False, f"❌ Email failed: {error}"
        except Exception as e:
            return False, f"❌ Error: {e}"
