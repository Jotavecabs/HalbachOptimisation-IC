"""Testes da Fase 3: avaliação vetorizada, operadores do GA em NumPy, paralelismo e memória."""

from __future__ import annotations

import math

import numpy as np
import pytest

from halbach_ic.domain import make_grid
from halbach_ic.evaluator import ParallelEvaluator
from halbach_ic.field_model import CuboidBackend, DipoleBackend
from halbach_ic.geometry import Design, MagnetSpec, build_design_space
from halbach_ic.memory import InsufficientMemoryError, check_memory, estimate_memory
from halbach_ic.objective import Objective, build_field_table, homogeneity_ppm
from halbach_ic.optimizer import (
    lexicographic_rank,
    tournament_selection,
    two_point_crossover,
    uniform_int_mutation,
)
from halbach_ic.parallel import SharedArray, attach_shared, compute_field

MAGNET = MagnetSpec(size=0.012, remanence=1.3, density=7500.0)


@pytest.fixture(scope="module")
def space():
    return build_design_space(
        magnet=MAGNET, bore_radius_candidates=tuple(0.14 + 0.003 * i for i in range(6)), n_bands=2,
        band_gap=0.004, magnet_gap=0.0015, field_direction=-math.pi / 2, angle_offset=0.0, n_rings=9,
        ring_spacing=0.022, axial_gap=0.001, min_bore_diameter=0.0,
    )


@pytest.fixture(scope="module")
def grid():
    return make_grid(0.1, 0.01)


@pytest.fixture(scope="module")
def objective(space, grid):
    table = build_field_table(space, grid.points("octant"), DipoleBackend(), -math.pi / 2, grid.weights("octant"))
    return Objective(table=table, mass_table=space.mass_table(), target_field=0.05, field_tolerance=0.001,
                     max_mass=10.0)


def _reference(objective: Objective, genes) -> tuple[float, float, float, float]:
    """Avaliação de uma solução pela fórmula direta (sem vetorização)."""
    field = objective.table.total_field(genes)
    mean = float(np.average(field, weights=objective.table.weights))
    mass = float(objective.mass_table[np.arange(len(genes)), genes].sum())
    violation = (max(0.0, abs(mean - objective.target_field) - objective.field_tolerance) / objective.field_tolerance
                 + max(0.0, mass - objective.max_mass) / objective.max_mass)
    return homogeneity_ppm(field, objective.table.weights), mean, mass, violation


@pytest.mark.parametrize("chunk_bytes", [64 * 2**20, 3000])
def test_batch_evaluation_matches_reference(objective, space, chunk_bytes: int) -> None:
    obj = Objective(table=objective.table, mass_table=objective.mass_table, target_field=objective.target_field,
                    field_tolerance=objective.field_tolerance, max_mass=objective.max_mass, chunk_bytes=chunk_bytes)
    genes = np.random.default_rng(0).integers(0, space.n_options, (57, space.n_slots))
    batch = obj.evaluate_batch(genes)
    for i, row in enumerate(genes):
        ppm, mean, mass, violation = _reference(obj, row)
        assert batch.ppm[i] == pytest.approx(ppm, rel=1e-9)
        assert batch.mean_field[i] == pytest.approx(mean, rel=1e-12)
        assert batch.mass[i] == pytest.approx(mass)
        assert batch.violation[i] == pytest.approx(violation, rel=1e-9, abs=1e-12)


def test_lexicographic_rank() -> None:
    violation = np.array([0.0, 1.0, 0.0, 0.5])
    ppm = np.array([30.0, 1.0, 10.0, 5.0])
    assert list(lexicographic_rank(violation, ppm)) == [1, 3, 0, 2]


def test_tournament_prefers_better_rank() -> None:
    rng = np.random.default_rng(0)
    rank = np.array([3, 0, 2, 1])
    assert set(tournament_selection(rng, rank, k=1, n=2000)) == {0, 1, 2, 3}
    winners = tournament_selection(rng, rank, k=40, n=2000)
    assert np.mean(winners == 1) > 0.97


def test_two_point_crossover_swaps_one_segment() -> None:
    rng = np.random.default_rng(1)
    parents = np.stack([np.zeros(12, int), np.ones(12, int)] * 500)
    children = parents.copy()
    two_point_crossover(rng, children, prob=1.0)
    for a, b in zip(children[0::2], children[1::2]):
        np.testing.assert_array_equal(a + b, 1)  # cada posição veio de um dos pais
        changed = np.flatnonzero(a == 1)
        assert changed.size >= 1
        assert np.all(np.diff(changed) == 1)  # trecho contíguo
    untouched = parents.copy()
    two_point_crossover(rng, untouched, prob=0.0)
    np.testing.assert_array_equal(untouched, parents)


def test_uniform_int_mutation_range_and_rate() -> None:
    rng = np.random.default_rng(2)
    pop = np.full((4000, 12), 7)
    uniform_int_mutation(rng, pop, prob=0.4, gene_prob=0.05, n_options=19)
    assert pop.min() >= 0 and pop.max() <= 18
    assert set(np.unique(pop)) == set(range(19))
    changed_fraction = np.mean(pop != 7)
    assert changed_fraction == pytest.approx(0.4 * 0.05 * 18 / 19, rel=0.15)


def test_parallel_evaluator_matches_serial(objective, space) -> None:
    genes = np.random.default_rng(3).integers(0, space.n_options, (400, space.n_slots))
    serial = objective.evaluate_batch(genes)
    with ParallelEvaluator(objective, n_workers=2, min_rows_per_worker=10) as evaluate:
        parallel = evaluate(genes)
        small = evaluate(genes[:5])  # lote pequeno: avaliado no processo principal
    np.testing.assert_array_equal(parallel.ppm, serial.ppm)
    np.testing.assert_array_equal(parallel.violation, serial.violation)
    np.testing.assert_array_equal(small.ppm, serial.ppm[:5])


@pytest.mark.parametrize("backend", [DipoleBackend(), CuboidBackend()])
def test_parallel_precompute_matches_serial(space, grid, backend) -> None:
    points, weights = grid.points("octant"), grid.weights("octant")
    serial = build_field_table(space, points, backend, -math.pi / 2, weights, n_workers=1)
    parallel = build_field_table(space, points, backend, -math.pi / 2, weights, n_workers=3)
    np.testing.assert_array_equal(serial.values, parallel.values)


def test_parallel_field_matches_serial(space, grid) -> None:
    magnets = Design(space, (0,) * space.n_slots).magnets()
    points = grid.points("full")
    np.testing.assert_allclose(compute_field(points, magnets, DipoleBackend(), n_workers=2),
                               DipoleBackend().field(points, magnets), rtol=1e-12)


def test_shared_array_roundtrip() -> None:
    data = np.arange(24, dtype=np.float32).reshape(2, 3, 4)
    with SharedArray(data) as shared:
        shm, view = attach_shared(shared.spec)
        np.testing.assert_array_equal(view, data)
        shared.array[0, 0, 0] = -1
        assert view[0, 0, 0] == -1  # mesma memória, sem cópia
        del view
        shm.close()


def test_memory_estimate_and_check() -> None:
    est = estimate_memory(n_points=1000, n_slots=10, n_options=20, n_workers=2, chunk_bytes=2**20,
                          field_chunk_pairs=1000)
    assert est.table == 1000 * 10 * 20 * 4
    assert check_memory(est, available=100 * est.total) is None
    assert "AVISO" in check_memory(est, available=int(1.5 * est.total))
    with pytest.raises(InsufficientMemoryError, match="grid_spacing_mm"):
        check_memory(est, available=est.total // 2)
