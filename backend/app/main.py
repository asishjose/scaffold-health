from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.briefs.router import router as briefs_router
from app.checkins.router import router as checkins_router
from app.documents.router import router as documents_router
from app.patients.router import router as patients_router

app = FastAPI(title="Scaffold Health API")

app.include_router(auth_router)
app.include_router(patients_router)
app.include_router(documents_router)
app.include_router(checkins_router)
app.include_router(briefs_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
