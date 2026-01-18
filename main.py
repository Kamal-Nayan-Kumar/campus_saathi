import multiprocessing
import os
import signal
import sys
import uvicorn
from dotenv import load_dotenv
from student_bot import run_student_bot
from admin_bot import run_admin_bot
from app import app

load_dotenv()

# Global process references for signal handling
p1 = None
p2 = None

def start_student():
    """Function to run the student bot."""
    try:
        run_student_bot()
    except Exception as e:
        print(f"Student Bot crashed: {e}")

def start_admin():
    """Function to run the admin bot."""
    try:
        run_admin_bot()
    except Exception as e:
        print(f"Admin Bot crashed: {e}")

def signal_handler(sig, frame):
    """Handle termination signals to clean up subprocesses."""
    print(f"\n🛑 Received signal {sig}. Shutting down bots...")
    if p1 and p1.is_alive():
        p1.terminate()
        p1.join()
    if p2 and p2.is_alive():
        p2.terminate()
        p2.join()
    print("✅ Bots terminated. Exiting.")
    sys.exit(0)

if __name__ == "__main__":
    print("🚀 Starting Campus Saathi System...")

    # Register signal handlers for clean shutdown on Render
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 1. Start Bots in separate processes
    p1 = multiprocessing.Process(target=start_student)
    p2 = multiprocessing.Process(target=start_admin)
    
    p1.start()
    p2.start()
    
    # 2. Start Web Server
    port = int(os.getenv("PORT", 8000))
    print(f"🌍 Web Server starting on port {port}...")
    
    try:
        # Run uvicorn (Web Server)
        uvicorn.run(app, host="0.0.0.0", port=port)
    except Exception as e:
        print(f"Web Server Error: {e}")
    finally:
        # Fallback cleanup
        print("🧹 Performing final cleanup...")
        if p1 and p1.is_alive(): p1.terminate()
        if p2 and p2.is_alive(): p2.terminate()
