import multiprocessing
import os
import uvicorn
from dotenv import load_dotenv
from student_bot import run_student_bot
from admin_bot import run_admin_bot
from app import app  # Import the FastAPI app

load_dotenv()

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

if __name__ == "__main__":
    print("🚀 Starting Campus Saathi System...")

    # 1. Start Bots in separate processes
    p1 = multiprocessing.Process(target=start_student)
    p2 = multiprocessing.Process(target=start_admin)
    
    p1.start()
    p2.start()
    
    # 2. Start Web Server (This keeps Render happy by listening on a port)
    # Render assigns a PORT env var, default to 8000 if missing
    port = int(os.getenv("PORT", 8000))
    print(f"🌍 Web Server starting on port {port}...")
    
    try:
        # Run uvicorn in the main thread
        uvicorn.run(app, host="0.0.0.0", port=port)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
    finally:
        # Ensure bots are killed when web server stops
        p1.terminate()
        p2.terminate()
        p1.join()
        p2.join()
        print("✅ System Shutdown Complete.")