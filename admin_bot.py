import os
import tempfile
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from backend.auth import AuthManager
from backend.pdf_processor import PDFProcessor

auth_manager = AuthManager()
pdf_processor = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if auth_manager.is_verified(user_id):
        await update.message.reply_text("🛡️ Welcome back Admin!")
        return

    await update.message.reply_text(
        "🛡️ Campus Saathi Admin Panel\n\n"
        "Please enter your Authorized Admin Email to begin verification."
    )
    context.user_data['awaiting_email'] = True

async def verify_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    success, msg = auth_manager.check_verification(user_id)
    await update.message.reply_text(msg)
    if success:
        context.user_data['awaiting_email'] = False
        await update.message.reply_text("📂 You can now upload PDF documents.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not auth_manager.is_verified(user_id):
        if context.user_data.get('awaiting_email'):
            success, msg = auth_manager.send_otp(user_id, text)
            await update.message.reply_text(msg)
            return

        await update.message.reply_text("🔒 Please verify your email first. Send /start to begin.")
        return

    await update.message.reply_text("Please upload a PDF file.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not auth_manager.is_verified(user_id):
        await update.message.reply_text("🔒 Unauthorized.")
        return

    document = update.message.document
    if document.mime_type != 'application/pdf':
        await update.message.reply_text("❌ Please upload a PDF file.")
        return

    status_msg = await update.message.reply_text("📥 Processing PDF... (This may take a minute)")
    
    try:
        file = await context.bot.get_file(document.file_id)
        
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            tmp_path = tmp.name

        global pdf_processor
        if not pdf_processor:
            pdf_processor = PDFProcessor()

        pdf_processor.process_and_ingest(tmp_path, document.file_name)
        
        os.remove(tmp_path)
        await status_msg.edit_text(f"✅ Added '{document.file_name}' to knowledge base!")
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")

def init_admin_app():
    """Initializes and returns the Admin Bot Application."""
    token = os.getenv("TELEGRAM_ADMIN_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_ADMIN_BOT_TOKEN missing")

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("verify", verify_command))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    return app
