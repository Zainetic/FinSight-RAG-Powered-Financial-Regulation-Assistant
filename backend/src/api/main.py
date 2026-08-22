from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.core.database import init_db
from src.core.ledger import init_ledger_table
from src.api.routes import router as compliance_router
from src.api.auth import router as auth_router
import re


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Eagerly initialize PostgreSQL audit ledger table and indexes on startup
    try:
        init_db()
        init_ledger_table()
    except Exception as e:
        print(f"[Startup Warning] Database initialization deferred: {e}")
    yield


app = FastAPI(
    title="FinSight RegTech API",
    description="Enterprise Multi-Tenant Regulatory Compliance Gatekeeper with RBAC and SHA-256 Ledger",
    version="2.0.0",
    lifespan=lifespan
)

# Allow local development and any Vercel deployment preview/production domain
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://finsight.vercel.app",
]

# Regex to automatically whitelist any Vercel preview branch for this project
origin_regex = r"https://finsight(-[a-zA-Z0-9-]+)?-zain-130c\.vercel\.app"

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Core Authentication & RegTech Routers
app.include_router(auth_router)
app.include_router(compliance_router)


@app.get("/health", tags=["System Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": "FinSight RegTech Engine",
        "version": "2.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host="0.0.0.0", port=8000, reload=True)

