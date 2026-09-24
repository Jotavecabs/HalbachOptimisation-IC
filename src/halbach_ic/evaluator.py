"""Avaliação da população: no processo atual ou dividida entre processos.

O otimizador só enxerga uma função ``genes (P, n_slots) -> BatchEvaluation``.
:class:`ParallelEvaluator` divide a matriz de genes em blocos, um por
processo; a tabela de campos fica em memória compartilhada.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np
from numpy.typing import NDArray

from halbach_ic.objective import BatchEvaluation, FieldTable, Objective
from halbach_ic.parallel import SharedArray, SharedArraySpec, attach_shared, resolve_workers, spawn_context

BatchEvaluator = Callable[[NDArray[np.int64]], BatchEvaluation]

_worker_state: dict[str, Any] = {}
"""Estado do processo trabalhador atual (vazio no processo principal)."""


def _init_worker(spec: SharedArraySpec, weights: NDArray[np.float64], mass_table: NDArray[np.float64],
                 target: float, tolerance: float, max_mass: float, chunk_bytes: int) -> None:
    shm, values = attach_shared(spec)
    table = FieldTable(values=values, points=np.empty((0, 3)), field_direction=0.0, weights=weights)
    _worker_state.update(
        shm=shm,
        objective=Objective(table=table, mass_table=mass_table, target_field=target,
                            field_tolerance=tolerance, max_mass=max_mass, chunk_bytes=chunk_bytes),
    )


def _evaluate_in_worker(genes: NDArray[np.int64]) -> BatchEvaluation:
    return _worker_state["objective"].evaluate_batch(genes)


class ParallelEvaluator:
    """Avalia populações com ``n_workers`` processos. Use como gerenciador de contexto.

    Lotes pequenos (menos de ``min_rows_per_worker`` linhas por processo) são
    avaliados no processo principal, porque o custo de comunicação passaria o
    ganho.
    """

    def __init__(self, objective: Objective, n_workers: int, min_rows_per_worker: int = 500) -> None:
        self.objective = objective
        self.n_workers = resolve_workers(n_workers)
        self.min_rows_per_worker = min_rows_per_worker
        self._shared: SharedArray | None = None
        self._pool: Any = None

    def __enter__(self) -> ParallelEvaluator:
        if self.n_workers > 1:
            obj = self.objective
            self._shared = SharedArray(obj.table.values)
            self._pool = spawn_context().Pool(
                self.n_workers,
                initializer=_init_worker,
                initargs=(self._shared.spec, obj.table.weights, obj.mass_table, obj.target_field,
                          obj.field_tolerance, obj.max_mass, obj.chunk_bytes),
            )
        return self

    def __exit__(self, *exc: object) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool.join()
            self._pool = None
        if self._shared is not None:
            self._shared.close()
            self._shared = None

    def __call__(self, genes: NDArray[np.int64]) -> BatchEvaluation:
        genes = np.atleast_2d(np.asarray(genes, dtype=np.int64))
        workers = min(self.n_workers, len(genes) // self.min_rows_per_worker)
        if self._pool is None or workers <= 1:
            return self.objective.evaluate_batch(genes)
        parts = self._pool.map(_evaluate_in_worker, np.array_split(genes, workers))
        return BatchEvaluation.concatenate(parts)
