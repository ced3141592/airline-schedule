from datetime import date, datetime, timedelta
from pathlib import Path

import pytz

from app.clients.flightsfrom import FlightsFromClient
from app.repository import monday_on_or_before, window_dates


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def test_parse_duration():
    duration = FlightsFromClient._parse_duration("Flight duration: 2 hours and 25 minutes")
    assert duration == timedelta(hours=2, minutes=25)


def test_parse_scheduled_flights_from_html():
    html_doc = (FIXTURE_DIR / "calendar_popup.html").read_text()
    flights = FlightsFromClient._parse_scheduled_flights_from_html(html_doc)

    assert [flight.flight_number for flight in flights] == ["KL1500", "UX1091", "IB731"]
    assert flights[0].airline == "KLM"
    assert flights[0].aircraft == "Airbus A321neo"
    assert flights[0].departure == "MAD"
    assert flights[0].destination == "AMS"

    madrid = pytz.timezone("Europe/Madrid")
    expected_departure = madrid.localize(datetime(2026, 9, 10, 6, 0)).astimezone(pytz.UTC)
    assert flights[0].scheduled_departure_time == expected_departure
    assert flights[0].scheduled_arrival_time == expected_departure + timedelta(hours=2, minutes=25)


def test_parse_empty_day():
    html_doc = (FIXTURE_DIR / "empty_day.html").read_text()
    assert FlightsFromClient._parse_scheduled_flights_from_html(html_doc) == []


def test_monday_window():
    assert monday_on_or_before(date(2026, 9, 10)) == date(2026, 9, 7)
    assert window_dates(date(2026, 9, 7), 2)[0] == date(2026, 9, 7)
    assert window_dates(date(2026, 9, 7), 2)[-1] == date(2026, 9, 20)
