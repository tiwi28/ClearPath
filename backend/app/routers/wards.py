from fastapi import APIRouter

from ..mock import load

router = APIRouter(tags=["wards"])


@router.get("/wards/{ward_id}/report")
def ward_report(ward_id: int):
    # TODO: compute stats in SQL, pass {metric,value,source_url} rows to Gemini,
    # then validate every number in the briefing appears in the input.
    data = load("ward_report.json")
    data["ward_id"] = ward_id
    return data
