import { getStudentBot } from "@/bots/student-bot";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const bot = getStudentBot();
    await bot.handleUpdate(body);
    return Response.json({ status: "ok" });
  } catch (err) {
    console.error("❌ Student Webhook Error:", err);
    return Response.json(
      {
        status: "error",
        detail: err instanceof Error ? err.message : String(err),
      },
      { status: 500 }
    );
  }
}
