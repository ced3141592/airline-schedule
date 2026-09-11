from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class Airport:
    """Minimal IATA airport wrapper compatible with the FlightsFrom client."""

    def __init__(self, airport: str | Airport) -> None:
        if isinstance(airport, Airport):
            self.iata = airport.iata
            return

        code = airport.strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise ValueError(f"Invalid airport code: {airport!r}")
        self.iata = code

    def __str__(self) -> str:
        return self.iata


@dataclass(frozen=True)
class ScheduledFlight:
    departure: str
    destination: str
    scheduled_departure_time: datetime
    scheduled_arrival_time: datetime
    aircraft: str
    airline: str
    flight_number: str

    @property
    def flight_date(self):
        return self.scheduled_departure_time.date()
