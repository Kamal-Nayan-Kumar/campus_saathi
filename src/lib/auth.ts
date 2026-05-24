import admin from "firebase-admin";
import { OTPRecord } from "@/types";

let db: admin.firestore.Firestore;
let webApiKey: string;
let adminEmails: string[];

function initFirebase() {
  if (admin.apps.length) return;

  const projectId = process.env.FIREBASE_PROJECT_ID?.trim().replace(/^["']|["']$/g, "");
  const privateKey = process.env.FIREBASE_PRIVATE_KEY?.trim().replace(/^["']|["']$/g, "");
  const clientEmail = process.env.FIREBASE_CLIENT_EMAIL?.trim().replace(/^["']|["']$/g, "");

  if (!projectId || !privateKey || !clientEmail) {
    throw new Error(
      "Missing Firebase credentials. Please configure FIREBASE_PROJECT_ID, " +
        "FIREBASE_PRIVATE_KEY, and FIREBASE_CLIENT_EMAIL in your environment."
    );
  }

  const formattedPrivateKey = privateKey.replace(/\\n/g, "\n");

  const credDict: Record<string, string> = {
    type: "service_account",
    project_id: projectId,
    private_key: formattedPrivateKey,
    client_email: clientEmail,
    token_uri: "https://oauth2.googleapis.com/token",
  };

  if (process.env.FIREBASE_PRIVATE_KEY_ID) {
    credDict.private_key_id = process.env.FIREBASE_PRIVATE_KEY_ID;
  }
  if (process.env.FIREBASE_CLIENT_ID) {
    credDict.client_id = process.env.FIREBASE_CLIENT_ID;
  }

  admin.initializeApp({
    credential: admin.credential.cert(credDict as admin.ServiceAccount),
  });

  db = admin.firestore();
  webApiKey = process.env.FIREBASE_WEB_API_KEY || "";

  const adminEmailsStr = process.env.ADMIN_EMAILS || "";
  adminEmails = adminEmailsStr
    .split(",")
    .map((e) => e.trim())
    .filter(Boolean);
}

function ensureInit() {
  if (!db) initFirebase();
}

export async function sendOTP(
  userTelegramId: number,
  email: string
): Promise<[boolean, string]> {
  ensureInit();

  if (!email.endsWith("@iiitdwd.ac.in")) {
    if (!adminEmails.includes(email)) {
      return [false, "❌ Please use your official college email (@iiitdwd.ac.in)"];
    }
  }

  if (!webApiKey) {
    return [false, "❌ Configuration Error: Missing FIREBASE_WEB_API_KEY."];
  }

  try {
    let uid: string;
    try {
      const user = await admin.auth().getUserByEmail(email);
      uid = user.uid;
    } catch (err: unknown) {
      const firebaseErr = err as { code?: string };
      if (firebaseErr.code === "auth/user-not-found") {
        const user = await admin.auth().createUser({
          email,
          emailVerified: false,
        });
        uid = user.uid;
      } else {
        throw err;
      }
    }

    await db.collection("otp_requests").doc(String(userTelegramId)).set({
      email,
      uid,
      timestamp: Date.now() / 1000,
      is_admin_request: adminEmails.includes(email),
    } satisfies OTPRecord);

    const customToken = await admin.auth().createCustomToken(uid);

    const exchangeRes = await fetch(
      `https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=${webApiKey}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token: customToken,
          returnSecureToken: true,
        }),
      }
    );

    if (!exchangeRes.ok) {
      console.error("Token Exchange Error:", await exchangeRes.text());
      return [false, "❌ Auth Error: Could not generate token."];
    }

    const { idToken } = await exchangeRes.json();

    const verifyRes = await fetch(
      `https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key=${webApiKey}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          requestType: "VERIFY_EMAIL",
          idToken,
        }),
      }
    );

    if (verifyRes.ok) {
      return [
        true,
        "📨 I've asked Google to send a verification link to your email.\n\n" +
          "1. Check your Inbox (and Spam).\n" +
          "2. Click the link to verify.\n" +
          "3. Come back here and type /verify to finish.",
      ];
    } else {
      console.error("Email Send Error:", await verifyRes.text());
      return [false, "❌ Failed to trigger email. Please try again."];
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("Auth Flow Error:", err);
    return [false, `❌ Error: ${message}`];
  }
}

export async function checkVerification(
  userTelegramId: number
): Promise<[boolean, string]> {
  ensureInit();

  const docRef = db.collection("otp_requests").doc(String(userTelegramId));
  const doc = await docRef.get();

  if (!doc.exists) {
    return [false, "❌ No pending verification found. Send /start."];
  }

  const record = doc.data() as OTPRecord;
  const uid = record.uid;

  try {
    const user = await admin.auth().getUser(uid);

    if (user.emailVerified) {
      const role = record.is_admin_request ? "admin" : "student";

      await db.collection("users").doc(String(userTelegramId)).set({
        email: record.email,
        verified_at: Date.now() / 1000,
        role,
      });

      await docRef.delete();
      return [true, `✅ Verification Verified! Access granted as ${role}.`];
    } else {
      return [
        false,
        "⏳ Email not verified yet. Please click the link in your email and try /verify again.",
      ];
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    return [false, `❌ Error checking status: ${message}`];
  }
}

export async function isVerified(userTelegramId: number): Promise<boolean> {
  ensureInit();
  const doc = await db.collection("users").doc(String(userTelegramId)).get();
  return doc.exists;
}

export async function verifyAdmin(
  userTelegramId: number,
  email: string
): Promise<[boolean, string]> {
  return sendOTP(userTelegramId, email);
}
