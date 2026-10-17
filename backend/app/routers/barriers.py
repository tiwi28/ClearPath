from fastapi import APIRouter

from ..mock import load

router = APIRouter(tags=["barriers"])


@router.get("/barriers")
def list_barriers(bbox: str | None = None, kind: str | None = None):
    # TODO: query Postgres (ST_Intersects on bbox), filter by kind.
    return load("barriers.json")
