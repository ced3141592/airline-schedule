from __future__ import annotations

import airportsdata

_AIRPORTS = airportsdata.load("IATA")


def timezone_for_iata(iata: str) -> str:
    record = _AIRPORTS.get(iata.upper())
    if not record:
        return "UTC"
    return record.get("tz") or "UTC"
