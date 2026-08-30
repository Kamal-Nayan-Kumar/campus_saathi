from dotenv import load_dotenv
load_dotenv()

import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from telegram import Update

from student_bot import init_student_app
from admin_bot import init_admin_app
from backend.api import mount_portals, router as api_router

WEBHOOK_URL = os.getenv("WEBHOOK_URL")
student_app = None
admin_app = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global student_app, admin_app
    print("🚀 Initializing Bots...")
    try:
        student_app = init_student_app()
    except Exception as e:
        print(f"⚠️ Student bot not started: {e}")
        student_app = None
    try:
        admin_app = init_admin_app()
    except Exception as e:
        print(f"⚠️ Admin bot not started: {e}")
        admin_app = None

    if student_app:
        await student_app.initialize()
        await student_app.start()
    if admin_app:
        await admin_app.initialize()
        await admin_app.start()

    if WEBHOOK_URL and student_app and admin_app:
        print(f"🔗 Setting Webhooks to base: {WEBHOOK_URL}")
        try:
            s_url = f"{WEBHOOK_URL}/student-webhook"
            await student_app.bot.set_webhook(url=s_url)
            print(f"✅ Student Webhook set: {s_url}")
            a_url = f"{WEBHOOK_URL}/admin-webhook"
            await admin_app.bot.set_webhook(url=a_url)
            print(f"✅ Admin Webhook set: {a_url}")
        except Exception as e:
            print(f"⚠️ Webhook setup failed: {e}")
    elif student_app or admin_app:
        print("⚠️ WEBHOOK_URL not found — starting polling for local dev (Ctrl+C to stop)")
        try:
            if student_app and student_app.updater:
                await student_app.updater.start_polling(drop_pending_updates=True)
                print("✅ Student bot polling started (@CampusSaathi_Bot)")
            if admin_app and admin_app.updater:
                await admin_app.updater.start_polling(drop_pending_updates=True)
                print("✅ Admin bot polling started (@CampusSaathiAdmin_Bot)")
        except Exception as e:
            print(f"Polling start failed: {e}")

    yield

    print("🛑 Shutting down bots...")
    try:
        if student_app:
            if student_app.updater and student_app.updater.running:
                await student_app.updater.stop()
            await student_app.stop()
            await student_app.shutdown()
        if admin_app:
            if admin_app.updater and admin_app.updater.running:
                await admin_app.updater.stop()
            await admin_app.stop()
            await admin_app.shutdown()
    except Exception as e:
        print(f"Shutdown note: {e}")

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
    if not student_app:
        return {"status": "ok", "note": "student bot not configured"}
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
    if not admin_app:
        return {"status": "ok", "note": "admin bot not configured"}
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
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
