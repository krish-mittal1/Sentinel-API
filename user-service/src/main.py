import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routes.users import router as users_router
from .middleware.exceptions import AppException, app_exception_handler

app = FastAPI(
    title="Sentinel User Service",
    description="Handles CRUD operations for users.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(AppException, app_exception_handler)

app.include_router(users_router)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "user-service"}

if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.USER_SERVICE_PORT,
        reload=True,
    )
