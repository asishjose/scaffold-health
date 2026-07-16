from fastapi import FastAPI

app = FastAPI(title="Scaffold Health API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
