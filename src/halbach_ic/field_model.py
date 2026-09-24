"""Modelos (backends) de campo magnético de conjuntos de ímãs.

Cada backend implementa :class:`FieldBackend`: recebe pontos e um
:class:`~halbach_ic.geometry.MagnetArray` e devolve o vetor B em cada ponto.
Modelos disponíveis:

* ``dipole``: cada cubo vira um dipolo pontual. Rápido, aproximado perto dos ímãs.
* ``cuboid``: campo analítico exato do cubo (magpylib). Cerca de 13x mais lento.
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


class CuboidBackend:
    """Campo analítico exato de cubos uniformemente magnetizados (magpylib).

    Cada cubo tem o corpo girado em torno de z pelo mesmo ângulo da
    magnetização, que fica normal a uma face (convenção de ``geometry``). Os
    pontos são levados para o referencial local de cada cubo (cubo alinhado aos
    eixos, polarização ``(Br, 0, 0)``), o campo é calculado por
    ``magpylib.core.magnet_cuboid_Bfield`` e girado de volta.

    Válido em qualquer ponto fora do ímã, sem a aproximação de campo distante
    do dipolo.
    """

    name = "cuboid"

    def __init__(self, max_chunk_elements: int = 1_000_000) -> None:
        """
        Args:
            max_chunk_elements: limite de pares (ponto, ímã) calculados de uma vez.
        """
        self.max_chunk_elements = max_chunk_elements

    def field(self, points: NDArray[np.float64], magnets: MagnetArray) -> NDArray[np.float64]:
        from magpylib.core import magnet_cuboid_Bfield

        points = np.asarray(points, dtype=np.float64)
        size, remanence = magnets.spec.size, magnets.spec.remanence
        result = np.zeros((points.shape[0], 3))
        chunk = max(1, self.max_chunk_elements // max(1, points.shape[0]))
        for start in range(0, len(magnets), chunk):
            positions = magnets.positions[start : start + chunk]
            cos, sin = np.cos(magnets.angles[start : start + chunk]), np.sin(magnets.angles[start : start + chunk])
            d = points[:, None, :] - positions[None, :, :]
            local = np.stack([cos * d[..., 0] + sin * d[..., 1], -sin * d[..., 0] + cos * d[..., 1], d[..., 2]], axis=-1)
            n_pairs = local.shape[0] * local.shape[1]
            b_local = magnet_cuboid_Bfield(
                observers=local.reshape(n_pairs, 3),
                dimensions=np.broadcast_to([size, size, size], (n_pairs, 3)),
                polarizations=np.broadcast_to([remanence, 0.0, 0.0], (n_pairs, 3)),
            ).reshape(local.shape)
            result[:, 0] += np.sum(cos * b_local[..., 0] - sin * b_local[..., 1], axis=1)
            result[:, 1] += np.sum(sin * b_local[..., 0] + cos * b_local[..., 1], axis=1)
            result[:, 2] += np.sum(b_local[..., 2], axis=1)
        return result


_BACKENDS: dict[str, type] = {DipoleBackend.name: DipoleBackend, CuboidBackend.name: CuboidBackend}

BACKEND_NAMES: tuple[str, ...] = tuple(_BACKENDS)
"""Nomes aceitos em ``model.backend`` na configuração."""


def get_backend(name: str) -> FieldBackend:
    """Instancia o backend pelo nome (``"dipole"`` ou ``"cuboid"``)."""
    try:
        return _BACKENDS[name]()
    except KeyError:
        raise ValueError(f"backend '{name}' desconhecido; disponíveis: {sorted(_BACKENDS)}") from None
