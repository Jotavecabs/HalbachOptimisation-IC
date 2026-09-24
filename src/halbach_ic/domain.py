"""Região de avaliação: grade cartesiana, esfera do DSV e simetria.

A grade usa indexação ``ij``: ``grid[ix, iy, iz]`` corresponde a
``(axis[ix], axis[iy], axis[iz])``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from halbach_ic.config import Symmetry

_TOL = 1e-9


@dataclass(frozen=True)
class EvaluationGrid:
    """Grade cúbica centrada na origem que contém a esfera do DSV."""

    axis: NDArray[np.float64]
    """Coordenadas de um eixo [m], forma (n,)."""
    dsv_radius: float
    """Raio da esfera do DSV [m]."""

    @property
    def shape(self) -> tuple[int, int, int]:
        n = self.axis.size
        return (n, n, n)

    def coordinates(self) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
        """Coordenadas X, Y, Z da grade inteira, cada uma com forma ``shape``."""
        return np.meshgrid(self.axis, self.axis, self.axis, indexing="ij")

    def sphere_mask(self) -> NDArray[np.bool_]:
        """Pontos dentro (ou na superfície) da esfera do DSV."""
        x, y, z = self.coordinates()
        return x**2 + y**2 + z**2 <= self.dsv_radius**2 * (1 + _TOL)

    def mask(self, symmetry: Symmetry) -> NDArray[np.bool_]:
        """Máscara dos pontos avaliados.

        ``"full"`` é a esfera inteira. ``"octant"`` fica só com x, y, z >= 0,
        incluindo os planos de simetria.
        """
        mask = self.sphere_mask()
        if symmetry == "octant":
            x, y, z = self.coordinates()
            mask &= (x >= -_TOL) & (y >= -_TOL) & (z >= -_TOL)
        elif symmetry != "full":
            raise ValueError(f"simetria desconhecida: {symmetry!r}")
        return mask

    def points(self, symmetry: Symmetry) -> NDArray[np.float64]:
        """Pontos avaliados, forma (M, 3) [m], na ordem de ``mask(symmetry)``."""
        x, y, z = self.coordinates()
        mask = self.mask(symmetry)
        return np.stack([x[mask], y[mask], z[mask]], axis=1)


def make_grid(dsv_diameter: float, spacing: float) -> EvaluationGrid:
    """Cria a grade com passo o mais próximo possível de ``spacing``.

    O número de pontos por eixo é ``round(dsv_diameter / spacing) + 1``, de
    modo que os pontos extremos caem exatamente na superfície do DSV.
    """
    if dsv_diameter <= 0 or spacing <= 0:
        raise ValueError("diâmetro e espaçamento devem ser > 0")
    n = int(round(dsv_diameter / spacing)) + 1
    radius = dsv_diameter / 2
    return EvaluationGrid(axis=np.linspace(-radius, radius, n), dsv_radius=radius)
