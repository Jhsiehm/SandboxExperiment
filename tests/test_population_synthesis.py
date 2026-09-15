import pandas as pd

from psbx.population.compress import allocate_reasoning_budget, compress_population
from psbx.population.constraints import load_constraints, validate_constraints
from psbx.population.donors import filter_to_universe, load_donors, validate_donor_support
from psbx.population.runner import load_population_spec
from psbx.population.synthesize import build_synthetic_population


def _build():
    spec = load_population_spec("config/track_b_fixture.yaml")
    constraints = load_constraints(spec.constraints_path)
    validate_constraints(spec, constraints)
    donors = filter_to_universe(load_donors(spec.donors_path), spec.universe)
    validate_donor_support(donors, constraints)
    population, raking = build_synthetic_population(donors, constraints, spec)
    return spec, constraints, population, raking


def test_population_count_is_exact_and_ids_are_unique():
    spec, _, population, raking = _build()
    assert len(population) == spec.target_population
    assert population["synthetic_person_id"].is_unique
    assert raking.history[-1].max_relative_error <= spec.tolerance


def test_population_build_is_deterministic_for_seed():
    _, _, first, _ = _build()
    _, _, second, _ = _build()
    pd.testing.assert_frame_equal(first, second)


def test_representative_cells_and_reasoning_budget_are_separate():
    spec, _, population, _ = _build()
    cells = compress_population(population, spec.representative_cell_fields)
    allocated = allocate_reasoning_budget(cells, spec.reasoning_call_budget)
    assert allocated["population_weight"].sum() == spec.target_population
    assert allocated["reasoning_calls"].sum() == spec.reasoning_call_budget
    assert spec.target_population != spec.reasoning_call_budget
