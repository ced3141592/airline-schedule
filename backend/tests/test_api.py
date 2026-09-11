from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import get_settings
from app.db import get_session_factory, init_db, reset_engine
from app.domain import ScheduledFlight
from app.main import app
from app.repository import get_route, replace_route_schedule


TODAY = date(2026, 9, 14)


def _flight(hour: int, flight_number: str, day: date, origin="MAD", destination="AMS") -> ScheduledFlight:
    departure = datetime(day.year, day.month, day.day, hour, 0, tzinfo=timezone.utc)
    return ScheduledFlight(
        departure=origin,
        destination=destination,
        scheduled_departure_time=departure,
        scheduled_arrival_time=departure + timedelta(hours=2, minutes=25),
        aircraft="Airbus A320",
        airline="Iberia",
        flight_number=flight_number,
    )


def _search_body(origin="mad", destination="ams", start_date=TODAY, weeks=2):
    return {
        "origin": origin,
        "destination": destination,
        "start_date": start_date.isoformat(),
        "weeks": weeks,
    }


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://flights:flights@127.0.0.1:5432/flights_test")
    monkeypatch.setattr("app.services.today", lambda: TODAY)
    get_settings.cache_clear()
    reset_engine()
    init_db()
    session_factory = get_session_factory()
    with session_factory() as session:
        session.execute(text("TRUNCATE scheduled_flights, routes RESTART IDENTITY CASCADE"))
        session.commit()

    with TestClient(app) as test_client:
        yield test_client

    get_settings.cache_clear()
    reset_engine()


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_run_fetches_then_uses_cache(client, monkeypatch):
    flights = [
        _flight(6, "IB100", TODAY),
        _flight(8, "KL200", TODAY + timedelta(days=1)),
    ]
    fetch_calls = {"count": 0}

    def fake_fetch(origin, destination, window_start, weeks):
        fetch_calls["count"] += 1
        assert origin == "MAD"
        assert destination == "AMS"
        assert window_start == TODAY
        assert weeks == 2
        return flights

    monkeypatch.setattr("app.services.fetch_from_flightsfrom", fake_fetch)

    first = client.post("/api/schedules", json=_search_body())
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["source"] == "flightsfrom"
    assert body["flight_count"] == 2
    assert body["window_start"] == TODAY.isoformat()
    assert body["weeks"] == 2
    assert body["rows"][0]["weekday"] == "Monday"
    assert body["rows"][0]["cells"][0]["flights"][0]["flight_number"] == "IB100"
    assert body["rows"][1]["cells"][0]["flights"][0]["flight_number"] == "KL200"

    second = client.post("/api/schedules", json=_search_body(origin="MAD", destination="AMS"))
    assert second.status_code == 200
    assert second.json()["source"] == "database"
    assert fetch_calls["count"] == 1


def test_different_length_does_not_use_cache(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.fetch_from_flightsfrom",
        lambda origin, destination, window_start, weeks: [_flight(6, f"W{weeks}", TODAY)],
    )
    first = client.post("/api/schedules", json=_search_body(weeks=2))
    assert first.json()["weeks"] == 2
    second = client.post("/api/schedules", json=_search_body(weeks=4))
    assert second.status_code == 200
    assert second.json()["source"] == "flightsfrom"
    assert second.json()["weeks"] == 4


def test_update_overwrites_database(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.fetch_from_flightsfrom",
        lambda *args, **kwargs: [_flight(6, "OLD1", TODAY)],
    )
    initial = client.post("/api/schedules", json=_search_body())
    assert initial.json()["rows"][0]["cells"][0]["flights"][0]["flight_number"] == "OLD1"

    monkeypatch.setattr(
        "app.services.fetch_from_flightsfrom",
        lambda *args, **kwargs: [_flight(9, "NEW9", TODAY)],
    )
    updated = client.post("/api/schedules?force_update=true", json=_search_body())
    assert updated.status_code == 200
    assert updated.json()["source"] == "flightsfrom"
    flights = updated.json()["rows"][0]["cells"][0]["flights"]
    assert [flight["flight_number"] for flight in flights] == ["NEW9"]

    session_factory = get_session_factory()
    with session_factory() as session:
        route = get_route(session, "MAD", "AMS")
        assert len(route.flights) == 1
        assert route.flights[0].flight_number == "NEW9"


def test_search_deletes_past_flights(client, monkeypatch):
    past = TODAY - timedelta(days=3)
    session_factory = get_session_factory()
    with session_factory() as session:
        replace_route_schedule(
            session,
            origin="LHR",
            destination="CDG",
            flights=[_flight(6, "PAST1", past, origin="LHR", destination="CDG")],
            window_start=past,
            weeks=2,
        )
        replace_route_schedule(
            session,
            origin="MAD",
            destination="AMS",
            flights=[
                _flight(6, "PAST2", past),
                _flight(8, "KEEP", TODAY + timedelta(days=2)),
            ],
            window_start=past,
            weeks=2,
        )
        session.commit()

    monkeypatch.setattr(
        "app.services.fetch_from_flightsfrom",
        lambda *args, **kwargs: [_flight(7, "NEW", TODAY)],
    )
    response = client.post("/api/schedules", json=_search_body())
    assert response.status_code == 200
    assert response.json()["rows"][0]["cells"][0]["flights"][0]["flight_number"] == "NEW"

    with session_factory() as session:
        assert get_route(session, "LHR", "CDG") is None
        remaining = session.execute(text("SELECT flight_number FROM scheduled_flights ORDER BY flight_number"))
        assert [row[0] for row in remaining] == ["NEW"]


def test_rejects_start_date_in_the_past(client):
    response = client.post(
        "/api/schedules",
        json=_search_body(start_date=TODAY - timedelta(days=1)),
    )
    assert response.status_code == 400
    assert "past" in response.json()["detail"].lower()
