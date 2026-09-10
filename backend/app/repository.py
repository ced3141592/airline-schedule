from __future__ import annotations

from datetime import date, timedelta

import pytz
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import Route, ScheduledFlightRow, utcnow
from app.domain import ScheduledFlight
from app.timezones import timezone_for_iata


WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def monday_on_or_before(day: date) -> date:
    return day - timedelta(days=day.weekday())


def window_dates(window_start: date, weeks: int) -> list[date]:
    return [window_start + timedelta(days=offset) for offset in range(weeks * 7)]


def get_route(session: Session, origin: str, destination: str) -> Route | None:
    statement = (
        select(Route)
        .options(selectinload(Route.flights))
        .where(Route.origin == origin, Route.destination == destination)
    )
    return session.scalar(statement)


def replace_route_schedule(
    session: Session,
    origin: str,
    destination: str,
    flights: list[ScheduledFlight],
    window_start: date,
    weeks: int,
) -> Route:
    route = get_route(session, origin, destination)
    now = utcnow()
    origin_tz = timezone_for_iata(origin)
    destination_tz = timezone_for_iata(destination)

    if route is None:
        route = Route(
            origin=origin,
            destination=destination,
            origin_timezone=origin_tz,
            destination_timezone=destination_tz,
            window_start=window_start,
            weeks=weeks,
            fetched_at=now,
            updated_at=now,
        )
        session.add(route)
        session.flush()
    else:
        route.origin_timezone = origin_tz
        route.destination_timezone = destination_tz
        route.window_start = window_start
        route.weeks = weeks
        route.fetched_at = now
        route.updated_at = now
        route.flights.clear()
        session.flush()

    origin_zone = pytz.timezone(origin_tz)
    destination_zone = pytz.timezone(destination_tz)

    for flight in flights:
        departure_local = flight.scheduled_departure_time.astimezone(origin_zone)
        arrival_local = flight.scheduled_arrival_time.astimezone(destination_zone)
        flight_date = departure_local.date()
        route.flights.append(
            ScheduledFlightRow(
                flight_date=flight_date,
                weekday=flight_date.strftime("%A"),
                flight_number=flight.flight_number,
                airline=flight.airline,
                aircraft=flight.aircraft,
                scheduled_departure_time=flight.scheduled_departure_time,
                scheduled_arrival_time=flight.scheduled_arrival_time,
                departure_local_time=departure_local.time().replace(tzinfo=None),
                arrival_local_time=arrival_local.time().replace(tzinfo=None),
            )
        )

    session.flush()
    return get_route(session, origin, destination)
