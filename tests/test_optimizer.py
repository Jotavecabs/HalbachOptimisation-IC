"""Testes do algoritmo genético."""

from __future__ import annotations

import math
import random

import pytest
from deap import tools

from halbach_ic.config import GAConfig
from halbach_ic.domain import make_grid
from halbach_ic.field_model import DipoleBackend
from halbach_ic.geometry import MagnetSpec, build_design_space
from halbach_ic.objective import Objective, build_field_table
from halbach_ic.optimizer import run_ga

MAGNET = MagnetSpec(size=0.012, remanence=1.3, density=7500.0)


def test_legacy_mutflipbit_collapses_integer_genes() -> None:
    """Bug 1: mutFlipBit em genes inteiros só produz 0 ou 1."""
    random.seed(0)
    genes = [17] * 1000
    tools.mutFlipBit(genes, indpb=0.5)
    assert set(genes) == {0, 17}
    genes = [0] * 1000
    tools.mutFlipBit(genes, indpb=0.5)
    assert set(genes) == {0, 1}


def test_mut_uniform_int_covers_all_options() -> None:
    random.seed(0)
    genes = [5] * 5000
    tools.mutUniformInt(genes, low=0, up=18, indpb=1.0)
    assert set(genes) == set(range(19))


@pytest.fixture(scope="module")
def objective_and_space():
    space = build_design_space(
        magnet=MAGNET, bore_radius_candidates=tuple(0.14 + 0.003 * i for i in range(8)), n_bands=2,
        band_gap=0.004, magnet_gap=0.0015, field_direction=-math.pi / 2, angle_offset=0.0, n_rings=9,
        ring_spacing=0.022, axial_gap=0.001, min_bore_diameter=0.0,
    )
    grid = make_grid(0.1, 0.01)
    table = build_field_table(space, grid.points("octant"), DipoleBackend(), -math.pi / 2, grid.weights("octant"))
    return space, table


def _cfg(seed: int | None = 1) -> GAConfig:
    return GAConfig(population=200, generations=15, crossover_prob=0.55, mutation_prob=0.4,
                    gene_mutation_prob=0.05, tournament_size=3, seed=seed)


def test_ga_reaches_feasible_region_and_is_reproducible(objective_and_space) -> None:
    space, table = objective_and_space
    mean_min = min(table.total_field([0] * space.n_slots).mean(), table.total_field([7] * space.n_slots).mean())
    mean_max = max(table.total_field([0] * space.n_slots).mean(), table.total_field([7] * space.n_slots).mean())
    target = (mean_min + mean_max) / 2
    objective = Objective(table=table, mass_table=space.mass_table(), target_field=target,
                          field_tolerance=0.02 * target, max_mass=1e3)
    first = run_ga(objective, space.n_slots, space.n_options, _cfg())
    second = run_ga(objective, space.n_slots, space.n_options, _cfg())
    assert first.best.feasible
    assert first.best_genes == second.best_genes
    assert all(0 <= g < space.n_options for g in first.best_genes)
    assert len(first.history) == 15
    # o melhor global nunca é pior que o melhor de qualquer geração
    assert first.best.ppm <= min(h.best_ppm for h in first.history if h.best_violation == 0) + 1e-9


def test_ga_prefers_smaller_violation_when_infeasible(objective_and_space) -> None:
    space, table = objective_and_space
    objective = Objective(table=table, mass_table=space.mass_table(), target_field=1.0,
                          field_tolerance=1e-3, max_mass=1e3)
    result = run_ga(objective, space.n_slots, space.n_options, _cfg())
    # alvo inalcançável (1 T): o GA deve ir para o maior campo possível
    assert not result.best.feasible
    assert result.best_genes == (0,) * space.n_slots
