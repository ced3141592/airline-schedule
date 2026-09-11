from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ScheduleRequest, ScheduleResponse
from app.services import load_or_fetch_schedule

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/schedules", response_model=ScheduleResponse)
def get_schedule(
    payload: ScheduleRequest,
    force_update: bool = Query(False),
) -> ScheduleResponse:
    try:
        return load_or_fetch_schedule(
            origin=payload.origin,
            destination=payload.destination,
            force_update=force_update,
        )
    except ValueError as exc:
        message = str(exc)
        status = 502 if "fetch" in message.lower() or "cloudflare" in message.lower() else 400
        raise HTTPException(status_code=status, detail=message) from exc
