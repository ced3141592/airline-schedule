from __future__ import annotations

from collections.abc import Generator
from datetime import date, datetime, time, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, Time, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    origin: Mapped[str] = mapped_column(String(3), nullable=False)
    destination: Mapped[str] = mapped_column(String(3), nullable=False)
    origin_timezone: Mapped[str] = mapped_column(Text, nullable=False)
    destination_timezone: Mapped[str] = mapped_column(Text, nullable=False)
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    flights: Mapped[list[ScheduledFlightRow]] = relationship(
        back_populates="route",
        cascade="all, delete-orphan",
        order_by="ScheduledFlightRow.scheduled_departure_time",
    )


class ScheduledFlightRow(Base):
    __tablename__ = "scheduled_flights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"), nullable=False)
    flight_date: Mapped[date] = mapped_column(Date, nullable=False)
    weekday: Mapped[str] = mapped_column(Text, nullable=False)
    flight_number: Mapped[str] = mapped_column(Text, nullable=False)
    airline: Mapped[str] = mapped_column(Text, nullable=False)
    aircraft: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_departure_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_arrival_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    departure_local_time: Mapped[time] = mapped_column(Time, nullable=False)
    arrival_local_time: Mapped[time] = mapped_column(Time, nullable=False)
    route: Mapped[Route] = relationship(back_populates="flights")


_engine = None
_SessionLocal = None


def reset_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(settings.database_url, pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_session_factory():
    get_engine()
    return _SessionLocal


def init_db() -> None:
    settings = get_settings()
    statements = [part.strip() for part in settings.schema_path.read_text().split(";") if part.strip()]
    engine = get_engine()
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def get_session() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
