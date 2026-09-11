from __future__ import annotations

from datetime import date, datetime, timedelta

import pytz

from app.clients.flightsfrom import FlightsFromClient
from app.db import Route, get_session_factory
from app.repository import (
    WEEKDAYS,
    delete_past_data,
    get_route,
    replace_route_schedule,
    week_mondays_for_window,
    window_dates,
    window_end,
)
from app.schemas import FlightView, ScheduleCell, ScheduleResponse, ScheduleRow


def normalize_iata(code: str) -> str:
    return code.strip().upper()


def today() -> date:
    return datetime.now().date()


def fetch_from_flightsfrom(origin: str, destination: str, window_start: date, weeks: int) -> list:
    dates = [datetime.combine(day, datetime.min.time()) for day in window_dates(window_start, weeks)]
    return FlightsFromClient.get_flights_for_dates(origin, destination, dates)


def to_response(route: Route, source: str) -> ScheduleResponse:
    origin_zone = pytz.timezone(route.origin_timezone)
    destination_zone = pytz.timezone(route.destination_timezone)
    flights_by_date: dict[date, list[FlightView]] = {}
    last_date = window_end(route.window_start, route.weeks)

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

    columns = week_mondays_for_window(route.window_start, route.weeks)
    rows: list[ScheduleRow] = []
    for weekday_index, weekday in enumerate(WEEKDAYS):
        cells: list[ScheduleCell] = []
        for week_start in columns:
            cell_date = week_start + timedelta(days=weekday_index)
            in_range = route.window_start <= cell_date <= last_date
            cells.append(
                ScheduleCell(
                    date=cell_date,
                    weekday=weekday,
                    in_range=in_range,
                    flights=flights_by_date.get(cell_date, []) if in_range else [],
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


def load_or_fetch_schedule(
    origin: str,
    destination: str,
    force_update: bool,
    start_date: date | None = None,
    weeks: int | None = None,
) -> ScheduleResponse:
    origin = normalize_iata(origin)
    destination = normalize_iata(destination)
    if origin == destination:
        raise ValueError("Origin and destination must be different airports.")

    current_day = today()
    window_start = start_date or current_day
    week_count = 4 if weeks is None else weeks
    if window_start < current_day:
        raise ValueError("Start date cannot be in the past.")
    if week_count < 1:
        raise ValueError("Length must be at least 1 week.")

    session_factory = get_session_factory()

    with session_factory() as session:
        delete_past_data(session, current_day)
        session.commit()

    if not force_update:
        with session_factory() as session:
            cached = get_route(session, origin, destination)
            if (
                cached is not None
                and cached.window_start == window_start
                and cached.weeks == week_count
            ):
                return to_response(cached, source="database")

    flights = fetch_from_flightsfrom(origin, destination, window_start, week_count)

    with session_factory() as session:
        route = replace_route_schedule(
            session,
            origin=origin,
            destination=destination,
            flights=flights,
            window_start=window_start,
            weeks=week_count,
        )
        session.commit()
        return to_response(route, source="flightsfrom")
