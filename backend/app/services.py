from __future__ import annotations

from datetime import date, datetime, timedelta

import pytz
from sqlalchemy.orm import Session

from app.clients.flightsfrom import FlightsFromClient
from app.config import get_settings
from app.db import Route, get_session_factory
from app.repository import (
    WEEKDAYS,
    get_route,
    monday_on_or_before,
    replace_route_schedule,
    window_dates,
)
from app.schemas import FlightView, ScheduleCell, ScheduleResponse, ScheduleRow


def normalize_iata(code: str) -> str:
    return code.strip().upper()


def current_window_start() -> date:
    return monday_on_or_before(datetime.now().date())


def fetch_from_flightsfrom(origin: str, destination: str, window_start: date, weeks: int) -> list:
    dates = [datetime.combine(day, datetime.min.time()) for day in window_dates(window_start, weeks)]
    return FlightsFromClient.get_flights_for_dates(origin, destination, dates)


def to_response(route: Route, source: str) -> ScheduleResponse:
    origin_zone = pytz.timezone(route.origin_timezone)
    destination_zone = pytz.timezone(route.destination_timezone)
    flights_by_date: dict[date, list[FlightView]] = {}

    for row in route.flights:
        departure_local = row.scheduled_departure_time.astimezone(origin_zone)
        arrival_local = row.scheduled_arrival_time.astimezone(destination_zone)
        flights_by_date.setdefault(row.flight_date, []).append(
            FlightView(
                flight_number=row.flight_number,
                airline=row.airline,
                aircraft=row.aircraft,
                departure_local_time=departure_local.strftime("%H:%M"),
                arrival_local_time=arrival_local.strftime("%H:%M"),
                scheduled_departure_time=row.scheduled_departure_time,
                scheduled_arrival_time=row.scheduled_arrival_time,
            )
        )

    for flight_date in flights_by_date:
        flights_by_date[flight_date].sort(key=lambda item: item.departure_local_time)

    columns = [route.window_start + timedelta(weeks=week) for week in range(route.weeks)]
    rows: list[ScheduleRow] = []
    for weekday_index, weekday in enumerate(WEEKDAYS):
        cells: list[ScheduleCell] = []
        for week_start in columns:
            cell_date = week_start + timedelta(days=weekday_index)
            cells.append(
                ScheduleCell(
                    date=cell_date,
                    weekday=weekday,
                    flights=flights_by_date.get(cell_date, []),
                )
            )
        rows.append(ScheduleRow(weekday=weekday, cells=cells))

    return ScheduleResponse(
        origin=route.origin.strip(),
        destination=route.destination.strip(),
        source=source,
        fetched_at=route.fetched_at,
        window_start=route.window_start,
        weeks=route.weeks,
        columns=columns,
        rows=rows,
        flight_count=len(route.flights),
    )


def load_or_fetch_schedule(origin: str, destination: str, force_update: bool) -> ScheduleResponse:
    origin = normalize_iata(origin)
    destination = normalize_iata(destination)
    if origin == destination:
        raise ValueError("Origin and destination must be different airports.")

    session_factory = get_session_factory()

    if not force_update:
        with session_factory() as session:
            cached = get_route(session, origin, destination)
            if cached is not None:
                return to_response(cached, source="database")

    settings = get_settings()
    window_start = current_window_start()
    flights = fetch_from_flightsfrom(origin, destination, window_start, settings.schedule_weeks)

    with session_factory() as session:
        route = replace_route_schedule(
            session,
            origin=origin,
            destination=destination,
            flights=flights,
            window_start=window_start,
            weeks=settings.schedule_weeks,
        )
        session.commit()
        return to_response(route, source="flightsfrom")
