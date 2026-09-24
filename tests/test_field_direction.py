"""A direção de B0 precisa corresponder a ``field_direction``."""

from __future__ import annotations

import math

import numpy as np
import pytest

from halbach_ic.domain import make_grid
from halbach_ic.field_model import DipoleBackend, get_backend
from halbach_ic.geometry import Design, HalbachRing, MagnetSpec, build_design_space

MAGNET = MagnetSpec(size=0.012, remanence=1.3, density=7500.0)


@pytest.mark.parametrize("direction_deg", [0.0, 90.0, -90.0, 37.0, 180.0])
@pytest.mark.parametrize("offset", [0.0, 0.7])
@pytest.mark.parametrize("n_override", [None, (49, 57)])
@pytest.mark.parametrize("backend", ["dipole", "cuboid"])
def test_center_field_points_along_field_direction(
    direction_deg: float, offset: float, n_override: tuple[int, int] | None, backend: str
) -> None:
    direction = math.radians(direction_deg)
    ring = HalbachRing(
        bore_radius=0.14, magnet=MAGNET, n_bands=2, band_gap=0.004, magnet_gap=0.0015,
        field_direction=direction, angle_offset=offset, n_magnets_override=n_override,
    )
    b = get_backend(backend).field(np.zeros((1, 3)), ring.magnets(0.0))[0]
    unit = np.array([math.cos(direction), math.sin(direction), 0.0])
    assert b @ unit > 0
    assert np.linalg.norm(b - (b @ unit) * unit) < 1e-10 * np.linalg.norm(b)


@pytest.mark.parametrize("backend", ["dipole", "cuboid"])
def test_vertical_top_to_bottom_is_minus_y(backend: str) -> None:
    """Requisito do projeto: field_direction = -90° gera B0 de cima para baixo (-y)."""
    space = build_design_space(
        magnet=MAGNET, bore_radius_candidates=(0.14, 0.16), n_bands=2, band_gap=0.004, magnet_gap=0.0015,
        field_direction=-math.pi / 2, angle_offset=0.0, n_rings=7, ring_spacing=0.022, axial_gap=0.001,
        min_bore_diameter=0.0,
    )
    design = Design(space, (0, 1, 0, 1))
    grid = make_grid(0.1, 0.01)
    model = get_backend(backend)
    b = model.field(grid.points("full"), design.magnets())
    assert np.all(b[:, 1] < 0), "B0 deve apontar para -y em todo o DSV"
    center = model.field(np.zeros((1, 3)), design.magnets())[0]
    assert abs(center[0]) < 1e-10 * abs(center[1])
    assert abs(center[2]) < 1e-10 * abs(center[1])
    # fora do centro o campo é quase vertical (desvio pequeno)
    assert np.max(np.abs(b[:, 0]) / np.abs(b[:, 1])) < 0.05


def test_phase_convention_is_opposite_to_field_direction() -> None:
    """Magnetização em ``2*theta + phase`` gera B0 em ``-phase`` (não em ``+phase``).

    Por isso usar ``phase = -90°`` diretamente daria campo para CIMA (+y).
    O código recebe a direção desejada de B0 e calcula ``phase = -direction``.
    """
    from halbach_ic.geometry import MagnetArray

    n, r = 48, 0.15
    theta = 2 * math.pi * np.arange(n) / n
    positions = np.stack([r * np.cos(theta), r * np.sin(theta), np.zeros(n)], axis=1)
    phase = -math.pi / 2
    b = DipoleBackend().field(np.zeros((1, 3)), MagnetArray(MAGNET, positions, 2 * theta + phase))[0]
    assert b[1] > 0 and abs(b[0]) < 1e-10 * b[1]
