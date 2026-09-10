-- Flight schedule cache for origin/destination routes.

CREATE TABLE IF NOT EXISTS routes (
    id                  INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    origin              VARCHAR(3) NOT NULL CHECK (origin ~ '^[A-Z]{3}$'),
    destination         VARCHAR(3) NOT NULL CHECK (destination ~ '^[A-Z]{3}$'),
    origin_timezone     TEXT NOT NULL,
    destination_timezone TEXT NOT NULL,
    window_start        DATE NOT NULL,
    weeks               INTEGER NOT NULL CHECK (weeks > 0),
    fetched_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT routes_origin_destination_key UNIQUE (origin, destination)
);

CREATE TABLE IF NOT EXISTS scheduled_flights (
    id                          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    route_id                    INTEGER NOT NULL REFERENCES routes(id) ON DELETE CASCADE,
    flight_date                 DATE NOT NULL,
    weekday                     TEXT NOT NULL,
    flight_number               TEXT NOT NULL,
    airline                     TEXT NOT NULL,
    aircraft                    TEXT NOT NULL,
    scheduled_departure_time    TIMESTAMPTZ NOT NULL,
    scheduled_arrival_time      TIMESTAMPTZ NOT NULL,
    departure_local_time        TIME NOT NULL,
    arrival_local_time          TIME NOT NULL
);

CREATE INDEX IF NOT EXISTS scheduled_flights_route_date_idx
    ON scheduled_flights (route_id, flight_date, scheduled_departure_time);
