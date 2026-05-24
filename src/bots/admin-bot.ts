import { Bot, session, Context } from "grammy";
import { SessionData } from "@/types";
import { isVerified, sendOTP, checkVerification } from "@/lib/auth";
import { PDFProcessor } from "@/lib/pdf-processor";

type BotContext = Context & { session: SessionData };

let botInstance: Bot<BotContext> | null = null;
let pdfProcessor: PDFProcessor | null = null;

function createBot(): Bot<BotContext> {
  const token = process.env.TELEGRAM_ADMIN_BOT_TOKEN;
  if (!token) {
    throw new Error("TELEGRAM_ADMIN_BOT_TOKEN missing");
  }

  const bot = new Bot<BotContext>(token);

  bot.use(
    session({
      initial: (): SessionData => ({ awaitingEmail: false }),
    })
  );

  bot.command("start", async (ctx) => {
    const userId = ctx.from!.id;
    if (await isVerified(userId)) {
      await ctx.reply("🛡️ Welcome back Admin!");
      return;
    }
    await ctx.reply(
      "🛡️ Campus Saathi Admin Panel\n\n" +
        "Please enter your Authorized Admin Email to begin verification."
    );
    ctx.session.awaitingEmail = true;
  });

  bot.command("verify", async (ctx) => {
    const userId = ctx.from!.id;
    const [success, msg] = await checkVerification(userId);
    await ctx.reply(msg);
    if (success) {
      ctx.session.awaitingEmail = false;
      await ctx.reply("📂 You can now upload PDF documents.");
    }
  });

  bot.on("message:text", async (ctx) => {
    const userId = ctx.from!.id;
    const text = ctx.message.text.trim();

    if (!(await isVerified(userId))) {
      if (ctx.session.awaitingEmail) {
        const [, msg] = await sendOTP(userId, text);
        await ctx.reply(msg);
        return;
      }
      await ctx.reply(
        "🔒 Please verify your email first. Send /start to begin."
      );
      return;
    }

    await ctx.reply("Please upload a PDF file.");
  });

  bot.on(":document", async (ctx) => {
    const userId = ctx.from!.id;
    if (!(await isVerified(userId))) {
      await ctx.reply("🔒 Unauthorized.");
      return;
    }

    const msg = ctx.message;
    if (!msg) return;

    const doc = msg.document;
    if (!doc || doc.mime_type !== "application/pdf") {
      await ctx.reply("❌ Only PDF files are supported. Please upload a PDF.");
      return;
    }

    const statusMsg = await ctx.reply(
      "📥 Processing PDF... (This may take a minute)"
    );

    try {
      const file = await ctx.api.getFile(doc.file_id);
      const token = process.env.TELEGRAM_ADMIN_BOT_TOKEN;
      const fileUrl = `https://api.telegram.org/file/bot${token}/${file.file_path}`;

      const response = await fetch(fileUrl);
      const pdfBuffer = Buffer.from(await response.arrayBuffer());

      if (!pdfProcessor) {
        pdfProcessor = new PDFProcessor();
      }

      await pdfProcessor.processAndIngest(
        pdfBuffer,
        doc.file_name || "document.pdf"
      );
      await ctx.api.editMessageText(
        statusMsg.chat.id,
        statusMsg.message_id,
        `✅ Added '${doc.file_name}' to knowledge base!`
      );
    } catch (err) {
      console.error("PDF Processing Error:", err);
      const message = err instanceof Error ? err.message : String(err);
      await ctx.api.editMessageText(
        statusMsg.chat.id,
        statusMsg.message_id,
        `❌ Error: ${message}`
      );
    }
  });

  return bot;
}

export function getAdminBot(): Bot<BotContext> {
  if (!botInstance) {
    botInstance = createBot();
  }
  return botInstance;
}
