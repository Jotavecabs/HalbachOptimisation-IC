"""Testes dos modelos de campo (dipolo e cubo exato)."""

from __future__ import annotations

import math

import magpylib as magpy
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from halbach_ic.field_model import BACKEND_NAMES, CuboidBackend, DipoleBackend, get_backend
from halbach_ic.geometry import MagnetArray, MagnetSpec

MAGNET = MagnetSpec(size=0.012, remanence=1.3, density=7500.0)


def test_backends_are_registered() -> None:
    assert set(BACKEND_NAMES) == {"dipole", "cuboid"}
    assert get_backend("cuboid").name == "cuboid"
    with pytest.raises(ValueError):
        get_backend("fem")


def test_cuboid_matches_magpylib_object_api() -> None:
    """A rotação para o referencial local reproduz o Cuboid do magpylib com orientação."""
    rng = np.random.default_rng(0)
    positions = rng.normal(size=(6, 3)) * 0.1
    angles = rng.uniform(0, 2 * np.pi, 6)
    points = rng.normal(size=(40, 3)) * 0.05 + [0.4, 0.0, 0.0]
    ours = CuboidBackend().field(points, MagnetArray(MAGNET, positions, angles))
    collection = magpy.Collection(
        [
            magpy.magnet.Cuboid(
                polarization=(MAGNET.remanence, 0, 0), dimension=(MAGNET.size,) * 3,
                position=p, orientation=Rotation.from_euler("z", a),
            )
            for p, a in zip(positions, angles)
        ]
    )
    np.testing.assert_allclose(ours, magpy.getB(collection, points), rtol=1e-9, atol=1e-15)


@pytest.mark.parametrize("angle", [0.0, 0.4, math.pi / 4])
def test_cuboid_tends_to_dipole_far_away(angle: float) -> None:
    """Longe do ímã o cubo vira dipolo; o erro relativo cai como (a/r)^4 (primeira correção do cubo)."""
    magnet = MagnetArray(MAGNET, np.zeros((1, 3)), np.array([angle]))
    direction = np.array([0.6, 0.48, 0.64])
    errors = []
    for r in (0.1, 0.2, 0.4):
        point = (r * direction)[None, :]
        exact = CuboidBackend().field(point, magnet)
        dipole = DipoleBackend().field(point, magnet)
        errors.append(np.linalg.norm(exact - dipole) / np.linalg.norm(exact))
    assert errors[-1] < 1e-5
    slopes = np.log2(np.array(errors[:-1]) / np.array(errors[1:]))
    np.testing.assert_allclose(slopes, 4.0, atol=0.1)


def test_cuboid_moment_matches_dipole_moment_definition() -> None:
    """Ao longo do eixo de magnetização e longe, B -> mu0 m / (2 pi r^3) com m = Br V / mu0."""
    magnet = MagnetArray(MAGNET, np.zeros((1, 3)), np.array([0.0]))
    r = 2.0
    b = CuboidBackend().field(np.array([[r, 0.0, 0.0]]), magnet)[0]
    expected = MAGNET.remanence * MAGNET.volume / (2 * math.pi * r**3)
    assert b[0] == pytest.approx(expected, rel=1e-6)
