import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from backend.query_engine import QueryEngine

query_engine = None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Campus Saathi! Ask me anything about campus — "
        "in any language you like."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    status_msg = await update.message.reply_text("Thinking... 🤖")

    try:
        global query_engine
        if not query_engine:
            from backend.vector_store import KnowledgeBase
            query_engine = QueryEngine(knowledge_base=KnowledgeBase())

        answer = query_engine.process_query(text)
        await status_msg.edit_text(answer)
    except Exception as e:
        print(f"Error: {e}")
        await status_msg.edit_text("Sorry, I encountered an error processing your request.")


def init_student_app():
    """Initializes and returns the Student Bot Application."""

    token = os.getenv("TELEGRAM_STUDENT_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_STUDENT_BOT_TOKEN missing")

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app
