from __future__ import annotations

import multiprocessing
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from psbx import recurring_budget as budget
from psbx import spending
from psbx.schemas import ModelConfig

UTC = timezone.utc
START = datetime(2026, 10, 1, 4, tzinfo=UTC)


def _reserve_worker(item):
    path, index = item
    try:
        budget.reserve(Path(path), f"request-{index}", f"run-{index}", "0.1", now=START)
        return True
    except budget.RecurringBudgetError:
        return False


@pytest.fixture
def ledger(tmp_path):
    path = tmp_path / "budget.sqlite3"
    budget.initialize(path, now=START)
    return path


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for name in ("PSBX_RECURRING_BUDGET_PATH", "PSBX_ROUTINE_LIVE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def model():
    return ModelConfig(
        id="budget-test", provider="openrouter", model_name="test/model",
        declared_pretraining_cutoff="2024-01-01", is_instruction_tuned=True,
        cost_per_1k_input=0.001, cost_per_1k_output=0.002, max_tokens=100,
    )


def test_parallel_processes_and_run_ids_share_one_limit(ledger):
    with multiprocessing.get_context("spawn").Pool(4) as pool:
        results = pool.map(_reserve_worker, [(str(ledger), n) for n in range(24)])
    assert sum(results) == 10
    assert budget.status(ledger, now=START)["day_committed_usd"] == 1


def test_daily_limit_persists_across_new_run_and_restart(ledger):
    budget.reserve(ledger, "first", "run-one", 1, now=START)
    with pytest.raises(budget.RecurringBudgetError, match="exhausted"):
        budget.reserve(Path(str(ledger)), "second", "different-run", "0.000001", now=START)
    budget.reserve(ledger, "tomorrow", "run-two", 1, now=START + timedelta(days=1))
    assert budget.status(ledger, now=START + timedelta(days=1))["month_committed_usd"] == 2


def test_monthly_limit_survives_day_changes_and_resets_only_calendar_month(ledger):
    for day in range(20):
        budget.reserve(ledger, str(day), "different-run", 1, now=START + timedelta(days=day))
    with pytest.raises(budget.RecurringBudgetError, match="exhausted"):
        budget.reserve(ledger, "21", "next", "0.01", now=START + timedelta(days=20))
    # 03:59 UTC November 1 is still October in New York.
    with pytest.raises(budget.RecurringBudgetError, match="exhausted"):
        budget.reserve(ledger, "early", "next", "0.01", now=datetime(2026, 11, 1, 3, 59, tzinfo=UTC))
    budget.reserve(ledger, "nov", "next", 1, now=datetime(2026, 11, 1, 4, tzinfo=UTC))
    assert budget.status(ledger, now=datetime(2026, 11, 1, 4, tzinfo=UTC))["month_committed_usd"] == 1


def test_day_boundary_uses_new_york_and_dst(ledger):
    before = datetime(2026, 11, 2, 4, 59, tzinfo=UTC)
    after = datetime(2026, 11, 2, 5, 0, tzinfo=UTC)
    budget.reserve(ledger, "first", "run", 1, now=before)
    assert budget.status(ledger, now=before)["day"] == "2026-11-01"
    budget.reserve(ledger, "second", "run", 1, now=after)
    assert budget.status(ledger, now=after)["day"] == "2026-11-02"


def test_conservative_rounding_and_duplicate_reservations(ledger):
    budget.reserve(ledger, "same-id", "run", "0.9999999991", now=START)
    assert budget.status(ledger, now=START)["day_committed_usd"] == 1
    with pytest.raises(budget.RecurringBudgetError, match="duplicate"):
        budget.reserve(ledger, "same-id", "another-run", "0.9999999991", now=START)
    with pytest.raises(budget.RecurringBudgetError, match="exhausted"):
        budget.reserve(ledger, "new-id", "run", "0.0000000001", now=START)


def test_unknown_charges_and_lower_actuals_do_not_refund(ledger):
    budget.reserve(ledger, "unknown", "failed-process", "0.5", now=START)
    budget.reserve(ledger, "success", "run", "0.5", now=START)
    budget.record_actual(ledger, "success", "0.01")
    budget.record_actual(ledger, "success", "0")
    assert budget.status(ledger, now=START)["day_committed_usd"] == 1
    with pytest.raises(budget.RecurringBudgetError, match="exhausted"):
        budget.reserve(ledger, "extra", "run", "0.01", now=START)


def test_actual_overrun_is_recorded_and_blocks_future_days(ledger):
    budget.reserve(ledger, "request", "run", "0.1", now=START)
    budget.record_actual(ledger, "request", "0.1000000001")
    result = budget.status(ledger, now=START)
    assert result["blocked"] is True
    assert result["day_committed_usd"] == pytest.approx(0.100000001)
    budget.record_actual(ledger, "request", "0.01")
    with pytest.raises(budget.RecurringBudgetError, match="halted"):
        budget.reserve(ledger, "another", "new-run", "0.01", now=START + timedelta(days=40))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), -0.01, "bad", None])
