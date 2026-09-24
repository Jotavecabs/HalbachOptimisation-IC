"""Comparação do modelo de dipolo com soluções analíticas.

1. Anel de N dipolos Halbach k = 2 de raio r, deslocado de z do ponto
   avaliado. Somando os N dipolos, as partes que dependem de 2θ se cancelam
   (N > 2) e sobra, no eixo:

       |B| = mu0/(4 pi) * 3 m N r² / (2 d^5),  com d = sqrt(r² + z²),

   apontando na direção de B0. Em z = 0 isso vira 3 N mu0 m / (8 pi r³).

2. Cilindro Halbach contínuo k = 2 (raios ri, ro, comprimento L), no centro.
   Integrando a fórmula acima com m N -> M * 2 pi r dr dz:

       B = (Br/2) * ∫_{ri}^{ro} h (2h² + 3r²) / (r (r² + h²)^{3/2}) dr,  h = L/2,

   que para L -> infinito tende ao resultado clássico B = Br * ln(ro/ri).
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.integrate import quad

from halbach_ic.field_model import DipoleBackend
from halbach_ic.geometry import MU0, HalbachRing, MagnetArray, MagnetSpec

MAGNET = MagnetSpec(size=0.012, remanence=1.3, density=7500.0)
ORIGIN = np.zeros((1, 3))


def ring_on_axis_field(n: int, radius: float, z: float, moment: float) -> float:
    """Módulo analítico de B no eixo para um anel Halbach k = 2 de dipolos."""
    d = math.hypot(radius, z)
    return MU0 / (4 * math.pi) * 3 * moment * n * radius**2 / (2 * d**5)


def finite_cylinder_center_field(br: float, ri: float, ro: float, length: float) -> float:
    """Campo no centro de um cilindro Halbach k = 2 contínuo de comprimento finito."""
    h = length / 2
    integrand = lambda r: h * (2 * h**2 + 3 * r**2) / (r * (r**2 + h**2) ** 1.5)  # noqa: E731
    return br / 2 * quad(integrand, ri, ro)[0]


@pytest.mark.parametrize("n", [3, 8, 50, 51])
@pytest.mark.parametrize("z", [0.0, 0.03, -0.1])
def test_single_ring_matches_analytic(n: int, z: float) -> None:
    ring = HalbachRing(
        bore_radius=0.14, magnet=MAGNET, n_bands=1, band_gap=0.0, magnet_gap=0.0,
        field_direction=0.3, n_magnets_override=(n,),
    )
    b = DipoleBackend().field(ORIGIN, ring.magnets(z))[0]
    expected = ring_on_axis_field(n, ring.band_radii[0], z, MAGNET.dipole_moment)
    assert np.linalg.norm(b) == pytest.approx(expected, rel=1e-12)


def test_finite_formula_tends_to_infinite_cylinder() -> None:
    assert finite_cylinder_center_field(1.3, 0.1, 0.15, 1e4) == pytest.approx(1.3 * math.log(1.5), rel=1e-6)


@pytest.mark.parametrize("length", [0.1, 0.4, 2.0])
def test_discretized_continuous_cylinder(length: float) -> None:
    """Cilindro contínuo discretizado em muitos dipolos pequenos converge para a solução analítica."""
    br, ri, ro = 1.3, 0.05, 0.08
    nr, nz, n_theta = 30, 400, 16
    dr, dz = (ro - ri) / nr, length / nz
    backend = DipoleBackend()
    total = np.zeros(3)
    for r in ri + dr * (np.arange(nr) + 0.5):
        volume = 2 * math.pi * r * dr * dz / n_theta
        spec = MagnetSpec(size=volume ** (1 / 3), remanence=br, density=1.0)
        theta = 2 * math.pi * np.arange(n_theta) / n_theta
        for z in -length / 2 + dz * (np.arange(nz) + 0.5):
            positions = np.stack([r * np.cos(theta), r * np.sin(theta), np.full_like(theta, z)], axis=1)
            total += backend.field(ORIGIN, MagnetArray(spec, positions, 2 * theta))[0]
    expected = finite_cylinder_center_field(br, ri, ro, length)
    assert total[0] == pytest.approx(expected, rel=1e-3)
    assert abs(total[1]) < 1e-9 * expected
