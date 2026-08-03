from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import STATIC_DIR

app = FastAPI(title="AIMS")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
