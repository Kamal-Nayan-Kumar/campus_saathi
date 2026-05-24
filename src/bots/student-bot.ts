import { Bot, session, Context } from "grammy";
import { SessionData } from "@/types";
import { isVerified, sendOTP, checkVerification } from "@/lib/auth";
import { processQuery } from "@/lib/query-engine";

type BotContext = Context & { session: SessionData };

let botInstance: Bot<BotContext> | null = null;

function createBot(): Bot<BotContext> {
  const token = process.env.TELEGRAM_STUDENT_BOT_TOKEN;
  if (!token) {
    throw new Error("TELEGRAM_STUDENT_BOT_TOKEN missing");
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
      await ctx.reply("👋 Welcome back! How can I help you today?");
    } else {
      await ctx.reply(
        "👋 Welcome to Campus Saathi!\n\n" +
          "To verify your identity, please enter your official college email address (@iiitdwd.ac.in)."
      );
      ctx.session.awaitingEmail = true;
    }
  });

  bot.command("verify", async (ctx) => {
    const userId = ctx.from!.id;
    const [success, msg] = await checkVerification(userId);
    await ctx.reply(msg);
    if (success) {
      ctx.session.awaitingEmail = false;
      await ctx.reply("🎓 You can now ask questions!");
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

    const statusMsg = await ctx.reply("Thinking... 🤖");

    try {
      const answer = await processQuery(text);
      await ctx.api.editMessageText(
        statusMsg.chat.id,
        statusMsg.message_id,
        answer
      );
    } catch (err) {
      console.error("Error:", err);
      await ctx.api.editMessageText(
        statusMsg.chat.id,
        statusMsg.message_id,
        "Sorry, I encountered an error processing your request."
      );
    }
  });

  return bot;
}

export function getStudentBot(): Bot<BotContext> {
  if (!botInstance) {
    botInstance = createBot();
  }
  return botInstance;
}
