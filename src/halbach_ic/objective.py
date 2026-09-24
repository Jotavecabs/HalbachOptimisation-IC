"""Função objetivo: homogeneidade no DSV com restrições de campo e massa.

O campo total de uma solução é a soma das contribuições de cada slot, então
as contribuições de todas as combinações (slot, opção) são calculadas uma
única vez em :func:`build_field_table` e a avaliação vira uma soma de colunas.

Só a componente de B na direção de ``field_direction`` entra na tabela (é o
que torna a soma linear).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from halbach_ic.field_model import FieldBackend
from halbach_ic.geometry import DesignSpace, MagnetArray


def field_unit_vector(field_direction: float) -> NDArray[np.float64]:
    """Vetor unitário da direção de B0 no plano xy."""
    return np.array([math.cos(field_direction), math.sin(field_direction), 0.0])


@dataclass(frozen=True)
class FieldTable:
    """Campo pré-calculado de cada (slot, opção) nos pontos de avaliação."""

    values: NDArray[np.float32]
    """Componente de B na direção de B0 [T], forma (M, n_slots, n_options)."""
    points: NDArray[np.float64]
    """Pontos de avaliação [m], forma (M, 3)."""
    field_direction: float
    """Direção de B0 usada na projeção [rad]."""
    weights: NDArray[np.float64]
    """Peso de cada ponto na média, forma (M,) (ver ``EvaluationGrid.weights``)."""

    @property
    def n_points(self) -> int:
        return self.values.shape[0]

    def total_field(self, genes: NDArray[np.int64] | tuple[int, ...] | list[int]) -> NDArray[np.float64]:
        """Campo total (componente na direção de B0) para uma solução [T], forma (M,)."""
        genes = np.asarray(genes)
        return self.values[:, np.arange(genes.size), genes].sum(axis=1, dtype=np.float64)


def build_field_table(
    space: DesignSpace,
    points: NDArray[np.float64],
    backend: FieldBackend,
    field_direction: float,
    weights: NDArray[np.float64] | None = None,
) -> FieldTable:
    """Calcula a contribuição de cada opção de anel em cada slot.

    Args:
        space: espaço de busca (slots e opções).
        points: pontos de avaliação, forma (M, 3) [m].
        backend: modelo de campo.
        field_direction: direção de B0 [rad]; a tabela guarda a projeção nela.
        weights: peso de cada ponto na média (padrão: todos 1).
    """
    unit = field_unit_vector(field_direction)
    values = np.empty((points.shape[0], space.n_slots, space.n_options), dtype=np.float32)
    for s, slot in enumerate(space.slots):
        for o, ring in enumerate(space.options):
            magnets = MagnetArray.concatenate([ring.magnets(z) for z in slot])
            values[:, s, o] = backend.field(points, magnets) @ unit
    if weights is None:
        weights = np.ones(points.shape[0])
    if weights.shape != (points.shape[0],):
        raise ValueError("weights deve ter um valor por ponto")
    return FieldTable(values=values, points=points, field_direction=field_direction, weights=weights)


def homogeneity_ppm(values: NDArray[np.float64], weights: NDArray[np.float64] | None = None) -> float:
    """Homogeneidade pico a pico relativa à média, em ppm: ``(max - min) / |média| * 1e6``.

    Args:
        values: campo nos pontos.
        weights: pesos da média (``None`` = média simples).
    """
    mean = float(np.average(values, weights=weights))
    if mean == 0.0:
        return math.inf
    return float((np.max(values) - np.min(values)) / abs(mean) * 1e6)


@dataclass(frozen=True)
class Evaluation:
    """Resultado da avaliação de uma solução."""

    ppm: float
    """Homogeneidade pico a pico [ppm]."""
    mean_field: float
    """Campo médio na direção de B0 [T] (negativo = sentido oposto ao pedido)."""
    mass: float
    """Massa total dos ímãs [kg]."""
    violation: float
    """Violação normalizada das restrições (0 = viável)."""

    @property
    def feasible(self) -> bool:
        return self.violation == 0.0


@dataclass(frozen=True)
class Objective:
    """Homogeneidade (objetivo) + campo alvo e massa máxima (restrições).

    A violação é a soma de quanto cada restrição foi ultrapassada, normalizada
    pela própria escala (tolerância de campo e massa máxima). Não há pesos
    arbitrários: o otimizador compara primeiro a violação e só depois a
    homogeneidade (regras de Deb).
    """

    table: FieldTable
    mass_table: NDArray[np.float64]
    """Massa de cada (slot, opção) [kg], forma (n_slots, n_options)."""
    target_field: float
    field_tolerance: float
    max_mass: float

    def evaluate(self, genes: NDArray[np.int64] | tuple[int, ...] | list[int]) -> Evaluation:
        """Avalia uma solução (índice da opção escolhida em cada slot)."""
        genes = np.asarray(genes)
        field = self.table.total_field(genes)
        mean = float(np.average(field, weights=self.table.weights))
        mass = float(self.mass_table[np.arange(genes.size), genes].sum())
        field_excess = max(0.0, abs(mean - self.target_field) - self.field_tolerance) / self.field_tolerance
        mass_excess = max(0.0, mass - self.max_mass) / self.max_mass
        return Evaluation(
            ppm=homogeneity_ppm(field, self.table.weights), mean_field=mean, mass=mass, violation=field_excess + mass_excess
        )
