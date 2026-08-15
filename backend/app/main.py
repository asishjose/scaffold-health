from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.assistant.router import router as assistant_router
from app.auth.router import router as auth_router
from app.briefs.router import router as briefs_router
from app.checkins.router import router as checkins_router
from app.copilot.router import router as copilot_router
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.core.request_context import RequestContextMiddleware
from app.documents.router import router as documents_router
from app.patients.router import router as patients_router
from app.timeline.router import router as timeline_router

configure_logging()

app = FastAPI(title="Scaffold Health API")
app.add_middleware(RequestContextMiddleware)
# Added outermost so preflight OPTIONS requests are answered before hitting
# any other middleware or route handler.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_allowed_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(patients_router)
app.include_router(documents_router)
app.include_router(checkins_router)
app.include_router(briefs_router)
app.include_router(timeline_router)
app.include_router(assistant_router)
app.include_router(copilot_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
