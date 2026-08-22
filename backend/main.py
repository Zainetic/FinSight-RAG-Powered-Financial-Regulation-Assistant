"""
FinSight RegTech API Root Entrypoint
Re-exports FastAPI application instance from src.api.main
"""
from src.api.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
