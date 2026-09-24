"""Função objetivo: homogeneidade no DSV com restrições de campo e massa.

O campo total de uma solução é a soma das contribuições de cada slot, então
as contribuições de todas as combinações (slot, opção) são calculadas uma
única vez em :func:`build_field_table` e a avaliação vira uma soma de linhas
da tabela.

Só a componente de B na direção de ``field_direction`` entra na tabela (é o
que torna a soma linear).

A avaliação é vetorizada: :meth:`Objective.evaluate_batch` avalia uma
população inteira (matriz de genes) com operações matriciais, em blocos para
limitar a memória.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from halbach_ic.field_model import FieldBackend
from halbach_ic.geometry import DesignSpace
from halbach_ic.parallel import compute_field_columns

DEFAULT_CHUNK_BYTES = 64 * 2**20
"""Memória de trabalho padrão por bloco de avaliação (64 MiB)."""


def field_unit_vector(field_direction: float) -> NDArray[np.float64]:
    """Vetor unitário da direção de B0 no plano xy."""
    return np.array([math.cos(field_direction), math.sin(field_direction), 0.0])


@dataclass(frozen=True)
class FieldTable:
    """Campo pré-calculado de cada (slot, opção) nos pontos de avaliação."""

    values: NDArray[np.float32]
    """Componente de B na direção de B0 [T], forma (n_slots, n_options, M).

    Os pontos ficam no último eixo para que ``values[s, genes]`` leia linhas
    contíguas da memória.
    """
    points: NDArray[np.float64]
    """Pontos de avaliação [m], forma (M, 3)."""
    field_direction: float
    """Direção de B0 usada na projeção [rad]."""
    weights: NDArray[np.float64]
    """Peso de cada ponto na média, forma (M,) (ver ``EvaluationGrid.weights``)."""

    @property
    def n_points(self) -> int:
        return self.values.shape[2]

    def total_field(self, genes: NDArray[np.int64] | tuple[int, ...] | list[int]) -> NDArray[np.float64]:
        """Campo total (componente na direção de B0) para uma solução [T], forma (M,)."""
        genes = np.asarray(genes)
        return self.values[np.arange(genes.size), genes].sum(axis=0, dtype=np.float64)


def build_field_table(
    space: DesignSpace,
    points: NDArray[np.float64],
    backend: FieldBackend,
    field_direction: float,
    weights: NDArray[np.float64] | None = None,
    n_workers: int = 1,
) -> FieldTable:
    """Calcula a contribuição de cada opção de anel em cada slot.

    Args:
        space: espaço de busca (slots e opções).
        points: pontos de avaliação, forma (M, 3) [m].
        backend: modelo de campo.
        field_direction: direção de B0 [rad]; a tabela guarda a projeção nela.
        weights: peso de cada ponto na média (padrão: todos 1).
        n_workers: processos usados no cálculo (1 = sem paralelismo).
    """
    if weights is None:
        weights = np.ones(points.shape[0])
    if weights.shape != (points.shape[0],):
        raise ValueError("weights deve ter um valor por ponto")
    tasks = [(slot, ring) for slot in space.slots for ring in space.options]
    columns = compute_field_columns(tasks, points, backend, field_direction_unit=field_unit_vector(field_direction),
                                    n_workers=n_workers)
    values = columns.reshape(space.n_slots, space.n_options, points.shape[0])
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
class BatchEvaluation:
    """Avaliação de várias soluções; cada campo tem forma (P,)."""

    ppm: NDArray[np.float64]
    mean_field: NDArray[np.float64]
    mass: NDArray[np.float64]
    violation: NDArray[np.float64]

    def __len__(self) -> int:
        return self.ppm.size

    def __getitem__(self, i: int) -> Evaluation:
        return Evaluation(ppm=float(self.ppm[i]), mean_field=float(self.mean_field[i]),
                          mass=float(self.mass[i]), violation=float(self.violation[i]))

    @staticmethod
    def concatenate(parts: list[BatchEvaluation]) -> BatchEvaluation:
        """Junta avaliações de blocos diferentes, na ordem."""
        return BatchEvaluation(*(np.concatenate([getattr(p, f) for p in parts])
                                 for f in ("ppm", "mean_field", "mass", "violation")))


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
    chunk_bytes: int = DEFAULT_CHUNK_BYTES
    """Memória de trabalho por bloco de avaliação [bytes]."""

    def evaluate_batch(self, genes: NDArray[np.int64]) -> BatchEvaluation:
        """Avalia várias soluções de uma vez.

        Args:
            genes: matriz (P, n_slots) com o índice da opção em cada slot.
        """
        genes = np.atleast_2d(np.asarray(genes, dtype=np.int64))
        n_pop, n_slots = genes.shape
        values, weights = self.table.values, self.table.weights
        n_points = values.shape[2]
        weight_total = weights.sum()
        rows = max(1, self.chunk_bytes // (8 * n_points))

        ppm = np.empty(n_pop)
        mean = np.empty(n_pop)
        for start in range(0, n_pop, rows):
            block = genes[start : start + rows]
            field = values[0, block[:, 0]].astype(np.float64)
            for s in range(1, n_slots):
                field += values[s, block[:, s]]
            block_mean = field @ weights / weight_total
            spread = field.max(axis=1) - field.min(axis=1)
            with np.errstate(divide="ignore"):
                ppm[start : start + rows] = np.where(block_mean != 0, spread / np.abs(block_mean) * 1e6, np.inf)
            mean[start : start + rows] = block_mean

        mass = self.mass_table[np.arange(n_slots), genes].sum(axis=1)
        field_excess = np.maximum(0.0, np.abs(mean - self.target_field) - self.field_tolerance) / self.field_tolerance
        mass_excess = np.maximum(0.0, mass - self.max_mass) / self.max_mass
        return BatchEvaluation(ppm=ppm, mean_field=mean, mass=mass, violation=field_excess + mass_excess)

    def evaluate(self, genes: NDArray[np.int64] | tuple[int, ...] | list[int]) -> Evaluation:
        """Avalia uma solução (índice da opção escolhida em cada slot)."""
        return self.evaluate_batch(np.asarray(genes)[None, :])[0]
