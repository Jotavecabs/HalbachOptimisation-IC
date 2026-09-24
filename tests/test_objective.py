"""Testes da grade, da tabela de campos e da função objetivo."""

from __future__ import annotations

import math

import numpy as np
import pytest

from halbach_ic.domain import make_grid
from halbach_ic.field_model import DipoleBackend
from halbach_ic.geometry import Design, MagnetSpec, build_design_space
from halbach_ic.objective import Objective, build_field_table, field_unit_vector, homogeneity_ppm

MAGNET = MagnetSpec(size=0.012, remanence=1.3, density=7500.0)


@pytest.fixture(scope="module")
def space():
    return build_design_space(
        magnet=MAGNET, bore_radius_candidates=(0.12, 0.14, 0.16), n_bands=2, band_gap=0.004, magnet_gap=0.0015,
        field_direction=-math.pi / 2, angle_offset=0.0, n_rings=5, ring_spacing=0.022, axial_gap=0.001,
        min_bore_diameter=0.0,
    )


def test_grid_points() -> None:
    grid = make_grid(0.2, 0.005)
    assert grid.axis.size == 41
    full, octant = grid.points("full"), grid.points("octant")
    assert np.all(np.linalg.norm(full, axis=1) <= 0.1 + 1e-12)
    assert np.all(octant >= 0)
    assert grid.mask("full").sum() > 7 * grid.mask("octant").sum() > 0
    assert any(np.allclose(p, [0.1, 0, 0]) for p in full)


def test_homogeneity_ppm() -> None:
    assert homogeneity_ppm(np.array([0.05, 0.05001, 0.04999])) == pytest.approx(400.0)


def test_table_sum_equals_direct_field(space) -> None:
    points = make_grid(0.08, 0.02).points("full")
    table = build_field_table(space, points, DipoleBackend(), -math.pi / 2)
    genes = (2, 0, 1)
    direct = DipoleBackend().field(points, Design(space, genes).magnets()) @ field_unit_vector(-math.pi / 2)
    np.testing.assert_allclose(table.total_field(genes), direct, rtol=1e-6)


def test_constraint_violation(space) -> None:
    points = make_grid(0.08, 0.02).points("full")
    table = build_field_table(space, points, DipoleBackend(), -math.pi / 2)
    genes = (1, 1, 1)
    mean = float(np.mean(table.total_field(genes)))
    mass = Design(space, genes).mass

    def objective(target: float, tol: float, max_mass: float) -> Objective:
        return Objective(table=table, mass_table=space.mass_table(), target_field=target,
                         field_tolerance=tol, max_mass=max_mass)

    ok = objective(mean, 1e-3, 2 * mass).evaluate(genes)
    assert ok.feasible and ok.mean_field == pytest.approx(mean) and ok.mass == pytest.approx(mass)
    # campo 3 tolerâncias acima da faixa -> violação 2 (1 tolerância é a própria faixa)
    far = objective(mean - 3e-3, 1e-3, 2 * mass).evaluate(genes)
    assert far.violation == pytest.approx(2.0, rel=1e-6)
    heavy = objective(mean, 1e-3, mass / 2).evaluate(genes)
    assert heavy.violation == pytest.approx(1.0)


def test_octant_with_weights_equals_full_sphere(space) -> None:
    """Item 6: com pesos de multiplicidade, o octante reproduz a esfera inteira."""
    grid = make_grid(0.1, 0.01)
    full = build_field_table(space, grid.points("full"), DipoleBackend(), -math.pi / 2, grid.weights("full"))
    octant = build_field_table(space, grid.points("octant"), DipoleBackend(), -math.pi / 2, grid.weights("octant"))
    assert grid.weights("octant").sum() == pytest.approx(grid.mask("full").sum())
    for genes in [(0, 0, 0), (2, 1, 0), (1, 2, 2)]:
        f, o = full.total_field(genes), octant.total_field(genes)
        assert np.average(o, weights=octant.weights) == pytest.approx(np.mean(f), rel=1e-9)
        assert homogeneity_ppm(o, octant.weights) == pytest.approx(homogeneity_ppm(f), rel=1e-5)
        # sem pesos (como no original) a média fica enviesada
        assert np.mean(o) != pytest.approx(np.mean(f), rel=1e-9)
