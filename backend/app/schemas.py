from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class ScheduleRequest(BaseModel):
    origin: str = Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    destination: str = Field(min_length=3, max_length=3, pattern=r"^[A-Za-z]{3}$")
    start_date: date | None = None
    weeks: int = Field(default=4, ge=1, le=8)


class FlightView(BaseModel):
    flight_number: str
    airline: str
    aircraft: str
    departure_local_time: str
    arrival_local_time: str
    scheduled_departure_time: datetime
    scheduled_arrival_time: datetime


class ScheduleCell(BaseModel):
    date: date
    weekday: str
    in_range: bool
    flights: list[FlightView]


class ScheduleRow(BaseModel):
    weekday: str
    cells: list[ScheduleCell]


class ScheduleResponse(BaseModel):
    origin: str
    destination: str
    source: str
    fetched_at: datetime
    window_start: date
    weeks: int
    columns: list[date]
    rows: list[ScheduleRow]
    flight_count: int
