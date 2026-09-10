from __future__ import annotations

import base64
import binascii
import html
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytz
from bs4 import BeautifulSoup
from curl_cffi import requests

from app.clients.browser import mock_random_browser
from app.domain import Airport, ScheduledFlight
from app.timezones import timezone_for_iata

logger = logging.getLogger(__name__)

HTML_FILE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "calendar_popup.html"
IS_DEV = False


class FlightsFromClient:
    @staticmethod
    def get_flights(dep: str, dest: str, date: datetime) -> list[ScheduledFlight]:
        html_doc = FlightsFromClient._get_html(dep, dest, date)
        return FlightsFromClient._parse_scheduled_flights_from_html(html_doc)

    @staticmethod
    def get_flights_for_dates(dep: str, dest: str, dates: list[datetime]) -> list[ScheduledFlight]:
        if not dates:
            return []

        if IS_DEV:
            flights: list[ScheduledFlight] = []
            for date in dates:
                flights.extend(FlightsFromClient.get_flights(dep, dest, date))
            return flights

        dep_iata = FlightsFromClient._to_iata(dep)
        dest_iata = FlightsFromClient._to_iata(dest)
        session = requests.Session(impersonate="chrome")
        browser_headers = FlightsFromClient._build_browser_headers(dep_iata, dest_iata)
        FlightsFromClient._warmup_session(session, dep_iata, dest_iata, browser_headers)

        flights: list[ScheduledFlight] = []
        for index, date in enumerate(dates):
            logger.info("Fetching %s-%s on %s (%s/%s)", dep_iata, dest_iata, date.date(), index + 1, len(dates))
            html_doc = FlightsFromClient._get_html_with_session(
                session, dep_iata, dest_iata, date, browser_headers
            )
            flights.extend(FlightsFromClient._parse_scheduled_flights_from_html(html_doc))
            if index < len(dates) - 1:
                time.sleep(0.25)
        return flights

    @staticmethod
    def _get_html(dep: str, dest: str, date: datetime) -> str:
        if IS_DEV:
            return HTML_FILE.read_text()

        dep_iata = FlightsFromClient._to_iata(dep)
        dest_iata = FlightsFromClient._to_iata(dest)
        url = FlightsFromClient._build_url(dep, dest, date)
        session = requests.Session(impersonate="chrome")
        browser_headers = FlightsFromClient._build_browser_headers(dep_iata, dest_iata)
        res = FlightsFromClient._fetch_calendar_payload(session, dep_iata, dest_iata, url, browser_headers)

        return FlightsFromClient._decode_payload(res)

    @staticmethod
    def _get_html_with_session(
        session: requests.Session,
        dep_iata: str,
        dest_iata: str,
        date: datetime,
        browser_headers: dict[str, str],
    ) -> str:
        url = FlightsFromClient._build_url(dep_iata, dest_iata, date)
        res = session.get(url, headers=browser_headers, timeout=20)
        if not res.ok:
            if res.status_code == 403:
                time.sleep(10)
                res = session.get(url, headers=browser_headers, timeout=20)
            if not res.ok:
                raise ValueError(f"Failed to fetch flight data: {res.status_code} {res.text}")
        return FlightsFromClient._decode_payload(res)

    @staticmethod
    def _decode_payload(res: requests.Response) -> str:
        if not res.ok:
            if res.status_code == 403:
                time.sleep(10)
                raise ValueError(f"Failed to fetch flight data: {res.status_code} {res.text}")
            raise ValueError(f"Failed to fetch flight data: {res.status_code} {res.text}")

        payload = res.text.strip()
        if FlightsFromClient._is_challenge_page(payload):
            raise ValueError("Blocked by Cloudflare challenge page. Browser automation is required.")

        try:
            return base64.b64decode(payload, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return payload

    @staticmethod
    def _build_url(dep: str, dest: str, date: datetime) -> str:
        dep = FlightsFromClient._to_iata(dep)
        dest = FlightsFromClient._to_iata(dest)
        return f"https://www.flightsfrom.com/api/getCalendarPopupData/{date.strftime('%Y-%m-%d')}/{dep}/{dest}"

    @staticmethod
    def _to_iata(airport: str | Airport) -> str:
        if isinstance(airport, Airport):
            return airport.iata
        if len(airport) == 3:
            return airport.upper()
        return Airport(airport).iata

    @staticmethod
    def _build_browser_headers(dep: str, dest: str) -> dict[str, str]:
        headers = mock_random_browser(f"https://www.flightsfrom.com/{dep.lower()}-{dest.lower()}")
        headers["Referer"] = f"https://www.flightsfrom.com/{dep.lower()}-{dest.lower()}"
        return headers

    @staticmethod
    def _warmup_session(
        session: requests.Session,
        dep_iata: str,
        dest_iata: str,
        browser_headers: dict[str, str],
    ) -> None:
        session.get("https://www.flightsfrom.com", headers=browser_headers, timeout=20)
        session.get(
            f"https://www.flightsfrom.com/{dep_iata.lower()}-{dest_iata.lower()}",
            headers=browser_headers,
            timeout=20,
        )

    @staticmethod
    def _fetch_calendar_payload(
        session: requests.Session,
        dep_iata: str,
        dest_iata: str,
        url: str,
        browser_headers: dict[str, str],
    ) -> requests.Response:
        # Warm-up requests to establish cookies and request fingerprint before API call.
        FlightsFromClient._warmup_session(session, dep_iata, dest_iata, browser_headers)
        return session.get(url, headers=browser_headers, timeout=20)

    @staticmethod
    def _is_challenge_page(payload: str) -> bool:
        text = payload.lower()
        return (
            "just a moment" in text
            or "cf_chl_opt" in text
            or "challenges.cloudflare.com" in text
            or "enable javascript and cookies" in text
        )

    @staticmethod
    def _parse_duration(text: str) -> timedelta:
        hours = 0
        minutes = 0

        hours_match = re.search(r"(\d+)\s+hour", text)
        minutes_match = re.search(r"(\d+)\s+minute", text)

        if hours_match:
            hours = int(hours_match.group(1))
        if minutes_match:
            minutes = int(minutes_match.group(1))

        return timedelta(hours=hours, minutes=minutes)

    @staticmethod
    def _parse_scheduled_flights_from_html(html_doc: str) -> list[ScheduledFlight]:
        soup = BeautifulSoup(html_doc, "html.parser")

        first_row = soup.select_one("tr.ff-row-clickable")
        if first_row is None:
            return []

        duration_text = soup.select_one(".flightinfo-text")
        if duration_text is None:
            raise ValueError("Could not find flight duration in HTML")
        flight_duration = FlightsFromClient._parse_duration(duration_text.get_text(" ", strip=True))

        onclick = html.unescape(first_row.get("onclick") or "")
        route_match = re.search(
            r"initDatePlugin\('(?P<departure>[A-Z]{3})','(?P<destination>[A-Z]{3})',\s*'(?P<date>\d{4}-\d{2}-\d{2})'",
            onclick,
        )
        if route_match is None:
            raise ValueError("Could not parse route information from HTML")

        departure_code = route_match.group("departure")
        destination_code = route_match.group("destination")
        flight_date = datetime.strptime(route_match.group("date"), "%Y-%m-%d").date()

        departure_tz = pytz.timezone(timezone_for_iata(departure_code))
        destination_tz = pytz.timezone(timezone_for_iata(destination_code))

        flights: list[ScheduledFlight] = []
        for row in soup.select("tr.ff-row-clickable"):
            time_cell = row.select_one("td.ff-col-time")
            airline_cell = row.select_one("span.ff-airline-name")
            flight_number_cell = row.select_one("td.ff-col-flight")
            aircraft_cell = row.select_one("td.ff-col-aircraft")

            if not all([time_cell, airline_cell, flight_number_cell, aircraft_cell]):
                continue

            departure_time_text = time_cell.get_text(" ", strip=True)
            departure_time = datetime.strptime(departure_time_text, "%H:%M").time()
            departure_local = departure_tz.localize(datetime.combine(flight_date, departure_time))
            arrival_utc = departure_local.astimezone(pytz.UTC) + flight_duration
            arrival_local = arrival_utc.astimezone(destination_tz)

            flights.append(
                ScheduledFlight(
                    departure=departure_code,
                    destination=destination_code,
                    scheduled_departure_time=departure_local.astimezone(pytz.UTC),
                    scheduled_arrival_time=arrival_local.astimezone(pytz.UTC),
                    aircraft=aircraft_cell.get_text(" ", strip=True),
                    airline=airline_cell.get_text(" ", strip=True),
                    flight_number=flight_number_cell.get_text(" ", strip=True),
                )
            )

        logger.debug("Parsed %s flights for %s-%s on %s", len(flights), departure_code, destination_code, flight_date)
        return flights
