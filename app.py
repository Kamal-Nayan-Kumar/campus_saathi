from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
from dotenv import load_dotenv
import os

load_dotenv()

from backend.admin_routes import router as admin_router
from backend.student_routes import router as student_router

app = FastAPI(title="Campus Saathi")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(admin_router, prefix="/admin", tags=["admin"])
app.include_router(student_router, prefix="/student", tags=["student"])

# Create necessary directories
os.makedirs("uploads", exist_ok=True)
os.makedirs("chroma_db", exist_ok=True)

@app.get("/")
def read_root():
    return FileResponse("frontend/admin.html")

@app.get("/student")
def read_student():
    return FileResponse("frontend/student.html")

# Add a test endpoint to verify admin router is working
@app.get("/admin/test")
def test_admin():
    return {"message": "Admin router is working!"}

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    print(f"\n🚀 Starting server on {host}:{port}")
    print(f"📚 Admin Portal: http://localhost:{port}/")
    print(f"🎓 Student Portal: http://localhost:{port}/student")
    print(f"📖 API Docs: http://localhost:{port}/docs\n")
    uvicorn.run(app, host=host, port=port)
