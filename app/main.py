from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import uvicorn
import logging

from app.api.routes import router
from app.models.database import Base, engine, get_db
from app.utils.logger import setup_logging
from app.config import settings

# Set up logging
setup_logging(log_level="INFO")
logger = logging.getLogger(__name__)

# Create database tables
Base.metadata.create_all(bind=engine)

# Create FastAPI application
app = FastAPI(
    title="Healthcare Voice Assistant API",
    description="AI-powered voice assistant for healthcare administration",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)

# Health check endpoint
@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint to verify API is running"""
    return {
        "status": "healthy",
        "app_name": settings.app_name,
        "version": "1.0.0",
        "database_connected": db is not None
    }

# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info("Starting %s application", settings.app_name)
    logger.info("Database URL: %s", settings.database_url)

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down %s application", settings.app_name)

# Run application if executed directly
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)