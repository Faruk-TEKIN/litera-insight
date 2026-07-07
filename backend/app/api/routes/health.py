from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.services.ollama_service import get_ollama_service


router = APIRouter()


@router.get("/health")
def health_check():
    return {"status": "ok"}


@router.get("/health/ready")
def readiness_check(db: Session = Depends(get_db)):
    checks = {
        "database": False,
        "ollama": False,
        "ollama_model": False,
    }

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "checks": checks},
        )

    ollama = get_ollama_service()
    checks["ollama_model"] = ollama.is_model_ready()
    checks["ollama"] = checks["ollama_model"]

    if all(checks.values()):
        return JSONResponse(
            status_code=200,
            content={"status": "ready", "checks": checks},
        )

    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "checks": checks},
    )
