import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import settings
from app.db.session import engine
from app.nlp.model_loader import model_loader
from app.api.v1.router import api_router

logger = logging.getLogger("foodlence")
logging.basicConfig(
    level=logging.INFO if settings.DEBUG else logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager that performs zero-cold-start pre-warming
    for NLP models and initializes database connection pooling.
    """
    logger.info("Initializing %s in %s mode...", settings.PROJECT_NAME, settings.ENVIRONMENT)

    # 1. Zero Cold-Start NLP & ML Pipeline Warmup
    model_loader.load_nlp_pipeline()
    model_loader.load_serialized_models()
    model_loader.warmup()

    # 2. Database Connection Pool Healthcheck (non-blocking if database is warming up)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection pool established successfully (Pool size: %d, Max overflow: %d)",
                    settings.DB_POOL_SIZE, settings.DB_MAX_OVERFLOW)
    except Exception as exc:
        logger.warning("Database connection pool could not reach DB server at startup: %s. Requests requiring DB will retry on demand.", exc)

    yield

    # Shutdown: Cleanly dispose of connection pools and memory-mapped model weights
    logger.info("Disposing database connection pool...")
    engine.dispose()
    logger.info("Application shutdown complete.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="AI-Powered Food Ingredient & Allergen Detection Engine",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# CORS Configuration
if settings.BACKEND_CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.BACKEND_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Mount API V1 Router
app.include_router(api_router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Health"])
async def root():
    return {
        "project": settings.PROJECT_NAME,
        "status": "online",
        "docs_url": "/docs",
        "model_warmed_up": model_loader.is_warmed_up,
    }


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "database_pool": {
            "size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
        },
        "model_loader": {
            "warmed_up": model_loader.is_warmed_up,
            "nlp_loaded": model_loader.nlp is not None,
        },
    }
