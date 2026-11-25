from contextlib import asynccontextmanager
import os
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .database import Base, SessionLocal, engine
from .migrations import backfill_saved_snapshots, migrate_schema
from .routers.api import router
from .routers.admin_auth import router as admin_auth_router
from .routers.management import router as management_router
from .seed import seed_fall_data
from .services.saved_schedules import revalidate_saved_schedules


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    migrate_schema(engine)
    with SessionLocal() as db:
        seed_fall_data(db)
        backfill_saved_snapshots(db)
        revalidate_saved_schedules(db)
        db.commit()
    yield


app = FastAPI(title="UniSchedule API", version="0.1.0", lifespan=lifespan)
allowed_origins = {item.strip().rstrip("/") for item in os.getenv("UNISCHEDULE_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://127.0.0.1:8000").split(",") if item.strip()}


@app.middleware("http")
async def reject_cross_origin_writes(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        source = origin or (f"{urlsplit(referer).scheme}://{urlsplit(referer).netloc}" if referer else None)
        if source and source.rstrip("/") not in allowed_origins:
            return JSONResponse({"detail": "Cross-origin write rejected."}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-site write rejected."}, status_code=403)
    return await call_next(request)


app.add_middleware(CORSMiddleware, allow_origins=list(allowed_origins), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(management_router)
app.include_router(admin_auth_router)
