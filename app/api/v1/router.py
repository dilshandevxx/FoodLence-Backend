from fastapi import APIRouter
from app.api.v1.endpoints import analyze, auth, profiles, history, ingredients

api_router = APIRouter()

# Core Module Endpoints
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication & User Accounts"])
api_router.include_router(profiles.router, prefix="/profiles", tags=["Dietary Profiles"])
api_router.include_router(analyze.router, prefix="/analyze", tags=["Inference & Analysis"])
api_router.include_router(history.router, prefix="/history", tags=["Scan History"])
api_router.include_router(ingredients.router, prefix="/knowledge", tags=["Knowledge Base & Ingredients"])

# Allergen taxonomy shortcut for Flutter Profile Editor
api_router.add_api_route(
    "/allergens",
    ingredients.get_supported_allergens,
    methods=["GET"],
    tags=["Knowledge Base & Ingredients"],
    summary="Get standard allergen list for profile configuration",
)


@api_router.get("/status", tags=["Status"])
def api_status():
    return {
        "status": "active",
        "api_version": "v1",
        "endpoints": [
            "/api/v1/auth",
            "/api/v1/profiles",
            "/api/v1/analyze",
            "/api/v1/history",
            "/api/v1/knowledge",
            "/api/v1/allergens",
        ],
    }
