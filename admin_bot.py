import os
import tempfile
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from backend.pdf_processor import PDFProcessor
from backend.vector_store import KnowledgeBase
from backend.website_crawler import WebsiteCrawler

pdf_processor = None
website_crawler = None

ALLOWED_EXTS = (".pdf", ".xlsx", ".xls", ".txt", ".md", ".docx")
ALLOWED_MIME_SUBSTR = ("pdf", "officedocument", "spreadsheet", "excel", "text", "plain", "markdown", "word")

def _is_allowed(filename: str, mime: str) -> bool:
    lower = (filename or "").lower()
    if lower.endswith(ALLOWED_EXTS):
        return True
    mime = (mime or "").lower()
    return any(s in mime for s in ALLOWED_MIME_SUBSTR)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🛡️ *Campus Saathi — Admin Bot*\n\n"
        "I manage the Knowledge Base for the Admin Portal.\n"
        "• Send *PDF, Excel, Word (.docx), TXT or MD* to ingest\n"
        "• Use /crawl to refresh the college website (iiitdwd.ac.in) — recursively crawls up to 20 linked pages, not just homepage\n"
        "• Use /status to see what's ingested\n"
        "\n_Design matches the portal: slate #20372F + marigold #E9A13B_",
        parse_mode="Markdown"
    )

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        kb = KnowledgeBase()
        docs = kb.list_documents()
        if not docs:
            await update.message.reply_text("📭 Knowledge Base is empty — upload a file or run /crawl")
            return
        lines = [f"• {d['filename']} — {d['chunks']} chunks" for d in docs[:20]]
        if len(docs) > 20:
            lines.append(f"+{len(docs)-20} more")
        await update.message.reply_text("📚 *Knowledge Base*\n" + "\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Status error: {e}")

async def crawl_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Ask confirm before crawling
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, crawl 20 pages", callback_data="crawl:20"),
         InlineKeyboardButton("❌ Cancel", callback_data="crawl:cancel")]
    ])
    await update.message.reply_text(
        "🌐 *Refresh college website?*\n"
        "This will DELETE old `website:*` docs and re-crawl https://iiitdwd.ac.in via Firecrawl.\n"
        "• Recursive — discovers linked pages (academics, admissions, etc.), not just homepage\n"
        "• Limit 20 pages, ~30–60s, costs Firecrawl credits\n"
        "Confirm?",
        parse_mode="Markdown", reply_markup=kb
    )

async def handle_crawl_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "crawl:cancel":
        await query.edit_message_text("Cancelled.")
        return
    if query.data.startswith("crawl:"):
        limit = int(query.data.split(":")[1])
        await query.edit_message_text(f"🌐 Crawling iiitdwd.ac.in (limit {limit}) — this may take a minute…")
        try:
            global website_crawler
            if not website_crawler:
                website_crawler = WebsiteCrawler(knowledge_base=KnowledgeBase())
            result = website_crawler.crawl(limit=limit, delete_old=True)
            await query.edit_message_text(
                f"✅ Crawled {result['target']}\n"
                f"• Pages: {result['pages']}\n"
                f"• Chunks: {result['chunks']}\n"
                f"• Deleted old: {result['deleted']}"
            )
        except Exception as e:
            await query.edit_message_text(f"❌ Crawl failed: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please upload a *PDF, Excel, Word (.docx), TXT or MD* file.\nOr use /crawl to refresh the website.", parse_mode="Markdown")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    filename = document.file_name or "document"
    mime = document.mime_type or ""

    if filename.lower().endswith(".doc") and not filename.lower().endswith(".docx"):
        await update.message.reply_text("❌ Old .doc not supported — please save as .docx and retry.")
        return
    if not _is_allowed(filename, mime):
        await update.message.reply_text(
            "❌ Unsupported file.\nAccepted: *PDF, XLSX/XLS, DOCX, TXT, MD*.\n"
            f"You sent: `{filename}` ({mime})", parse_mode="Markdown"
        )
        return

    # Ask for confirmation before ingesting (cost warning)
    size_kb = (document.file_size or 0) / 1024
    context.user_data["pending_doc"] = {
        "file_id": document.file_id,
        "file_name": filename,
        "mime": mime,
    }
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Yes, ingest", callback_data="ingest:yes"),
         InlineKeyboardButton("❌ Cancel", callback_data="ingest:cancel")]
    ])
    await update.message.reply_text(
        f"⚠️ *Confirm ingest?*\n"
        f"File: `{filename}` • {size_kb:.1f} KB\n"
        f"Wrong files waste Firecrawl/Qdrant credits and pollute answers.\n"
        f"Proceed?",
        parse_mode="Markdown", reply_markup=kb
    )

async def handle_ingest_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "ingest:cancel":
        context.user_data.pop("pending_doc", None)
        await query.edit_message_text("Cancelled — file not ingested.")
        return
    if query.data != "ingest:yes":
        return
    pending = context.user_data.pop("pending_doc", None)
    if not pending:
        await query.edit_message_text("❌ No pending file. Please re-upload.")
        return

    await query.edit_message_text(f"📥 Processing `{pending['file_name']}`… (may take a minute)", parse_mode="Markdown")
    try:
        file = await context.bot.get_file(pending["file_id"])
        suffix = os.path.splitext(pending["file_name"])[1] or ".pdf"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            await file.download_to_drive(tmp.name)
            tmp_path = tmp.name

        global pdf_processor
        if not pdf_processor:
            pdf_processor = PDFProcessor(knowledge_base=KnowledgeBase())

        try:
            with open(tmp_path, "rb") as f:
                chunks = pdf_processor.process_and_ingest(f.read(), pending["file_name"])
            # mirror portal success style
            await query.edit_message_text(
                f"✅ Added *{pending['file_name']}* to the Knowledge Base\n"
                f"• {chunks} chunks ingested\n"
                f"Ask students to try the new content!",
                parse_mode="Markdown"
            )
        finally:
            try:
                os.remove(tmp_path)
            except: pass
    except Exception as e:
        await query.edit_message_text(f"❌ Error: {str(e)}")

def init_admin_app():
    token = os.getenv("TELEGRAM_ADMIN_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_ADMIN_BOT_TOKEN missing")
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("crawl", crawl_cmd))
    app.add_handler(CommandHandler("refresh", crawl_cmd))
    app.add_handler(CallbackQueryHandler(handle_crawl_callback, pattern=r"^crawl:"))
    app.add_handler(CallbackQueryHandler(handle_ingest_callback, pattern=r"^ingest:"))
    # Documents: handle allowed types via filter, but we check inside
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app
