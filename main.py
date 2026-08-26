from dotenv import load_dotenv
load_dotenv()

import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from telegram import Update

# Import Bot Initializers
from student_bot import init_student_app
from admin_bot import init_admin_app
from backend.api import mount_portals, router as api_router

# --- Config ---
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g., https://campus-saathi.onrender.com
STUDENT_TOKEN = os.getenv("TELEGRAM_STUDENT_BOT_TOKEN")
ADMIN_TOKEN = os.getenv("TELEGRAM_ADMIN_BOT_TOKEN")

# Global Apps
student_app = None
admin_app = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle manager: 
    1. Init bots
    2. Set Webhooks
    3. Run startup tasks
    4. Clean up on shutdown
    """
    global student_app, admin_app
    
    print("🚀 Initializing Bots...")
    
    # 1. Initialize
    student_app = init_student_app()
    admin_app = init_admin_app()
    
    # 2. Start Apps
    await student_app.initialize()
    await admin_app.initialize()
    await student_app.start()
    await admin_app.start()
    
    # 3. Set Webhooks
    if WEBHOOK_URL:
        print(f"🔗 Setting Webhooks to base: {WEBHOOK_URL}")
        
        # Student Webhook
        s_url = f"{WEBHOOK_URL}/student-webhook"
        await student_app.bot.set_webhook(url=s_url)
        print(f"✅ Student Webhook set: {s_url}")
        
        # Admin Webhook
        a_url = f"{WEBHOOK_URL}/admin-webhook"
        await admin_app.bot.set_webhook(url=a_url)
        print(f"✅ Admin Webhook set: {a_url}")
    else:
        print("⚠️ WEBHOOK_URL not found. Bots will not receive updates unless polling is manually enabled (which it isn't).")

    yield
    
    # 4. Shutdown
    print("🛑 Shutting down bots...")
    await student_app.stop()
    await admin_app.stop()
    await student_app.shutdown()
    await admin_app.shutdown()

# --- FastAPI App ---
app = FastAPI(lifespan=lifespan)
app.include_router(api_router)
mount_portals(app)

@app.get("/")
def read_root():
    return {"status": "ok", "service": "Campus Saathi Webhook Server"}

@app.get("/health")
@app.head("/health")
def health_check():
    return {"status": "healthy"}

@app.post("/student-webhook")
async def student_webhook(request: Request):
    """Handle incoming updates for Student Bot"""
    try:
        data = await request.json()
        update = Update.de_json(data, student_app.bot)
        if update is None:
            return {"status": "ok"}
        await student_app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        print(f"❌ Student Webhook Error: {e}")
        return {"status": "error", "detail": str(e)}

@app.post("/admin-webhook")
async def admin_webhook(request: Request):
    """Handle incoming updates for Admin Bot"""
    try:
        data = await request.json()
        update = Update.de_json(data, admin_app.bot)
        if update is None:
            return {"status": "ok"}
        await admin_app.process_update(update)
        return {"status": "ok"}
    except Exception as e:
        print(f"❌ Admin Webhook Error: {e}")
        return {"status": "error", "detail": str(e)}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    # Note: On Render, 'uvicorn' command in Procfile is preferred, but this allows python main.py too
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)