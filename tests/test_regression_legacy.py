"""Regressão: o código novo reproduz o original (``legacy/``) quando configurado como ele.

O original tem duas diferenças de convenção que o teste precisa desfazer:

* Campo em +x (``field_direction = 0``).
* Bug 4: a malha deslocada coloca o ímã em ``-pos``. Isso equivale a girar o
  anel de 180° (``angle_offset = pi``) ou, de forma equivalente, a avaliar o
  campo correto no ponto ``-g`` (inversão pela origem).

O GA original não é reproduzível (sem semente e com o bug de mutação), então a
regressão compara o campo e o valor da função objetivo para vetores fixos.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from halbach_ic.domain import make_grid
from halbach_ic.field_model import DipoleBackend
from halbach_ic.geometry import DesignSpace, HalbachRing, MagnetSpec, symmetric_slots
from halbach_ic.objective import build_field_table, homogeneity_ppm

MAGNET = MagnetSpec(size=0.012, remanence=1.3, density=7500.0)
LEGACY_RADII = np.array([148, 151, 154, 156, 159, 162, 165, 168, 171, 174, 177, 180, 183, 186, 189, 192, 195, 198, 201]) * 1e-3
LEGACY_N_INNER = np.arange(50, 69)
LEGACY_BAND_PITCH = 0.021
RES_LEGACY = 100.0  # pontos por metro no original = grade de 10 mm
SIM = (0.2, 0.2, 0.2)


def legacy_ring(index: int, angle_offset: float) -> HalbachRing:
    """Anel equivalente à entrada ``index`` das tabelas do original (2 bandas)."""
    footprint = MAGNET.footprint_diameter
    return HalbachRing(
        bore_radius=LEGACY_RADII[index] - footprint / 2, magnet=MAGNET, n_bands=2,
        band_gap=LEGACY_BAND_PITCH - footprint, magnet_gap=0.0015, field_direction=0.0,
        angle_offset=angle_offset,
        n_magnets_override=(int(LEGACY_N_INNER[index]), int(LEGACY_N_INNER[index]) + 7),
    )


def legacy_grid_points() -> np.ndarray:
    """Pontos na mesma ordem dos arrays do original (meshgrid com indexação 'xy')."""
    axis = np.linspace(-0.1, 0.1, 21)
    x, y, z = np.meshgrid(axis, axis, axis)
    return np.stack([x.ravel(), y.ravel(), z.ravel()], axis=1)


@pytest.mark.parametrize("n", [50, 51])
@pytest.mark.parametrize("rings", [(0.0,), (-0.044, 0.044)])
def test_field_matches_legacy(legacy, n: int, rings: tuple[float, ...]) -> None:
    fields, _ = legacy
    radius = 0.148
    b_legacy = fields.createHalbach(
        numMagnets=n, rings=rings, radius=radius, magnetSize=0.012, resolution=RES_LEGACY, simDimensions=SIM
    ).reshape(-1, 3)
    points = legacy_grid_points()
    # só dentro do DSV: nos cantos da grade o ponto fica a < 1 cm do ímã, onde o dipolo não vale
    inside = np.linalg.norm(points, axis=1) <= 0.1 + 1e-12
    points, b_legacy = points[inside], b_legacy[inside]
    scale = np.abs(b_legacy).max()

    def ring(offset: float) -> HalbachRing:
        return HalbachRing(
            bore_radius=radius - MAGNET.footprint_diameter / 2, magnet=MAGNET, n_bands=1, band_gap=0.0,
            magnet_gap=0.0, field_direction=0.0, angle_offset=offset, n_magnets_override=(n,),
        )

    def field(offset: float, pts: np.ndarray) -> np.ndarray:
        from halbach_ic.geometry import MagnetArray

        magnets = MagnetArray.concatenate([ring(offset).magnets(z) for z in rings])
        return DipoleBackend().field(pts, magnets)

    # anel girado de 180° reproduz o original
    np.testing.assert_allclose(field(math.pi, points), b_legacy, atol=2e-6 * scale)
    # campo correto em -g também reproduz o original (bug 4 = inversão pela origem)
    np.testing.assert_allclose(field(0.0, -points), b_legacy, atol=2e-6 * scale)


def test_fitness_matches_legacy(legacy) -> None:
    fields, optimisation = legacy
    option_idx = [0, 7, 18]
    slots = symmetric_slots(23, 0.022)
    grid = make_grid(0.2, 0.01)

    # --- tabela como no original (mesmo laço de homogeneityOptimisation.py) ---
    axis = np.linspace(-0.1, 0.1, 21)
    coords = np.meshgrid(axis, axis, axis)
    mask = coords[0] ** 2 + coords[1] ** 2 + coords[2] ** 2 <= 0.1**2
    octant = mask & (coords[0] >= 0) & (coords[1] >= 0) & (coords[2] >= 0)
    legacy_table = np.zeros((int(octant.sum()), len(slots), len(option_idx)))
    for s, slot in enumerate(slots):
        for o, idx in enumerate(option_idx):
            b = fields.createHalbach(
                numMagnets=LEGACY_N_INNER[idx], rings=slot, radius=LEGACY_RADII[idx], magnetSize=0.012,
                resolution=RES_LEGACY, simDimensions=SIM,
            )
            b += fields.createHalbach(
                numMagnets=LEGACY_N_INNER[idx] + 7, rings=slot, radius=LEGACY_RADII[idx] + 0.021,
                magnetSize=0.012, resolution=RES_LEGACY, simDimensions=SIM,
            )
            legacy_table[:, s, o] = b[octant, 0]
    optimisation.sharedShimMagnetsFields = legacy_table

    # --- mesma instância no código novo ---
    space = DesignSpace(slots=slots, options=tuple(legacy_ring(i, math.pi) for i in option_idx))
    table = build_field_table(space, grid.points("octant"), DipoleBackend(), field_direction=0.0)

    assert table.n_points == legacy_table.shape[0]
    rng = np.random.default_rng(0)
    for genes in [np.zeros(len(slots), int), np.full(len(slots), 2), *rng.integers(0, 3, (5, len(slots)))]:
        legacy_ppm = optimisation.fieldError(list(genes))[0]
        # o original usa média simples no octante (sem pesos), então compara assim
        assert homogeneity_ppm(table.total_field(genes)) == pytest.approx(legacy_ppm, rel=1e-4)
