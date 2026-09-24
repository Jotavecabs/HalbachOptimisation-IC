"""Modelos (backends) de campo magnético de conjuntos de ímãs.

Cada backend implementa :class:`FieldBackend`: recebe pontos e um
:class:`~halbach_ic.geometry.MagnetArray` e devolve o vetor B em cada ponto.
Por enquanto só existe o modelo de dipolo pontual; o modelo exato de cubos
(magpylib) entra na Fase 2.
"""

from __future__ import annotations

import math
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from halbach_ic.geometry import MU0, MagnetArray


class FieldBackend(Protocol):
    """Interface comum dos modelos de campo."""

    name: str

    def field(self, points: NDArray[np.float64], magnets: MagnetArray) -> NDArray[np.float64]:
        """Campo B [T] nos pontos ``points`` (forma (M, 3), em m). Devolve forma (M, 3)."""
        ...


class DipoleBackend:
    """Cada cubo vira um dipolo pontual no seu centro, com momento ``Br*V/mu0``.

    ``B = mu0/(4 pi) * (3 (m·r) r / |r|^5 - m / |r|^3)``, com ``r`` indo do ímã
    até o ponto. É exato para uma esfera uniformemente magnetizada e uma
    aproximação para cubos, melhor quanto mais longe do ímã.
    """

    name = "dipole"

    def __init__(self, max_chunk_elements: int = 4_000_000) -> None:
        """
        Args:
            max_chunk_elements: limite de pares (ponto, ímã) calculados de uma vez,
                para controlar o uso de memória.
        """
        self.max_chunk_elements = max_chunk_elements

    def field(self, points: NDArray[np.float64], magnets: MagnetArray) -> NDArray[np.float64]:
        points = np.asarray(points, dtype=np.float64)
        positions = magnets.positions
        moments = magnets.moments
        result = np.zeros((points.shape[0], 3))
        min_distance = magnets.spec.size * math.sqrt(3) / 2
        chunk = max(1, self.max_chunk_elements // max(1, points.shape[0]))
        for start in range(0, len(magnets), chunk):
            r = points[:, None, :] - positions[None, start : start + chunk, :]
            r2 = np.einsum("mkc,mkc->mk", r, r)
            if np.any(r2 < min_distance**2):
                raise ValueError("ponto de avaliação dentro de um ímã: o modelo de dipolo não vale ali")
            m = moments[start : start + chunk]
            inv_r2 = 1.0 / r2
            inv_r3 = inv_r2 * np.sqrt(inv_r2)
            m_dot_r = np.einsum("mkc,kc->mk", r, m)
            result += np.einsum("mk,mkc->mc", 3.0 * m_dot_r * inv_r3 * inv_r2, r)
            result -= np.einsum("mk,kc->mc", inv_r3, m)
        return (MU0 / (4.0 * math.pi)) * result


_BACKENDS: dict[str, type] = {DipoleBackend.name: DipoleBackend}


def get_backend(name: str) -> FieldBackend:
    """Instancia o backend pelo nome (``"dipole"``)."""
    try:
        return _BACKENDS[name]()
    except KeyError:
        raise ValueError(f"backend '{name}' desconhecido; disponíveis: {sorted(_BACKENDS)}") from None
