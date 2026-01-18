import os
import uvicorn
import signal
import sys
import multiprocessing
from dotenv import load_dotenv
from student_bot import run_student_bot
from app import app

load_dotenv()

bot_process = None

def signal_handler(sig, frame):
    print(f"\n🛑 Received signal {sig}. Shutting down Student Bot...")
    if bot_process and bot_process.is_alive():
        bot_process.terminate()
        bot_process.join()
    sys.exit(0)

if __name__ == "__main__":
    print("🎓 Starting Student Bot Service...")
    
    # Handle shutdown signals
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start Student Bot
    bot_process = multiprocessing.Process(target=run_student_bot)
    bot_process.start()
    
    # Start Keep-Alive Web Server
    port = int(os.getenv("PORT", 8000))
    print(f"🌍 Web Server running on port {port}")
    
    try:
        uvicorn.run(app, host="0.0.0.0", port=port)
    finally:
        if bot_process and bot_process.is_alive():
            bot_process.terminate()
