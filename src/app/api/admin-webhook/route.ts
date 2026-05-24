import { getAdminBot } from "@/bots/admin-bot";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const bot = getAdminBot();
    await bot.handleUpdate(body);
    return Response.json({ status: "ok" });
  } catch (err) {
    console.error("❌ Admin Webhook Error:", err);
    return Response.json(
      {
        status: "error",
        detail: err instanceof Error ? err.message : String(err),
      },
      { status: 500 }
    );
  }
}
