"""Shared custom SQLAlchemy column types."""

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class TZDateTime(TypeDecorator):
    """A DateTime that is always timezone-aware, even on SQLite.

    SQLite has no native timestamptz type -- SQLAlchemy's own
    DateTime(timezone=True) is a no-op on the sqlite dialect, and a plain
    DateTime column silently drops tzinfo on every read. That previously
    meant every reader of Run.created_at/started_at/completed_at and
    AssetOutcome.updated_at (API responses, the CSV export, any future
    internal comparison against datetime.now(timezone.utc)) got back a
    naive datetime that was actually UTC without saying so.

    This mirrors SQLAlchemy's documented TZDateTime recipe
    (https://docs.sqlalchemy.org/en/20/core/custom_types.html): store as
    naive UTC (what SQLite can actually persist), and always hand back an
    aware UTC datetime, so tzinfo can never again go missing at any read
    site without deliberately stripping it.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise TypeError(
                f"{value!r} is naive; TZDateTime columns require an aware datetime"
            )
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)
