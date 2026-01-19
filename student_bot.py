import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from backend.auth import AuthManager
from backend.query_engine import QueryEngine

auth_manager = AuthManager()
query_engine = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if auth_manager.is_verified(user_id):
        await update.message.reply_text("👋 Welcome back! How can I help you today?")
    else:
        await update.message.reply_text(
            "👋 Welcome to Campus Saathi!\n\n"
            "To verify your identity, please enter your official college email address (@iiitdwd.ac.in)."
        )
        context.user_data['awaiting_email'] = True

async def verify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    success, msg = auth_manager.check_verification(user_id)
    await update.message.reply_text(msg)
    if success:
        context.user_data['awaiting_email'] = False
        await update.message.reply_text("🎓 You can now ask questions!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Flow 1: Verification
    if not auth_manager.is_verified(user_id):
        if context.user_data.get('awaiting_email'):
            success, msg = auth_manager.send_otp(user_id, text)
            await update.message.reply_text(msg)
            return

        await update.message.reply_text("🔒 Please verify your email first. Send /start to begin.")
        return

    # Flow 2: Q&A
    status_msg = await update.message.reply_text("Thinking... 🤖")
    
    try:
        global query_engine
        if not query_engine:
            query_engine = QueryEngine()
            
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
    app.add_handler(CommandHandler("verify", verify_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    return app
