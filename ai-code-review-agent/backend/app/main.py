from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .api import router as api_router

app = FastAPI(title="AI Code and Security Review API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api")


@app.get("/")
@app.get("/api")
def read_root():
    return {"message": "Welcome to the AI Code Review & Security Analysis Agent API!"}