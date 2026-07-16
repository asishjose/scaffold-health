from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.patients.router import router as patients_router

app = FastAPI(title="Scaffold Health API")

app.include_router(auth_router)
app.include_router(patients_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
