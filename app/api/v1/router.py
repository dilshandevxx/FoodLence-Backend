from fastapi import APIRouter
from app.api.v1.endpoints import analyze

api_router = APIRouter()

# Mount endpoints
api_router.include_router(analyze.router, prefix="/analyze", tags=["Inference & Analysis"])


@api_router.get("/status", tags=["Status"])
async def api_status():
    return {
        "status": "active",
        "api_version": "v1",
        "endpoints": [
            "/analyze",
            "/auth",
            "/profiles",
            "/ingredients",
            "/history",
        ],
    }
