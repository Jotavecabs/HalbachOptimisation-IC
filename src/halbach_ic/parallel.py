"""Paralelismo com ``multiprocessing``: pré-cálculo da tabela e memória compartilhada.

Usa sempre o método ``spawn`` (padrão no macOS e no Windows) para ter o mesmo
comportamento em todos os sistemas. Cada processo trabalhador guarda o seu
estado (pontos, modelo, tabela) numa variável própria do processo, preenchida
pelo ``initializer`` do ``Pool``; nada é compartilhado entre módulos.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import sys
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from multiprocessing import shared_memory
from typing import Any

import numpy as np
from numpy.typing import NDArray

from halbach_ic.field_model import FieldBackend, get_backend
from halbach_ic.geometry import HalbachRing, MagnetArray

_worker_state: dict[str, Any] = {}
"""Estado do processo trabalhador atual (vazio no processo principal)."""


def can_spawn() -> bool:
    """``False`` quando o programa principal não é um arquivo (ex.: ``python - <<EOF``).

    Nesse caso o método ``spawn`` não consegue recriar o módulo principal nos
    processos filhos, que falham e são recriados sem parar. Jupyter e arquivos
    ``.py`` funcionam normalmente.
    """
    main_file = getattr(sys.modules.get("__main__"), "__file__", None)
    return main_file is None or os.path.exists(main_file)


def resolve_workers(n_workers: int) -> int:
    """Converte a configuração em número de processos (0 = todos os núcleos)."""
    if n_workers < 0:
        raise ValueError("n_workers deve ser >= 0")
    workers = n_workers or (os.cpu_count() or 1)
    if workers > 1 and not can_spawn():
        warnings.warn("programa principal não é um arquivo .py: usando 1 processo (sem paralelismo)",
                      RuntimeWarning, stacklevel=2)
        return 1
    return workers


def spawn_context() -> mp.context.SpawnContext:
    """Contexto ``spawn`` usado por todos os pools do pacote."""
    return mp.get_context("spawn")


# --------------------------------------------------------------------------
# Pré-cálculo da tabela de campos
# --------------------------------------------------------------------------

FieldTask = tuple[tuple[float, ...], HalbachRing]
"""(posições z do slot, anel) — uma coluna da tabela."""


def _column(task: FieldTask, points: NDArray[np.float64], backend: FieldBackend,
            unit: NDArray[np.float64]) -> NDArray[np.float32]:
    zs, ring = task
    magnets = MagnetArray.concatenate([ring.magnets(z) for z in zs])
    return (backend.field(points, magnets) @ unit).astype(np.float32)


def _init_columns(points: NDArray[np.float64], backend_name: str, unit: NDArray[np.float64]) -> None:
    _worker_state.update(points=points, backend=get_backend(backend_name), unit=unit)


def _column_in_worker(task: FieldTask) -> NDArray[np.float32]:
    return _column(task, _worker_state["points"], _worker_state["backend"], _worker_state["unit"])


def compute_field_columns(
    tasks: Sequence[FieldTask],
    points: NDArray[np.float64],
    backend: FieldBackend,
    field_direction_unit: NDArray[np.float64],
    n_workers: int = 1,
) -> NDArray[np.float32]:
    """Calcula a componente de B na direção de B0 para cada tarefa.

    Args:
        tasks: lista de (posições z, anel).
        points: pontos de avaliação, forma (M, 3).
        backend: modelo de campo (nos trabalhadores é recriado pelo nome).
        field_direction_unit: vetor unitário da direção de B0.
        n_workers: número de processos; 1 calcula no processo atual.

    Returns:
        Array (len(tasks), M) em float32.
    """
    out = np.empty((len(tasks), points.shape[0]), dtype=np.float32)
    workers = min(resolve_workers(n_workers), len(tasks))
    if workers <= 1:
        for i, task in enumerate(tasks):
            out[i] = _column(task, points, backend, field_direction_unit)
        return out
    with spawn_context().Pool(workers, initializer=_init_columns,
                              initargs=(points, backend.name, field_direction_unit)) as pool:
        for i, column in enumerate(pool.imap(_column_in_worker, tasks, chunksize=1)):
            out[i] = column
    return out


def _init_points_field(magnets: MagnetArray, backend_name: str) -> None:
    _worker_state.update(magnets=magnets, backend=get_backend(backend_name))


def _points_field_in_worker(points: NDArray[np.float64]) -> NDArray[np.float64]:
    return _worker_state["backend"].field(points, _worker_state["magnets"])


def compute_field(
    points: NDArray[np.float64], magnets: MagnetArray, backend: FieldBackend, n_workers: int = 1
) -> NDArray[np.float64]:
    """Campo B de um conjunto de ímãs em muitos pontos, dividindo os pontos entre processos."""
    workers = min(resolve_workers(n_workers), max(1, points.shape[0] // 1000))
    if workers <= 1:
        return backend.field(points, magnets)
    with spawn_context().Pool(workers, initializer=_init_points_field, initargs=(magnets, backend.name)) as pool:
        return np.concatenate(pool.map(_points_field_in_worker, np.array_split(points, workers * 4)))


# --------------------------------------------------------------------------
# Memória compartilhada
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SharedArraySpec:
    """O que um trabalhador precisa para abrir um array compartilhado."""

    name: str
    shape: tuple[int, ...]
    dtype: str


class SharedArray:
    """Array NumPy em memória compartilhada, criado e liberado pelo processo principal.

    Os trabalhadores abrem o mesmo bloco com :func:`attach_shared` sem copiar
    os dados, então a tabela de campos existe uma vez só na RAM, qualquer que
    seja o número de processos.
    """

    def __init__(self, array: NDArray[Any]) -> None:
        self._shm = shared_memory.SharedMemory(create=True, size=max(1, array.nbytes))
        self.array: NDArray[Any] = np.ndarray(array.shape, dtype=array.dtype, buffer=self._shm.buf)
        self.array[...] = array
        self.spec = SharedArraySpec(name=self._shm.name, shape=array.shape, dtype=array.dtype.str)

    def close(self) -> None:
        """Libera o bloco (só o processo que criou deve chamar)."""
        del self.array
        self._shm.close()
        self._shm.unlink()

    def __enter__(self) -> SharedArray:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def attach_shared(spec: SharedArraySpec) -> tuple[shared_memory.SharedMemory, NDArray[Any]]:
    """Abre, num trabalhador, um array criado por :class:`SharedArray`.

    Os processos filhos usam o mesmo ``resource_tracker`` do processo
    principal, que guarda os nomes num conjunto: registrar de novo ao abrir não
    duplica nada, e o bloco é liberado uma vez só, por quem criou
    (:meth:`SharedArray.close`). Por isso o trabalhador não deve remover o
    registro: isso apagaria o registro do processo principal.
    """
    shm = shared_memory.SharedMemory(name=spec.name)
    return shm, np.ndarray(spec.shape, dtype=np.dtype(spec.dtype), buffer=shm.buf)
