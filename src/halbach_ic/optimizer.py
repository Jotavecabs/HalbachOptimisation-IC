"""Algoritmo genético (DEAP) para escolher o anel de cada slot.

Cada indivíduo é um vetor de inteiros: o índice da opção de anel em cada slot.
A aptidão é o par ``(violação, ppm)``, comparado lexicograficamente pelo DEAP
(que é o comportamento de ``Fitness`` com mais de um peso). Isso implementa as
regras de Deb sem pesos arbitrários:

1. solução viável sempre vence solução inviável;
2. entre inviáveis, vence a que viola menos;
3. entre viáveis, vence a mais homogênea.
"""

from __future__ import annotations

import math
import random
import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from deap import algorithms, base, tools

from halbach_ic.config import GAConfig
from halbach_ic.objective import Evaluation, Objective


class LexicographicFitness(base.Fitness):
    """Aptidão ``(violação, ppm)``, ambos minimizados, comparados em ordem."""

    weights = (-1.0, -1.0)


class Individual(list):
    """Vetor de genes com aptidão anexada (substitui ``creator.create`` e seu estado global)."""

    def __init__(self, genes: list[int] | tuple[int, ...] = ()) -> None:
        super().__init__(genes)
        self.fitness = LexicographicFitness()


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
    """Número de avaliações realmente calculadas (sem contar o cache)."""


def run_ga(
    objective: Objective,
    n_slots: int,
    n_options: int,
    cfg: GAConfig,
    progress: Callable[[GenerationStats], None] | None = None,
) -> GAResult:
    """Executa o GA.

    Args:
        objective: função objetivo já montada.
        n_slots: número de genes.
        n_options: cada gene fica em ``[0, n_options - 1]``.
        cfg: parâmetros do GA.
        progress: chamada ao fim de cada geração (para log).
    """
    if cfg.seed is not None:
        random.seed(cfg.seed)

    cache: dict[tuple[int, ...], Evaluation] = {}

    def evaluate(individual: Individual) -> tuple[float, float]:
        key = tuple(individual)
        if key not in cache:
            cache[key] = objective.evaluate(key)
        result = cache[key]
        return result.violation, result.ppm

    toolbox = base.Toolbox()
    toolbox.register("gene", random.randint, 0, n_options - 1)
    toolbox.register("individual", tools.initRepeat, Individual, toolbox.gene, n_slots)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)
    toolbox.register("evaluate", evaluate)
    toolbox.register("mate", tools.cxTwoPoint)
    # Correção do bug 1: mutFlipBit fazia "not gene", levando todo gene a 0 ou 1.
    toolbox.register("mutate", tools.mutUniformInt, low=0, up=n_options - 1, indpb=cfg.gene_mutation_prob)
    toolbox.register("select", tools.selTournament, tournsize=cfg.tournament_size)

    start = time.perf_counter()
    population = toolbox.population(n=cfg.population)
    for ind in population:
        ind.fitness.values = toolbox.evaluate(ind)
    hall_of_fame = tools.HallOfFame(1)
    hall_of_fame.update(population)

    history: list[GenerationStats] = []
    for generation in range(1, cfg.generations + 1):
        t0 = time.perf_counter()
        offspring = algorithms.varAnd(
            toolbox.select(population, len(population)), toolbox, cfg.crossover_prob, cfg.mutation_prob
        )
        for ind in offspring:
            if not ind.fitness.valid:
                ind.fitness.values = toolbox.evaluate(ind)
        population[:] = offspring
        hall_of_fame.update(population)

        best = tools.selBest(population, 1)[0]
        best_eval = cache[tuple(best)]
        feasible_ppm = [ind.fitness.values[1] for ind in population if ind.fitness.values[0] == 0.0]
        stats = GenerationStats(
            generation=generation,
            best_violation=best_eval.violation,
            best_ppm=best_eval.ppm,
            best_mean_field=best_eval.mean_field,
            mean_ppm_feasible=float(np.mean(feasible_ppm)) if feasible_ppm else math.nan,
            feasible_fraction=len(feasible_ppm) / len(population),
            duplicate_fraction=1.0 - len({tuple(ind) for ind in population}) / len(population),
            elapsed=time.perf_counter() - t0,
        )
        history.append(stats)
        if progress is not None:
            progress(stats)

    best_genes = tuple(int(g) for g in hall_of_fame[0])
    return GAResult(
        best_genes=best_genes,
        best=cache[best_genes],
        history=tuple(history),
        elapsed=time.perf_counter() - start,
        evaluations=len(cache),
    )