def test_invalid_cost_never_creates_or_updates_a_reservation(ledger, value):
    with pytest.raises(budget.RecurringBudgetError, match="finite"):
        budget.reserve(ledger, "invalid", "run", value, now=START)
    budget.reserve(ledger, "valid", "run", "0.2", now=START)
    with pytest.raises(budget.RecurringBudgetError, match="finite"):
        budget.record_actual(ledger, "valid", value)
    assert budget.status(ledger, now=START)["day_committed_usd"] == 0.2


def test_missing_corrupt_and_foreign_databases_fail_closed(tmp_path):
    path = tmp_path / "missing.sqlite3"
    with pytest.raises(budget.RecurringBudgetError):
        budget.reserve(path, "r", "run", "0.1")
    assert not path.exists()
    path.write_bytes(b"not a sqlite database")
    for operation in (lambda: budget.status(path), lambda: budget.initialize(path)):
        with pytest.raises(budget.RecurringBudgetError):
            operation()
    assert path.read_bytes() == b"not a sqlite database"
    other = tmp_path / "foreign.sqlite3"
    with sqlite3.connect(other) as db:
        db.execute("CREATE TABLE unrelated(value TEXT)")
    with pytest.raises(budget.RecurringBudgetError):
        budget.reserve(other, "r", "run", "0.1")


@pytest.mark.parametrize("mutation", [
    "UPDATE policy SET daily_units=2000000000",
    "UPDATE policy SET monthly_units=21000000000",
    "UPDATE policy SET timezone='UTC'",
    "PRAGMA user_version=2",
    "ALTER TABLE reservations RENAME COLUMN actual_units TO unknown_column",
])
def test_modified_schema_or_policy_cannot_authorize_calls(ledger, mutation):
    with sqlite3.connect(ledger) as db:
        db.execute(mutation)
    with pytest.raises(budget.RecurringBudgetError):
        budget.reserve(ledger, "r", "run", "0.1", now=START)


def test_initialization_is_exclusive_and_not_retrospective(ledger):
    with pytest.raises(budget.RecurringBudgetError, match="new writable path"):
        budget.initialize(ledger)
    with pytest.raises(budget.RecurringBudgetError, match="before initialization"):
        budget.reserve(ledger, "earlier", "run", "0.1", now=START - timedelta(seconds=1))
    assert budget.status(ledger, now=START)["initialized_at"] == START.isoformat()


def test_paid_guard_requires_config_for_routine_before_network(model, monkeypatch):
    monkeypatch.setenv("PSBX_ENABLE_PAID_MODELS", "1")
    monkeypatch.setenv("PSBX_ROUTINE_LIVE", "1")
    with pytest.raises(spending.SpendGuardError, match="PSBX_RECURRING_BUDGET_PATH"):
        spending._SpendGuard().reserve(model, {"messages": []})
    with pytest.raises(spending.SpendGuardError, match="PSBX_RECURRING_BUDGET_PATH"):
        spending.preflight_paid_requests([(model, 1)])


def test_nonroutine_reservation_behavior_is_unchanged(model, monkeypatch):
    monkeypatch.setenv("PSBX_ENABLE_PAID_MODELS", "1")
    guard = spending._SpendGuard()
    reservation = guard.reserve(model, {"messages": []})
    assert reservation.recurring_budget_path is None
    guard.record_usage(reservation, {"cost": 0.00001}, model)
    assert guard._request_count == 1


def test_integration_keeps_budget_path_and_blocks_overrun(model, ledger, monkeypatch):
    monkeypatch.setenv("PSBX_ENABLE_PAID_MODELS", "1")
    monkeypatch.setenv("PSBX_RECURRING_BUDGET_PATH", str(ledger))
    guard = spending._SpendGuard()
    reservation = guard.reserve(model, {"messages": ["DO-NOT-STORE-PAYLOAD"]})
    assert reservation.recurring_budget_path == ledger
    monkeypatch.delenv("PSBX_RECURRING_BUDGET_PATH")
    guard.record_usage(reservation, {"cost": reservation.estimated_usd + 0.01}, model)
    assert budget.status(ledger)["blocked"] is True
    monkeypatch.setenv("PSBX_RECURRING_BUDGET_PATH", str(ledger))
    with pytest.raises(spending.SpendGuardError, match="halted"):
        spending._SpendGuard().reserve(model, {"messages": []})
    assert b"DO-NOT-STORE-PAYLOAD" not in ledger.read_bytes()


def test_relative_environment_path_is_rejected(monkeypatch):
    monkeypatch.setenv("PSBX_RECURRING_BUDGET_PATH", "budget.sqlite3")
    with pytest.raises(budget.RecurringBudgetError, match="absolute"):
        budget.configured_path()


def test_unknown_reservation_usage_is_rejected(ledger):
    with pytest.raises(budget.RecurringBudgetError, match="no recurring reservation"):
        budget.record_actual(ledger, "unknown", 0.01)
