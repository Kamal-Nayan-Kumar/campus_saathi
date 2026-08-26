import os
import tempfile
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from backend.pdf_processor import PDFProcessor
from backend.vector_store import KnowledgeBase

pdf_processor = None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ Campus Saathi Admin Bot\nSend me a PDF to add it to the knowledge base."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please upload a PDF file.")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            pdf_processor = PDFProcessor(knowledge_base=KnowledgeBase())

        try:
            with open(tmp_path, "rb") as f:
                chunks = pdf_processor.process_and_ingest(f.read(), document.file_name)
            await status_msg.edit_text(
                f"✅ Added '{document.file_name}' to the knowledge base "
                f"({chunks} chunks)!"
            )
        finally:
            os.remove(tmp_path)

    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")


async def handle_non_pdf_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Only PDF files are supported. Please upload a PDF.")


def init_admin_app():
    """Initializes and returns the Admin Bot Application."""

    token = os.getenv("TELEGRAM_ADMIN_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_ADMIN_BOT_TOKEN missing")

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Document.PDF, handle_document))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_non_pdf_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app
