import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from backend.query_engine import QueryEngine

query_engine = None

# Portal-matching branding
WELCOME = (
    "👋 *Campus Saathi — Your AI Campus Assistant*\n"
    "Ask about campus — in any language.\n"
    "\n"
    "Try:\n"
    "• *What is the fee for 3rd semester?*\n"
    "• *What is in dinner today?*\n"
    "• *When is the next bus from campus?*\n"
    "\n"
    "_Answers come from ingested college documents & iiitdwd.ac.in (via Firecrawl)._"
)

HELP = (
    "💬 *How to use:*\n"
    "Just send your question as text — e.g. `When does the library open?`\n"
    "I detect your language and reply in it.\n"
    "Sources are shown when available.\n"
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Try to send cover/logo if available, else text
    try:
        # cs_logo.png is the portal logo (54px header), cover.png is hero
        for img_path in ["cover.png", "cs_logo.png", "frontend/student/cover.png", "frontend/student/cs_logo.png"]:
            if os.path.exists(img_path):
                with open(img_path, "rb") as f:
                    await update.message.reply_photo(photo=f, caption=WELCOME, parse_mode="Markdown")
                return
    except Exception:
        pass
    await update.message.reply_text(WELCOME, parse_mode="Markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text:
        return
    status_msg = await update.message.reply_text("Thinking… 🤖")

    try:
        global query_engine
        if not query_engine:
            from backend.vector_store import KnowledgeBase
            query_engine = QueryEngine(knowledge_base=KnowledgeBase())

        # Per-user history (last 5 pairs stored in context.user_data)
        history = context.user_data.get("history", [])
        answer, sources = query_engine.process_query(text, history)

        # Save to history
        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": answer})
        # keep last 10 entries (5 pairs)
        context.user_data["history"] = history[-10:]

        # Append sources like portal does
        if sources:
            uniq = list(dict.fromkeys(sources))
            src_line = "\n\n📄 *Source:* " + ", ".join(f"`{s}`" for s in uniq[:3])
            if len(uniq) > 3:
                src_line += f" +{len(uniq)-3} more"
            answer = answer + src_line

        # Telegram limit 4096
        if len(answer) > 4000:
            answer = answer[:4000] + "…"

        await status_msg.edit_text(answer, parse_mode="Markdown")
    except Exception as e:
        print(f"Student bot error: {e}")
        await status_msg.edit_text("Sorry, I encountered an error processing your request. Please try again.")

async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["history"] = []
    await update.message.reply_text("🔄 Conversation cleared.")

def init_student_app():
    token = os.getenv("TELEGRAM_STUDENT_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_STUDENT_BOT_TOKEN missing")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("clear", clear_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app
