from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from src.core.limiter import limiter
from src.core.database import init_db
from src.core.ledger import init_ledger_table
from src.api.routes import router as compliance_router
from src.api.auth import router as auth_router
from src.api.transactions import router as transactions_router


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

# 1. Register SlowAPI Rate Limiter State & Exception Handler (Rules 11 & 12)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 2. Strict Security Headers Middleware (Rule 18)
@app.middleware("http")
async def add_security_headers_middleware(request: Request, call_next):
    response: Response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response

# 3. Handle Render / Reverse Proxy HTTPS Headers
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# 4. CORS Configuration with Credential & HttpOnly Cookie Support (Rule 9)
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://finsight.vercel.app",
]

origin_regex = r"https://.*\.vercel\.app"

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
    expose_headers=["Strict-Transport-Security", "X-Content-Type-Options", "X-Frame-Options"],
)

# Include Core Authentication, RegTech & Transaction Gatekeeper Routers
app.include_router(auth_router)
app.include_router(compliance_router)
app.include_router(transactions_router)



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