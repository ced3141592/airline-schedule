from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import get_settings
from app.db import get_session_factory, init_db, reset_engine
from app.domain import ScheduledFlight
from app.main import app
from app.repository import get_route


def _flight(hour: int, flight_number: str, day: date) -> ScheduledFlight:
    departure = datetime(day.year, day.month, day.day, hour, 0, tzinfo=timezone.utc)
    return ScheduledFlight(
        departure="MAD",
        destination="AMS",
        scheduled_departure_time=departure,
        scheduled_arrival_time=departure + timedelta(hours=2, minutes=25),
        aircraft="Airbus A320",
        airline="Iberia",
        flight_number=flight_number,
    )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://flights:flights@127.0.0.1:5432/flights_test")
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
    monday = date(2026, 9, 7)
    flights = [
        _flight(6, "IB100", monday),
        _flight(8, "KL200", monday + timedelta(days=1)),
    ]
    fetch_calls = {"count": 0}

    def fake_fetch(origin, destination, window_start, weeks):
        fetch_calls["count"] += 1
        assert origin == "MAD"
        assert destination == "AMS"
        return flights

    monkeypatch.setattr("app.services.fetch_from_flightsfrom", fake_fetch)
    monkeypatch.setattr("app.services.current_window_start", lambda: monday)

    first = client.post("/api/schedules", json={"origin": "mad", "destination": "ams"})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["source"] == "flightsfrom"
    assert body["flight_count"] == 2
    assert body["rows"][0]["weekday"] == "Monday"
    assert body["rows"][0]["cells"][0]["flights"][0]["flight_number"] == "IB100"
    assert body["rows"][1]["cells"][0]["flights"][0]["flight_number"] == "KL200"

    second = client.post("/api/schedules", json={"origin": "MAD", "destination": "AMS"})
    assert second.status_code == 200
    assert second.json()["source"] == "database"
    assert fetch_calls["count"] == 1


def test_update_overwrites_database(client, monkeypatch):
    monday = date(2026, 9, 7)
    monkeypatch.setattr("app.services.current_window_start", lambda: monday)
    monkeypatch.setattr(
        "app.services.fetch_from_flightsfrom",
        lambda *args, **kwargs: [_flight(6, "OLD1", monday)],
    )
    initial = client.post("/api/schedules", json={"origin": "MAD", "destination": "AMS"})
    assert initial.json()["rows"][0]["cells"][0]["flights"][0]["flight_number"] == "OLD1"

    monkeypatch.setattr(
        "app.services.fetch_from_flightsfrom",
        lambda *args, **kwargs: [_flight(9, "NEW9", monday)],
    )
    updated = client.post("/api/schedules?force_update=true", json={"origin": "MAD", "destination": "AMS"})
    assert updated.status_code == 200
    assert updated.json()["source"] == "flightsfrom"
    flights = updated.json()["rows"][0]["cells"][0]["flights"]
    assert [flight["flight_number"] for flight in flights] == ["NEW9"]

    session_factory = get_session_factory()
    with session_factory() as session:
        route = get_route(session, "MAD", "AMS")
        assert len(route.flights) == 1
        assert route.flights[0].flight_number == "NEW9"
