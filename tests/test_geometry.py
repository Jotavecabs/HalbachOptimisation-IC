"""Testes de geometria: número de ímãs, sobreposição e recusa de configurações inviáveis."""

from __future__ import annotations

import math

import numpy as np
import pytest

from halbach_ic.geometry import (
    Design,
    HalbachRing,
    InfeasibleGeometryError,
    MagnetSpec,
    build_design_space,
    max_magnets_on_circle,
    squares_overlap,
    symmetric_slots,
)

MAGNET = MagnetSpec(size=0.012, remanence=1.3, density=7500.0)


def ring(bore: float, **kwargs: object) -> HalbachRing:
    params: dict[str, object] = dict(
        bore_radius=bore, magnet=MAGNET, n_bands=2, band_gap=0.004, magnet_gap=0.0015, field_direction=-math.pi / 2
    )
    params.update(kwargs)
    return HalbachRing(**params)  # type: ignore[arg-type]


def test_squares_overlap_basic_cases() -> None:
    a = np.array([0.0, 0.0])
    assert squares_overlap(a, 0.0, np.array([0.011, 0.0]), 0.0, 0.012)
    assert not squares_overlap(a, 0.0, np.array([0.0121, 0.0]), 0.0, 0.012)
    # girado 45°: a meia diagonal é 8.49 mm, então a 14 mm encosta, a 14.6 mm não
    assert squares_overlap(a, math.pi / 4, np.array([0.014, 0.0]), 0.0, 0.012)
    assert not squares_overlap(a, math.pi / 4, np.array([0.0146, 0.0]), 0.0, 0.012)


def test_max_magnets_respects_chord() -> None:
    footprint, gap = MAGNET.footprint_diameter, 0.0015
    for radius in np.linspace(0.05, 0.3, 40):
        n = max_magnets_on_circle(radius, footprint, gap)
        assert 2 * radius * math.sin(math.pi / n) >= footprint + gap - 1e-12
        assert 2 * radius * math.sin(math.pi / (n + 1)) < footprint + gap


def test_computed_count_matches_original_lumc_design() -> None:
    # O original usa 50 ímãs internos em r = 148 mm e 57 externos em r = 169 mm.
    r = ring(0.148 - MAGNET.footprint_diameter / 2, band_gap=0.021 - MAGNET.footprint_diameter)
    assert r.band_radii == pytest.approx((0.148, 0.169))
    assert r.n_magnets == (50, 57)


@pytest.mark.parametrize("bore", np.linspace(0.06, 0.2, 15))
@pytest.mark.parametrize("n_bands", [1, 2, 3])
@pytest.mark.parametrize("offset", [0.0, 0.3, math.pi])
def test_generated_rings_never_overlap(bore: float, n_bands: int, offset: float) -> None:
    r = ring(bore, n_bands=n_bands, angle_offset=offset, magnet_gap=0.0)
    assert not r.has_overlap()


def test_bore_is_respected() -> None:
    r = ring(0.14)
    arr = r.magnets()
    # distância exata do eixo até o ponto mais próximo de cada cubo girado
    radial = np.hypot(arr.positions[:, 0], arr.positions[:, 1])
    alpha = arr.angles - np.arctan2(arr.positions[:, 1], arr.positions[:, 0])
    closest = radial - MAGNET.size / 2 * (np.abs(np.cos(alpha)) + np.abs(np.sin(alpha)))
    assert closest.min() >= r.bore_radius - 1e-12


def test_too_many_magnets_is_refused() -> None:
    n_max = ring(0.14).n_magnets
    with pytest.raises(InfeasibleGeometryError, match="não cabem"):
        ring(0.14, n_magnets_override=(n_max[0] + 1, n_max[1]))
    assert ring(0.14, n_magnets_override=(n_max[0] - 4, n_max[1])).n_magnets[0] == n_max[0] - 4


def test_bore_too_small_is_refused() -> None:
    with pytest.raises(InfeasibleGeometryError):
        ring(0.001)


def test_negative_gap_is_refused() -> None:
    with pytest.raises(InfeasibleGeometryError):
        ring(0.14, magnet_gap=-0.001)


def _space(**overrides: object):
    params: dict[str, object] = dict(
        magnet=MAGNET,
        bore_radius_candidates=(0.12, 0.14, 0.16),
        n_bands=2,
        band_gap=0.004,
        magnet_gap=0.0015,
        field_direction=-math.pi / 2,
        angle_offset=0.0,
        n_rings=5,
        ring_spacing=0.022,
        axial_gap=0.001,
        min_bore_diameter=0.0,
    )
    params.update(overrides)
    return build_design_space(**params)  # type: ignore[arg-type]


def test_axial_overlap_is_refused() -> None:
    with pytest.raises(InfeasibleGeometryError, match="espaçamento"):
        _space(ring_spacing=0.0125)


def test_min_bore_filters_candidates() -> None:
    space = _space(min_bore_diameter=0.27)
    assert [o.bore_radius for o in space.options] == [0.14, 0.16]
    assert len(space.rejected) == 1


def test_symmetric_slots() -> None:
    assert symmetric_slots(5, 0.02) == ((0.0,), (-0.02, 0.02), (-0.04, 0.04))
    assert np.allclose(symmetric_slots(4, 0.02), ((-0.01, 0.01), (-0.03, 0.03)))


def test_design_mass_and_rings() -> None:
    space = _space()
    design = Design(space, (0, 1, 2))
    zs = [z for z, _ in design.rings()]
    assert zs == pytest.approx([-0.044, -0.022, 0.0, 0.022, 0.044])
    expected = space.options[0].mass + 2 * space.options[1].mass + 2 * space.options[2].mass
    assert design.mass == pytest.approx(expected)
    assert design.mass == pytest.approx(space.mass_table()[np.arange(3), [0, 1, 2]].sum())
    assert design.free_bore_diameter == pytest.approx(0.24)
    with pytest.raises(ValueError):
        Design(space, (0, 1, 3))
