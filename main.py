import multiprocessing
import os
from dotenv import load_dotenv
from student_bot import run_student_bot
from admin_bot import run_admin_bot

load_dotenv()

def start_student():
    run_student_bot()

def start_admin():
    run_admin_bot()

if __name__ == "__main__":
    print("🚀 Starting Campus Saathi Bots...")
    
    p1 = multiprocessing.Process(target=start_student)
    p2 = multiprocessing.Process(target=start_admin)
    
    p1.start()
    p2.start()
    
    try:
        p1.join()
        p2.join()
    except KeyboardInterrupt:
        p1.terminate()
        p2.terminate()
