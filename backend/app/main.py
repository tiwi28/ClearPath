from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import audit, barriers, routing, wards

app = FastAPI(title="Clearpath Toronto API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(barriers.router)
app.include_router(routing.router)
app.include_router(wards.router)
app.include_router(audit.router)


@app.get("/health")
def health():
    return {"status": "ok"}
