from fastapi import APIRouter

api_router = APIRouter()


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
