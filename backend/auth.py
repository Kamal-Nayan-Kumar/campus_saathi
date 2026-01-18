import os
import time
import json
import requests
import firebase_admin
from firebase_admin import credentials, firestore, auth

class AuthManager:
    def __init__(self):
        # Firebase Admin Init (for Firestore)
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
        self.web_api_key = os.getenv("FIREBASE_WEB_API_KEY")
        
        # Parse list of allowed admin emails
        admin_emails_str = os.getenv("ADMIN_EMAILS", "")
        self.admin_emails = [e.strip() for e in admin_emails_str.split(",") if e.strip()]

    def send_otp(self, user_telegram_id, email):
        """
        Uses Firebase Auth REST API to send a verification link.
        Google sends the email, bypassing local SMTP blocks.
        """
        if not self.web_api_key:
            return False, "❌ Configuration Error: Missing FIREBASE_WEB_API_KEY."

        # Domain Check
        if not email.endswith("@iiitdwd.ac.in"):
             # Check if it's an admin email attempting to login
            if email not in self.admin_emails:
                return False, "❌ Please use your official college email (@iiitdwd.ac.in)"

        try:
            # 1. Check if user exists in Firebase Auth, if not create them
            try:
                user = auth.get_user_by_email(email)
                uid = user.uid
            except auth.UserNotFoundError:
                user = auth.create_user(email=email, email_verified=False)
                uid = user.uid

            # 2. Store the pending request in Firestore
            doc_ref = self.db.collection('otp_requests').document(str(user_telegram_id))
            doc_ref.set({
                'email': email,
                'uid': uid,
                'timestamp': time.time(),
                'is_admin_request': (email in self.admin_emails)
            })

            # 3. Generate ID Token via Custom Token Exchange
            # This is required because we need to act "as the user" to trigger their verification email
            custom_token = auth.create_custom_token(uid).decode('utf-8')
            
            exchange_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={self.web_api_key}"
            exchange_resp = requests.post(exchange_url, json={"token": custom_token, "returnSecureToken": True})
            
            if not exchange_resp.ok:
                print(f"Token Exchange Error: {exchange_resp.text}")
                return False, "❌ Auth Error: Could not generate token."
                
            id_token = exchange_resp.json()['idToken']
            
            # 4. Trigger verification email
            verify_url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={self.web_api_key}"
            verify_resp = requests.post(verify_url, json={
                "requestType": "VERIFY_EMAIL",
                "idToken": id_token
            })
            
            if verify_resp.ok:
                return True, (
                    "\U0001f4e8 I've asked Google to send a verification link to your email.\n\n"
                    "1. Check your Inbox (and Spam).\n"
                    "2. Click the link to verify.\n"
                    "3. Come back here and type /verify to finish."
                )
            else:
                print(f"Email Send Error: {verify_resp.text}")
                return False, "❌ Failed to trigger email. Please try again."

        except Exception as e:
            print(f"Auth Flow Error: {e}")
            return False, f"❌ Error: {str(e)}"

    def check_verification(self, user_telegram_id):
        """
        Called when user types /verify. Checks if email is verified in Firebase.
        """
        doc_ref = self.db.collection('otp_requests').document(str(user_telegram_id))
        doc = doc_ref.get() 
        
        if not doc.exists:
            return False, "❌ No pending verification found. Send /start."

        record = doc.to_dict()
        uid = record['uid']
        
        # Refresh user data from Firebase Auth
        try:
            user = auth.get_user(uid)
            if user.email_verified:
                # Success!
                role = 'admin' if record.get('is_admin_request') else 'student'
                
                # Store permanently
                self.db.collection('users').document(str(user_telegram_id)).set({
                    'email': record['email'],
                    'verified_at': time.time(),
                    'role': role
                })
                
                doc_ref.delete()
                return True, f"✅ Verification Verified! Access granted as {role}."
            else:
                return False, "⏳ Email not verified yet. Please click the link in your email and try /verify again."
                
        except Exception as e:
            return False, f"❌ Error checking status: {e}"

    # --- Backward Compatibility Methods ---
    def verify_otp(self, user_telegram_id, code):
        return False, "❌ Please use /verify command instead of entering a code."

    def is_verified(self, user_telegram_id):
        doc = self.db.collection('users').document(str(user_telegram_id)).get()
        return doc.exists

    def verify_admin(self, user_telegram_id, email):
        return self.send_otp(user_telegram_id, email)
