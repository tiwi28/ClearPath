from fastapi import APIRouter

from ..mock import load

router = APIRouter(tags=["audit"])


@router.post("/audit")
def audit():
    # Optional add-on. Keep YOLO imports out of the backend path.
    return load("audit.json")
