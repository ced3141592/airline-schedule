# Airline Schedule

Web app that shows weekly airline schedules for a route. It has three parts:

- **UI** (`frontend/`): JavaScript page with From / To fields, Run, and Update
- **Server** (`backend/`): Python FastAPI service
- **Database** (`database/`): PostgreSQL scripts that cache fetched schedules

## How it works

1. Enter 3-letter IATA codes (for example `MAD` → `AMS`) and click **Run**.
2. The server looks up that route in PostgreSQL.
3. If the route is cached, the UI renders it immediately.
4. If it is missing, the server fetches two weeks of calendars from [FlightsFrom.com](https://www.flightsfrom.com), stores them, and then renders them.
5. **Update** always refetches from FlightsFrom.com and overwrites the cached route.

The table has one row per weekday (Monday–Sunday) and one column per week. Each cell lists that date’s flights in departure order.

## Run with Docker

```bash
docker compose up --build
```

Open http://localhost:8000

## Run locally

PostgreSQL 16+ and Python 3.12+ are required.

```bash
psql -U postgres -c "CREATE USER flights WITH PASSWORD 'flights';"
psql -U postgres -c "CREATE DATABASE flights OWNER flights;"
cp .env.example .env
python3 -m pip install -r backend/requirements.txt
cd backend
PYTHONPATH=. uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API applies `database/schema.sql` on startup.

## Tests

```bash
python3 -m pip install -r backend/requirements-dev.txt
cd backend
PYTHONPATH=. pytest
```

API tests expect a PostgreSQL database named `flights_test` owned by the `flights` user.

## Project layout

```
backend/app/          FastAPI app, FlightsFrom client, and persistence
backend/tests/        Parser and API tests
database/schema.sql  PostgreSQL tables
frontend/            Static HTML, CSS, and JavaScript
```
