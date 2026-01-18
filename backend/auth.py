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
        self.admin_email = os.getenv("ADMIN_EMAIL")
        
        # Initialize Firebase
        if not firebase_admin._apps:
            cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")
            if cred_path and os.path.exists(cred_path):
                cred = credentials.Certificate(cred_path)
                firebase_admin.initialize_app(cred)
            else:
                # Try handling JSON content directly from env var (common in Render)
                cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
                if cred_json:
                    cred_dict = json.loads(cred_json)
                    cred = credentials.Certificate(cred_dict)
                    firebase_admin.initialize_app(cred)
                else:
                    # Fallback to default (GOOGLE_APPLICATION_CREDENTIALS)
                    firebase_admin.initialize_app()
        
        self.db = firestore.client()

    def generate_otp(self):
        return ''.join(random.choices(string.digits, k=6))

    def send_otp(self, user_telegram_id, email):
        if not email.endswith("@iiitdwd.ac.in"):
            return False, "❌ Please use your official college email (@iiitdwd.ac.in)"

        otp = self.generate_otp()
        
        try:
            # 1. Store in Firestore
            doc_ref = self.db.collection('otp_requests').document(str(user_telegram_id))
            doc_ref.set({
                'otp': otp,
                'email': email,
                'timestamp': time.time()
            })

            # 2. Send Email
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = email
            msg['Subject'] = "Campus Saathi Verification Code"

            body = f"Your verification code for Campus Saathi is: {otp}\n\nThis code expires in 10 minutes."
            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.sender_email, self.sender_password)
            server.send_message(msg)
            server.quit()

            return True, "✅ OTP sent to your email. Please enter it here."

        except Exception as e:
            print(f"Auth Error: {e}")
            return False, "❌ Failed to process request. Check credentials or try again later."

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
            # Determine role
            role = 'admin' if record.get('is_admin_request') else 'student'
            
            # Store as verified user in Firestore
            user_ref = self.db.collection('users').document(str(user_telegram_id))
            user_ref.set({
                'email': record['email'],
                'verified_at': time.time(),
                'role': role
            })
            
            # Clean up OTP
            doc_ref.delete()
            return True, f"✅ Verification Successful! Access granted as {role}."
        
        return False, "❌ Invalid OTP. Please try again."

    def is_verified(self, user_telegram_id):
        # Check local cache or DB? DB is safer for persistence across restarts
        doc = self.db.collection('users').document(str(user_telegram_id)).get()
        return doc.exists

    def verify_admin(self, user_telegram_id, email):
        if email != self.admin_email:
            return False, "❌ You are not authorized as an Admin."
        
        otp = self.generate_otp()
        try:
            # Store in Firestore
            doc_ref = self.db.collection('otp_requests').document(str(user_telegram_id))
            doc_ref.set({
                'otp': otp,
                'email': email,
                'timestamp': time.time(),
                'is_admin_request': True
            })

            # Send Email
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = email
            msg['Subject'] = "Campus Saathi Admin Verification"

            body = f"Admin Verification Code: {otp}"
            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.sender_email, self.sender_password)
            server.send_message(msg)
            server.quit()

            return True, "✅ Admin OTP sent."
        except Exception as e:
            return False, f"❌ Email failed: {e}"

    def confirm_admin_otp(self, user_telegram_id, code):
        # Separate method or reuse verify_otp? Reuse but check admin flag/store role
        doc_ref = self.db.collection('otp_requests').document(str(user_telegram_id))
        doc = doc_ref.get()
        
        if not doc.exists:
            return False, "❌ No OTP request found."

        record = doc.to_dict()
        
        if record['otp'] == code.strip():
            # Store as admin
            user_ref = self.db.collection('users').document(str(user_telegram_id))
            user_ref.set({
                'email': record['email'],
                'verified_at': time.time(),
                'role': 'admin'
            })
            doc_ref.delete()
            return True, "✅ Admin Verified."
        
        return False, "❌ Invalid OTP."