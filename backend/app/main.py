from fastapi import FastAPI

from app.assistant.router import router as assistant_router
from app.auth.router import router as auth_router
from app.briefs.router import router as briefs_router
from app.checkins.router import router as checkins_router
from app.copilot.router import router as copilot_router
from app.documents.router import router as documents_router
from app.patients.router import router as patients_router
from app.timeline.router import router as timeline_router

app = FastAPI(title="Scaffold Health API")

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
