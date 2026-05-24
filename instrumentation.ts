export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;

  const { config } = await import("dotenv");
  config();

  const webhookUrl = process.env.WEBHOOK_URL;
  if (!webhookUrl) {
    console.warn("⚠️ WEBHOOK_URL not found. Webhooks will not be set.");
    return;
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
