"""Shared, conservative budget for guarded routine calls, not an account-wide quota.

Initialize explicitly with ``python -m psbx.recurring_budget init --path PATH``.
Reservations are durable before network I/O and are never refunded, including
failed calls and unknown charges. Deleting this file destroys its accounting;
there is deliberately no reset, quota-change, or unblock command.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

UTC = timezone.utc
TIMEZONE = "America/New_York"
UNITS_PER_USD = 1_000_000_000
DAILY_UNITS = UNITS_PER_USD
MONTHLY_UNITS = 20 * UNITS_PER_USD
SCHEMA_VERSION = 1


class RecurringBudgetError(RuntimeError):
    """The persistent routine budget could not authorize a request."""


def configured_path() -> Path | None:
    raw = os.environ.get("PSBX_RECURRING_BUDGET_PATH", "").strip()
    routine = os.environ.get("PSBX_ROUTINE_LIVE", "").strip().lower()
    if not raw:
        if routine in {"1", "true", "yes", "on"}:
            raise RecurringBudgetError("routine live calls require PSBX_RECURRING_BUDGET_PATH")
        return None
    path = Path(raw)
    if not path.is_absolute():
        raise RecurringBudgetError("PSBX_RECURRING_BUDGET_PATH must be absolute")
    return path


def _units(value: object) -> int:
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount > 1_000_000:
            raise ValueError
        return int((amount * UNITS_PER_USD).to_integral_value(rounding=ROUND_CEILING))
    except (InvalidOperation, ValueError, TypeError, OverflowError):
        raise RecurringBudgetError("cost must be a finite nonnegative USD amount") from None


def _stamp(now: datetime | None) -> tuple[str, str, str]:
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise RecurringBudgetError("budget time must be timezone-aware")
    local = current.astimezone(ZoneInfo(TIMEZONE))
    return current.astimezone(UTC).isoformat(), local.strftime("%Y-%m-%d"), local.strftime("%Y-%m")


def _identifier(value: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 200 or any(
        ord(char) < 32 for char in value
    ):
        raise RecurringBudgetError("budget identifiers must be nonempty, bounded plain text")


def _validate(db: sqlite3.Connection) -> None:
    if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise RecurringBudgetError("recurring budget database failed integrity checking")
    policy = db.execute(
        "SELECT version, timezone, daily_units, monthly_units, units_per_usd, "
        "initialized_at, blocked FROM policy WHERE id=1"
    ).fetchone()
    if (
        policy is None
        or tuple(policy[:5]) != (
            SCHEMA_VERSION, TIMEZONE, DAILY_UNITS, MONTHLY_UNITS, UNITS_PER_USD
        )
        or policy[6] not in (0, 1)
        or db.execute("SELECT count(*) FROM policy").fetchone()[0] != 1
        or db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION
    ):
        raise RecurringBudgetError("recurring budget schema or fixed policy does not match")
    try:
        _stamp(datetime.fromisoformat(policy[5]))
    except (ValueError, TypeError):
        raise RecurringBudgetError("recurring budget initialization time is invalid") from None
    # Touch every required column; a truncated or foreign schema cannot authorize traffic.
    invalid = db.execute(
        "SELECT count(*) FROM reservations WHERE reservation_id IS NULL OR run_id IS NULL "
        "OR created_at IS NULL OR length(day)!=10 OR length(month)!=7 "
        "OR substr(day,1,7)!=month OR typeof(reserved_units)!='integer' "
        "OR reserved_units<=0 OR (actual_units IS NOT NULL AND "
        "(typeof(actual_units)!='integer' OR actual_units<0))"
    ).fetchone()[0]
    if invalid:
        raise RecurringBudgetError("recurring budget reservation data is invalid")


@contextmanager
def _transaction(path: Path) -> Iterator[sqlite3.Connection]:
    db = None
    try:
        # mode=rw never creates a missing ledger, including after accidental deletion.
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=rw", uri=True, timeout=30)
        db.execute("PRAGMA synchronous=FULL")
        db.execute("BEGIN IMMEDIATE")
        _validate(db)
        yield db
        db.commit()
    except (sqlite3.Error, OSError, ValueError) as exc:
        if db is not None:
            db.rollback()
        raise RecurringBudgetError(
            "recurring budget is missing, unreadable, locked, or invalid; traffic blocked"
        ) from exc
    finally:
        if db is not None:
            db.close()


def initialize(path: Path, *, now: datetime | None = None) -> None:
    """Create a new ledger once. Existing, even corrupt, files are never replaced."""
    stamp, _, _ = _stamp(now)
    if not path.is_absolute():
        raise RecurringBudgetError("budget path must be absolute")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except OSError as exc:
        raise RecurringBudgetError("budget initialization requires a new writable path") from exc
    os.close(fd)
    try:
        with sqlite3.connect(path) as db:
            db.execute("PRAGMA synchronous=FULL")
            db.executescript(
                "CREATE TABLE policy (id INTEGER PRIMARY KEY CHECK(id=1), version INTEGER, "
                "timezone TEXT, daily_units INTEGER, monthly_units INTEGER, units_per_usd INTEGER, "
                "initialized_at TEXT NOT NULL, blocked INTEGER NOT NULL CHECK(blocked IN (0,1)));"
                "CREATE TABLE reservations (reservation_id TEXT PRIMARY KEY NOT NULL, "
                "run_id TEXT NOT NULL, created_at TEXT NOT NULL, day TEXT NOT NULL, month TEXT NOT NULL, "
                "reserved_units INTEGER NOT NULL CHECK(reserved_units>0), "
                "actual_units INTEGER CHECK(actual_units>=0));"
                "CREATE INDEX reservation_periods ON reservations(month, day);"
                f"PRAGMA user_version={SCHEMA_VERSION};"
            )
            db.execute(
                "INSERT INTO policy VALUES (1,?,?,?,?,?,?,0)",
                (SCHEMA_VERSION, TIMEZONE, DAILY_UNITS, MONTHLY_UNITS, UNITS_PER_USD, stamp),
            )
    except sqlite3.Error as exc:
        raise RecurringBudgetError("budget initialization failed; incomplete file retained") from exc


def _totals(db: sqlite3.Connection, day: str, month: str) -> tuple[int, int]:
    row = db.execute(
        "SELECT COALESCE(SUM(CASE WHEN day=? THEN max(reserved_units, "
        "COALESCE(actual_units,0)) ELSE 0 END),0), "
        "COALESCE(SUM(max(reserved_units,COALESCE(actual_units,0))),0) "
        "FROM reservations WHERE month=?", (day, month),
    ).fetchone()
    return row[0], row[1]


def reserve(
    path: Path, reservation_id: str, run_id: str, estimated_usd: object,
    *, now: datetime | None = None,
) -> None:
    """Reserve once, atomically across processes, before any paid request."""
    _identifier(reservation_id)
    _identifier(run_id)
    units = _units(estimated_usd)
    if not units:
        raise RecurringBudgetError("reservation cost must be positive")
    stamp, day, month = _stamp(now)
    with _transaction(path) as db:
        initialized_at, blocked = db.execute(
            "SELECT initialized_at, blocked FROM policy"
        ).fetchone()
        if datetime.fromisoformat(stamp) < datetime.fromisoformat(initialized_at):
            raise RecurringBudgetError("budget cannot account for calls before initialization")
        if blocked:
            raise RecurringBudgetError("recurring budget halted after a reported cost overrun")
        if db.execute(
            "SELECT 1 FROM reservations WHERE reservation_id=?", (reservation_id,)
        ).fetchone():
            raise RecurringBudgetError("duplicate recurring reservation; replay blocked")
        daily, monthly = _totals(db, day, month)
        if daily + units > DAILY_UNITS or monthly + units > MONTHLY_UNITS:
            raise RecurringBudgetError("recurring budget exhausted ($1/day or $20/calendar month)")
        db.execute(
            "INSERT INTO reservations VALUES (?,?,?,?,?,?,NULL)",
            (reservation_id, run_id, stamp, day, month, units),
        )


def record_actual(path: Path, reservation_id: str, actual_usd: object) -> None:
    """Record known cost; overruns persistently halt future calls, never refund."""
    _identifier(reservation_id)
    actual = _units(actual_usd)
    with _transaction(path) as db:
        row = db.execute(
            "SELECT reserved_units, actual_units FROM reservations WHERE reservation_id=?",
            (reservation_id,),
        ).fetchone()
        if row is None:
            raise RecurringBudgetError("reported usage has no recurring reservation")
        actual = max(actual, row[1] or 0)
        db.execute(
            "UPDATE reservations SET actual_units=? WHERE reservation_id=?",
            (actual, reservation_id),
        )
        if actual > row[0]:
            db.execute("UPDATE policy SET blocked=1 WHERE id=1")


def status(path: Path, *, now: datetime | None = None) -> dict:
    _, day, month = _stamp(now)
    with _transaction(path) as db:
        daily, monthly = _totals(db, day, month)
        initialized, blocked = db.execute("SELECT initialized_at, blocked FROM policy").fetchone()
        return {
            "schema_version": SCHEMA_VERSION, "timezone": TIMEZONE,
            "initialized_at": initialized, "day": day, "month": month,
            "daily_limit_usd": 1, "monthly_limit_usd": 20,
            "day_committed_usd": daily / UNITS_PER_USD,
            "month_committed_usd": monthly / UNITS_PER_USD,
            "blocked": bool(blocked),
            "note": "Conservative reservations, not a bill; accounting starts at initialization.",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "status"))
    parser.add_argument("--path", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "init":
            initialize(args.path)
        print(json.dumps(status(args.path), indent=2))
    except RecurringBudgetError as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
