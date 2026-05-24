export interface TranslationResult {
  translation: string;
  detected_language: string;
}

export interface OTPRecord {
  email: string;
  uid: string;
  timestamp: number;
  is_admin_request: boolean;
}

export interface UserRecord {
  email: string;
  verified_at: number;
  role: "student" | "admin";
}

export interface SessionData {
  awaitingEmail: boolean;
}
