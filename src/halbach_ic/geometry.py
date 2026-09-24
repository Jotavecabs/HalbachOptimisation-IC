"""Geometria dos anéis Halbach: posição, orientação e viabilidade dos ímãs.

Convenções (todas em SI):

* O eixo do bore é z. O campo B0 fica no plano transversal xy.
* Um ímã na posição angular ``theta`` tem magnetização no ângulo
  ``2*theta + phase`` (Halbach k = 2). O corpo do cubo gira junto com a
  magnetização (magnetização normal a uma face).
* Para k = 2, girar a estrutura inteira de ``beta`` gira o campo de ``beta`` e
  muda a fase de ``-beta``. Daí sai que o campo no centro aponta na direção
  ``-phase``. Por isso a fase é calculada a partir da direção desejada de B0
  como ``phase = -field_direction`` (ver :func:`magnetization_phase`).

Regra de não sobreposição (conservadora): como o cubo pode estar em qualquer
rotação em torno de z, cada ímã é tratado no plano xy como um círculo de
diâmetro ``a*sqrt(2)`` (o círculo circunscrito ao quadrado). Em z, os cubos
não giram, então a extensão axial é exatamente ``a``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

MU0 = 4e-7 * math.pi
"""Permeabilidade magnética do vácuo [T·m/A]."""

HALBACH_K = 2
"""Ordem do arranjo Halbach. k = 2 gera campo transversal uniforme (dipolar)."""

_EPS = 1e-12


class InfeasibleGeometryError(ValueError):
    """Configuração geométrica que não pode ser construída (ímãs sobrepostos etc.)."""


def magnetization_phase(field_direction: float) -> float:
    """Fase ``phase`` da magnetização ``2*theta + phase`` que produz B0 em ``field_direction``.

    Args:
        field_direction: direção desejada de B0 no plano xy, a partir de +x [rad].

    Returns:
        A fase da magnetização [rad]. Para k = 2 vale ``-field_direction``.
    """
    return -field_direction


@dataclass(frozen=True)
class MagnetSpec:
    """Ímã cúbico uniformemente magnetizado."""

    size: float
    """Aresta [m]."""
    remanence: float
    """Remanência Br [T]."""
    density: float
    """Densidade [kg/m³]."""

    def __post_init__(self) -> None:
        if self.size <= 0 or self.remanence <= 0 or self.density <= 0:
            raise InfeasibleGeometryError("tamanho, remanência e densidade do ímã devem ser > 0")

    @property
    def volume(self) -> float:
        """Volume [m³]."""
        return self.size**3

    @property
    def mass(self) -> float:
        """Massa de um ímã [kg]."""
        return self.density * self.volume

    @property
    def dipole_moment(self) -> float:
        """Momento de dipolo equivalente ``Br*V/mu0`` [A·m²]."""
        return self.remanence * self.volume / MU0

    @property
    def footprint_diameter(self) -> float:
        """Diâmetro do círculo circunscrito ao quadrado no plano xy [m]."""
        return self.size * math.sqrt(2.0)


@dataclass(frozen=True)
class MagnetArray:
    """Conjunto de ímãs cúbicos iguais, com posição e orientação de cada um."""

    spec: MagnetSpec
    positions: NDArray[np.float64]
    """Centros dos cubos, forma (K, 3) [m]."""
    angles: NDArray[np.float64]
    """Ângulo da magnetização no plano xy, forma (K,) [rad]. O corpo do cubo gira junto."""

    def __post_init__(self) -> None:
        if self.positions.ndim != 2 or self.positions.shape[1] != 3:
            raise ValueError("positions deve ter forma (K, 3)")
        if self.angles.shape != (self.positions.shape[0],):
            raise ValueError("angles deve ter forma (K,)")

    def __len__(self) -> int:
        return self.positions.shape[0]

    @property
    def directions(self) -> NDArray[np.float64]:
        """Vetores unitários de magnetização, forma (K, 3)."""
        return np.stack([np.cos(self.angles), np.sin(self.angles), np.zeros_like(self.angles)], axis=1)

    @property
    def moments(self) -> NDArray[np.float64]:
        """Momentos de dipolo, forma (K, 3) [A·m²]."""
        return self.spec.dipole_moment * self.directions

    @staticmethod
    def concatenate(arrays: list[MagnetArray]) -> MagnetArray:
        """Junta vários conjuntos com o mesmo tipo de ímã."""
        if not arrays:
            raise ValueError("lista vazia")
        spec = arrays[0].spec
        if any(a.spec != spec for a in arrays):
            raise ValueError("todos os conjuntos devem usar o mesmo MagnetSpec")
        return MagnetArray(
            spec=spec,
            positions=np.concatenate([a.positions for a in arrays]),
            angles=np.concatenate([a.angles for a in arrays]),
        )


def max_magnets_on_circle(radius: float, footprint: float, gap: float) -> int:
    """Maior número de ímãs que cabe num círculo sem sobreposição.

    Ímãs vizinhos ficam a uma distância de ``2*r*sin(pi/N)`` (corda). A corda
    precisa ser pelo menos ``footprint + gap``.

    Args:
        radius: raio do círculo dos centros [m].
        footprint: diâmetro ocupado por cada ímã [m].
        gap: folga mínima entre ímãs vizinhos [m].

    Returns:
        O número máximo de ímãs (0 se nem dois ímãs cabem).
    """
    ratio = (footprint + gap) / (2.0 * radius)
    if ratio >= 1.0:
        return 0
    return int(math.floor(math.pi / math.asin(ratio) + 1e-9))


def squares_overlap(
    center_a: NDArray[np.float64],
    angle_a: NDArray[np.float64],
    center_b: NDArray[np.float64],
    angle_b: NDArray[np.float64],
    size: float,
) -> NDArray[np.bool_]:
    """Teste exato de sobreposição entre quadrados girados (teorema do eixo separador).

    Serve para verificar a regra conservadora do círculo circunscrito. Aceita
    arrays com broadcast: centros com forma (..., 2), ângulos com forma (...).

    Returns:
        Array booleano, ``True`` onde os quadrados se sobrepõem (encostar conta
        como sobreposição).
    """
    delta = np.asarray(center_b) - np.asarray(center_a)
    half = size / 2.0
    overlap = np.ones(np.broadcast_shapes(delta.shape[:-1], np.shape(angle_a), np.shape(angle_b)), dtype=bool)
    for axis_angle in (angle_a, angle_a + np.pi / 2, angle_b, angle_b + np.pi / 2):
        nx, ny = np.cos(axis_angle), np.sin(axis_angle)
        distance = np.abs(delta[..., 0] * nx + delta[..., 1] * ny)
        extent_a = half * (np.abs(np.cos(angle_a - axis_angle)) + np.abs(np.sin(angle_a - axis_angle)))
        extent_b = half * (np.abs(np.cos(angle_b - axis_angle)) + np.abs(np.sin(angle_b - axis_angle)))
        overlap &= distance < extent_a + extent_b + _EPS
    return overlap


@dataclass(frozen=True)
class HalbachRing:
    """Anel Halbach k = 2 com uma ou mais camadas (bandas) concêntricas de cubos.

    A geometria parte das grandezas físicas: o raio livre interno (bore), o ímã,
    o número de bandas e as folgas. O número de ímãs de cada banda é calculado
    como o máximo que cabe sem sobreposição. Configurações inviáveis geram
    :class:`InfeasibleGeometryError` já na construção.

    O raio livre interno é conservador: considera o círculo circunscrito de cada
    cubo, então a folga real é igual ou maior.
    """

    bore_radius: float
    """Raio livre interno [m] (a parte mais interna de qualquer ímã fica fora dele)."""
    magnet: MagnetSpec
    n_bands: int
    band_gap: float
    """Folga radial extra entre bandas, além do diâmetro circunscrito [m]."""
    magnet_gap: float
    """Folga mínima entre ímãs vizinhos na mesma banda [m]."""
    field_direction: float
    """Direção de B0 no plano xy [rad]."""
    angle_offset: float = 0.0
    """Posição angular do 1º ímã de cada banda, relativa a ``field_direction`` [rad]."""
    n_magnets_override: tuple[int, ...] | None = None
    """Número de ímãs por banda escolhido manualmente (validado contra o máximo)."""

    band_radii: tuple[float, ...] = field(init=False)
    """Raio do círculo dos centros de cada banda [m]."""
    n_magnets: tuple[int, ...] = field(init=False)
    """Número de ímãs de cada banda."""

    def __post_init__(self) -> None:
        if self.bore_radius <= 0:
            raise InfeasibleGeometryError(f"raio do bore deve ser > 0, recebido {self.bore_radius}")
        if self.n_bands < 1:
            raise InfeasibleGeometryError("n_bands deve ser >= 1")
        if self.band_gap < 0 or self.magnet_gap < 0:
            raise InfeasibleGeometryError("folgas não podem ser negativas")

        footprint = self.magnet.footprint_diameter
        pitch = footprint + self.band_gap
        radii = tuple(self.bore_radius + footprint / 2 + i * pitch for i in range(self.n_bands))
        maximum = tuple(max_magnets_on_circle(r, footprint, self.magnet_gap) for r in radii)

        if self.n_magnets_override is None:
            counts = maximum
        else:
            counts = tuple(int(n) for n in self.n_magnets_override)
            if len(counts) != self.n_bands:
                raise InfeasibleGeometryError(
                    f"n_magnets_override tem {len(counts)} valores para {self.n_bands} bandas"
                )
            for band, (n, n_max) in enumerate(zip(counts, maximum)):
                if n > n_max:
                    raise InfeasibleGeometryError(
                        f"banda {band} (r = {radii[band] * 1e3:.2f} mm): {n} ímãs não cabem; "
                        f"máximo é {n_max} com folga de {self.magnet_gap * 1e3:.2f} mm"
                    )
        for band, n in enumerate(counts):
            if n < 3:
                raise InfeasibleGeometryError(
                    f"banda {band} (r = {radii[band] * 1e3:.2f} mm) comporta só {n} ímã(s); "
                    "um anel Halbach precisa de pelo menos 3"
                )

        object.__setattr__(self, "band_radii", radii)
        object.__setattr__(self, "n_magnets", counts)

    @property
    def total_magnets(self) -> int:
        """Número de ímãs no anel (todas as bandas)."""
        return sum(self.n_magnets)

    @property
    def outer_radius(self) -> float:
        """Raio externo ocupado pelos ímãs (círculo circunscrito) [m]."""
        return self.band_radii[-1] + self.magnet.footprint_diameter / 2

    @property
    def mass(self) -> float:
        """Massa dos ímãs do anel [kg]."""
        return self.total_magnets * self.magnet.mass

    def band_angles(self, band: int) -> NDArray[np.float64]:
        """Posições angulares dos ímãs da banda ``band`` [rad]."""
        n = self.n_magnets[band]
        return self.field_direction + self.angle_offset + 2.0 * np.pi * np.arange(n) / n

    def magnets(self, z: float = 0.0) -> MagnetArray:
        """Ímãs do anel centrado em ``z``, com posição e orientação."""
        phase = magnetization_phase(self.field_direction)
        positions, angles = [], []
        for band, radius in enumerate(self.band_radii):
            theta = self.band_angles(band)
            positions.append(np.stack([radius * np.cos(theta), radius * np.sin(theta), np.full_like(theta, z)], axis=1))
            angles.append(HALBACH_K * theta + phase)
        return MagnetArray(spec=self.magnet, positions=np.concatenate(positions), angles=np.concatenate(angles))

    def has_overlap(self) -> bool:
        """Verificação exata (quadrados girados) de sobreposição entre quaisquer dois ímãs do anel."""
        arr = self.magnets()
        xy = arr.positions[:, :2]
        i, j = np.triu_indices(len(arr), k=1)
        return bool(np.any(squares_overlap(xy[i], arr.angles[i], xy[j], arr.angles[j], self.magnet.size)))


def ring_z_positions(n_rings: int, spacing: float) -> NDArray[np.float64]:
    """Posições z dos centros dos anéis, simétricas em torno de z = 0 [m]."""
    return (np.arange(n_rings) - (n_rings - 1) / 2.0) * spacing


def symmetric_slots(n_rings: int, spacing: float) -> tuple[tuple[float, ...], ...]:
    """Agrupa os anéis em posições otimizáveis usando a simetria em z.

    Cada posição com z > 0 vira o par ``(-z, +z)``, que recebe sempre o mesmo
    anel. Se ``n_rings`` for ímpar, o anel em z = 0 fica sozinho. A comparação
    com zero é feita por índice, não por igualdade de float.
    """
    z = ring_z_positions(n_rings, spacing)
    half = n_rings // 2
    slots: list[tuple[float, ...]] = []
    if n_rings % 2 == 1:
        slots.append((0.0,))
        upper = z[half + 1 :]
    else:
        upper = z[half:]
    slots.extend((-float(zz), float(zz)) for zz in upper)
    return tuple(slots)


@dataclass(frozen=True)
class DesignSpace:
    """Espaço de busca: cada posição (slot) escolhe um anel entre as opções."""

    slots: tuple[tuple[float, ...], ...]
    """Posições z de cada slot [m]; slots com dois valores são pares simétricos."""
    options: tuple[HalbachRing, ...]
    """Anéis candidatos, iguais para todos os slots."""
    rejected: tuple[tuple[float, str], ...] = ()
    """Raios de bore candidatos recusados e o motivo."""

    @property
    def n_slots(self) -> int:
        return len(self.slots)

    @property
    def n_options(self) -> int:
        return len(self.options)

    def slot_multiplicity(self) -> NDArray[np.int64]:
        """Quantos anéis físicos cada slot representa (1 ou 2)."""
        return np.array([len(s) for s in self.slots])

    def option_mass(self) -> NDArray[np.float64]:
        """Massa de um anel de cada opção [kg], forma (n_options,)."""
        return np.array([ring.mass for ring in self.options])

    def mass_table(self) -> NDArray[np.float64]:
        """Massa de cada (slot, opção) [kg], forma (n_slots, n_options)."""
        return self.slot_multiplicity()[:, None] * self.option_mass()[None, :]


def build_design_space(
    *,
    magnet: MagnetSpec,
    bore_radius_candidates: tuple[float, ...],
    n_bands: int,
    band_gap: float,
    magnet_gap: float,
    field_direction: float,
    angle_offset: float,
    n_rings: int,
    ring_spacing: float,
    axial_gap: float,
    min_bore_diameter: float,
) -> DesignSpace:
    """Monta o espaço de busca a partir dos parâmetros físicos.

    Candidatos inviáveis (ímãs não cabem ou bore abaixo do mínimo) são
    recusados e listados em ``DesignSpace.rejected``.

    Raises:
        InfeasibleGeometryError: espaçamento axial menor que o cubo mais a folga,
            ou nenhum candidato viável.
    """
    if ring_spacing < magnet.size + axial_gap - _EPS:
        raise InfeasibleGeometryError(
            f"espaçamento entre anéis ({ring_spacing * 1e3:.2f} mm) menor que o cubo mais a folga axial "
            f"({(magnet.size + axial_gap) * 1e3:.2f} mm): anéis vizinhos se sobreporiam"
        )
    options: list[HalbachRing] = []
    rejected: list[tuple[float, str]] = []
    for bore in bore_radius_candidates:
        if 2 * bore < min_bore_diameter - _EPS:
            rejected.append((bore, f"bore {2 * bore * 1e3:.1f} mm < mínimo {min_bore_diameter * 1e3:.1f} mm"))
            continue
        try:
            options.append(
                HalbachRing(
                    bore_radius=bore,
                    magnet=magnet,
                    n_bands=n_bands,
                    band_gap=band_gap,
                    magnet_gap=magnet_gap,
                    field_direction=field_direction,
                    angle_offset=angle_offset,
                )
            )
        except InfeasibleGeometryError as exc:
            rejected.append((bore, str(exc)))
    if not options:
        raise InfeasibleGeometryError(f"nenhum raio candidato é viável: {rejected}")
    return DesignSpace(slots=symmetric_slots(n_rings, ring_spacing), options=tuple(options), rejected=tuple(rejected))


@dataclass(frozen=True)
class Design:
    """Uma solução: a opção de anel escolhida para cada slot."""

    space: DesignSpace
    genes: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.genes) != self.space.n_slots:
            raise ValueError(f"esperados {self.space.n_slots} genes, recebidos {len(self.genes)}")
        if any(not 0 <= g < self.space.n_options for g in self.genes):
            raise ValueError(f"gene fora do intervalo [0, {self.space.n_options - 1}]: {self.genes}")

    def rings(self) -> list[tuple[float, HalbachRing]]:
        """Lista ``(z, anel)`` de todos os anéis físicos, ordenada por z."""
        items = [(z, self.space.options[g]) for slot, g in zip(self.space.slots, self.genes) for z in slot]
        return sorted(items, key=lambda item: item[0])

    def magnets(self) -> MagnetArray:
        """Todos os ímãs do arranjo."""
        return MagnetArray.concatenate([ring.magnets(z) for z, ring in self.rings()])

    @property
    def mass(self) -> float:
        """Massa total dos ímãs [kg]."""
        return float(sum(ring.mass for _, ring in self.rings()))

    @property
    def free_bore_diameter(self) -> float:
        """Diâmetro livre do arranjo (o menor dos anéis) [m]."""
        return 2.0 * min(ring.bore_radius for _, ring in self.rings())

    @property
    def n_magnets(self) -> int:
        """Número total de ímãs."""
        return sum(ring.total_magnets for _, ring in self.rings())
