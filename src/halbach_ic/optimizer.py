"""Algoritmo genético para escolher o anel de cada slot.

A população é uma matriz de inteiros (P, n_slots): cada linha é uma solução e
cada gene é o índice da opção de anel no slot. Os operadores são os mesmos do
código original, reimplementados em NumPy para operar na população inteira
de uma vez (sem clonar objetos Python a cada geração):

* seleção por torneio (``deap.tools.selTournament``);
* cruzamento de dois pontos em pares consecutivos (``cxTwoPoint`` via ``varAnd``);
* mutação que sorteia um novo índice válido para cada gene
  (``mutUniformInt``; o original usava ``mutFlipBit``, ver DOCS/correcoes.md item 1).

A aptidão é o par ``(violação, ppm)`` comparado em ordem lexicográfica, o que
implementa as regras de Deb sem pesos arbitrários:

1. solução viável sempre vence solução inviável;
2. entre inviáveis, vence a que viola menos;
3. entre viáveis, vence a mais homogênea.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from halbach_ic.config import GAConfig
from halbach_ic.objective import BatchEvaluation, Evaluation

BatchEvaluator = Callable[[NDArray[np.int64]], BatchEvaluation]


@dataclass(frozen=True)
class GenerationStats:
    """Estatísticas de uma geração."""

    generation: int
    best_violation: float
    best_ppm: float
    """ppm do melhor indivíduo da geração (pode ser inviável se nenhum for viável)."""
    best_mean_field: float
    """Campo médio do melhor indivíduo [T]."""
    mean_ppm_feasible: float
    """ppm médio entre os viáveis (NaN se não houver)."""
    feasible_fraction: float
    duplicate_fraction: float
    """Fração de indivíduos repetidos (perda de diversidade)."""
    elapsed: float
    """Tempo da geração [s]."""


@dataclass(frozen=True)
class GAResult:
    """Resultado do GA."""

    best_genes: tuple[int, ...]
    best: Evaluation
    history: tuple[GenerationStats, ...]
    elapsed: float
    evaluations: int
    """Número de soluções distintas avaliadas (o cache evita repetir)."""


def lexicographic_rank(violation: NDArray[np.float64], ppm: NDArray[np.float64]) -> NDArray[np.int64]:
    """Posição de cada indivíduo na ordem (violação, ppm); 0 = melhor."""
    order = np.lexsort((ppm, violation))
    rank = np.empty(order.size, dtype=np.int64)
    rank[order] = np.arange(order.size)
    return rank


def tournament_selection(rng: np.random.Generator, rank: NDArray[np.int64], k: int, n: int) -> NDArray[np.int64]:
    """Índices de ``n`` vencedores de torneios com ``k`` competidores sorteados com reposição."""
    contenders = rng.integers(0, rank.size, size=(n, k))
    return contenders[np.arange(n), np.argmin(rank[contenders], axis=1)]


def two_point_crossover(rng: np.random.Generator, pop: NDArray[np.int64], prob: float) -> None:
    """Cruzamento de dois pontos, no lugar, nos pares (0,1), (2,3), ... com probabilidade ``prob``.

    Os pontos de corte são dois valores distintos em [1, n_slots], como em
    ``deap.tools.cxTwoPoint``; o trecho entre eles é trocado entre os pais.
    """
    n_pairs, size = pop.shape[0] // 2, pop.shape[1]
    if size < 2 or n_pairs == 0:
        return
    chosen = np.flatnonzero(rng.random(n_pairs) < prob)
    if chosen.size == 0:
        return
    a = rng.integers(1, size + 1, chosen.size)
    b = rng.integers(1, size, chosen.size)
    b = b + (b >= a)
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    idx = np.arange(size)
    swap = (idx >= lo[:, None]) & (idx < hi[:, None])
    first, second = pop[2 * chosen], pop[2 * chosen + 1]
    pop[2 * chosen] = np.where(swap, second, first)
    pop[2 * chosen + 1] = np.where(swap, first, second)


def uniform_int_mutation(rng: np.random.Generator, pop: NDArray[np.int64], prob: float, gene_prob: float,
                         n_options: int) -> None:
    """Mutação no lugar: cada indivíduo sofre mutação com probabilidade ``prob``; nele,
    cada gene é sorteado de novo em [0, n_options - 1] com probabilidade ``gene_prob``."""
    mutate = (rng.random(pop.shape[0]) < prob)[:, None] & (rng.random(pop.shape) < gene_prob)
    pop[mutate] = rng.integers(0, n_options, int(mutate.sum()))


class _EvaluationCache:
    """Guarda a avaliação de cada vetor de genes já visto."""

    def __init__(self, evaluate: BatchEvaluator) -> None:
        self.evaluate = evaluate
        self.store: dict[bytes, tuple[float, float, float, float]] = {}

    def __call__(self, pop: NDArray[np.int64]) -> tuple[list[bytes], NDArray[np.float64]]:
        """Devolve as chaves e uma matriz (P, 4) com (violação, ppm, campo médio, massa)."""
        keys = [row.tobytes() for row in pop]
        missing: dict[bytes, int] = {}
        for i, key in enumerate(keys):
            if key not in self.store and key not in missing:
                missing[key] = i
        if missing:
            result = self.evaluate(pop[list(missing.values())])
            for j, key in enumerate(missing):
                self.store[key] = (float(result.violation[j]), float(result.ppm[j]),
                                   float(result.mean_field[j]), float(result.mass[j]))
        return keys, np.array([self.store[k] for k in keys])


def run_ga(
    evaluate: BatchEvaluator,
    n_slots: int,
    n_options: int,
    cfg: GAConfig,
    progress: Callable[[GenerationStats], None] | None = None,
) -> GAResult:
    """Executa o GA.

    Args:
        evaluate: avalia uma matriz de genes (``Objective.evaluate_batch`` ou um
            :class:`~halbach_ic.evaluator.ParallelEvaluator`).
        n_slots: número de genes.
        n_options: cada gene fica em ``[0, n_options - 1]``.
        cfg: parâmetros do GA.
        progress: chamada ao fim de cada geração (para log).
    """
    rng = np.random.default_rng(cfg.seed)
    cache = _EvaluationCache(evaluate)
    start = time.perf_counter()

    pop = rng.integers(0, n_options, size=(cfg.population, n_slots))
    _, fitness = cache(pop)
    first = int(np.lexsort((fitness[:, 1], fitness[:, 0]))[0])
    best_ever = (fitness[first, 0], fitness[first, 1], pop[first].copy())

    history: list[GenerationStats] = []
    for generation in range(1, cfg.generations + 1):
        t0 = time.perf_counter()
        rank = lexicographic_rank(fitness[:, 0], fitness[:, 1])
        pop = pop[tournament_selection(rng, rank, cfg.tournament_size, cfg.population)]
        two_point_crossover(rng, pop, cfg.crossover_prob)
        uniform_int_mutation(rng, pop, cfg.mutation_prob, cfg.gene_mutation_prob, n_options)
        keys, fitness = cache(pop)

        best = int(np.lexsort((fitness[:, 1], fitness[:, 0]))[0])
        if (fitness[best, 0], fitness[best, 1]) < best_ever[:2]:
            best_ever = (fitness[best, 0], fitness[best, 1], pop[best].copy())
        feasible = fitness[:, 0] == 0.0
        stats = GenerationStats(
            generation=generation,
            best_violation=float(fitness[best, 0]),
            best_ppm=float(fitness[best, 1]),
            best_mean_field=float(fitness[best, 2]),
            mean_ppm_feasible=float(np.mean(fitness[feasible, 1])) if feasible.any() else math.nan,
            feasible_fraction=float(feasible.mean()),
            duplicate_fraction=1.0 - len(set(keys)) / len(keys),
            elapsed=time.perf_counter() - t0,
        )
        history.append(stats)
        if progress is not None:
            progress(stats)

    best_genes = tuple(int(g) for g in best_ever[2])
    violation, ppm, mean_field, mass = cache.store[np.asarray(best_genes, dtype=pop.dtype).tobytes()]
    return GAResult(
        best_genes=best_genes,
        best=Evaluation(ppm=ppm, mean_field=mean_field, mass=mass, violation=violation),
        history=tuple(history),
        elapsed=time.perf_counter() - start,
        evaluations=len(cache.store),
    )
