"""Shared database utilities — kept here to avoid DRY violations across endpoints."""

from sqlalchemy.exc import OperationalError


def is_lock_not_available_error(exc: OperationalError) -> bool:
    """
    Best-effort detection of a lock-not-available error coming from the DB.

    Inspects the wrapped DBAPI error (``exc.orig``) for a lock-specific
    SQLSTATE such as PostgreSQL's 55P03 ("lock_not_available").
    Falls back to a string contains-check for SQLite and other drivers.
    """
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False
    # PostgreSQL via psycopg/asyncpg exposes SQLSTATE here
    pgcode = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
    if pgcode == "55P03":
        return True
    # Fallback for SQLite in tests and other drivers
    message = str(orig).lower()
    return "database is locked" in message or "lock not available" in message
