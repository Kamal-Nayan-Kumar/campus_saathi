import { config } from "dotenv";
import { resolve } from "path";

config({ path: resolve(process.cwd(), ".env") });
config({ path: resolve(process.cwd(), ".env.local") });

async function main() {
  const webhookUrl = process.env.WEBHOOK_URL;
  if (!webhookUrl) {
    console.error("❌ WEBHOOK_URL not found in environment.");
    process.exit(1);
  }

  console.log(`🔗 Setting Webhooks to base: ${webhookUrl}`);

  await setTelegramWebhook(
    process.env.TELEGRAM_STUDENT_BOT_TOKEN,
    "student-webhook",
    webhookUrl
  );
  await setTelegramWebhook(
    process.env.TELEGRAM_ADMIN_BOT_TOKEN,
    "admin-webhook",
    webhookUrl
  );

  console.log("✅ Webhook setup complete.");
}

async function setTelegramWebhook(
  token: string | undefined,
  path: string,
  baseUrl: string
) {
  if (!token) {
    console.warn(`⚠️ No token for ${path} webhook, skipping.`);
    return;
  }

  const url = `${baseUrl}/api/${path}`;
  const res = await fetch(
    `https://api.telegram.org/bot${token}/setWebhook`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    }
  );

  const data = await res.json();
  if (data.ok) {
    console.log(`✅ Webhook set: ${url}`);
  } else {
    console.error(
      `❌ Failed to set webhook for ${path}:`,
      data.description
    );
  }
}

main().catch(console.error);
