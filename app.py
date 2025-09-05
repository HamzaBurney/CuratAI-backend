import logging
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import uvicorn
from routes import images_upload_router
from services.supabase_services import SupabaseService

logging.basicConfig(level=logging.INFO) 
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup"""
    
    try:
        # Initialize Supabase service
        supabase_service = SupabaseService()
        if not supabase_service.test_connection():
            raise Exception("Failed to connect to Supabase")
        logger.info("Supabase service connected successfully")
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise
    
    yield
    
    logger.info("Application shutdown")
        
    
    

app = FastAPI(
    title="CuratAi-Backend",
    description="AI-Backend for CuratAI",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)
    
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False, 
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(images_upload_router)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        reload=True 
    )