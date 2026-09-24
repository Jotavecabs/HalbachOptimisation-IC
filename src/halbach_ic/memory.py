"""Estimativa de uso de memória e aviso antes de estourar a RAM.

O tamanho da tabela de campos é ``pontos × slots × opções × 4 bytes`` e cresce
muito rápido quando se abre mais liberdade de projeto (mais slots, mais
opções, grade mais fina ou esfera inteira). A estimativa é feita antes de
alocar qualquer coisa.
"""

from __future__ import annotations

from dataclasses import dataclass

import psutil

from halbach_ic.field_model import FIELD_CHUNK_PAIRS

WARN_FRACTION = 0.5
"""Avisa quando a estimativa passa desta fração da RAM disponível."""

BYTES_PER_PAIR_CUBOID = 3 * 8 * 8
"""Memória temporária do modelo exato por par (ponto, ímã): ~8 arrays (…, 3) de float64."""


class InsufficientMemoryError(MemoryError):
    """A configuração não cabe na RAM disponível."""


@dataclass(frozen=True)
class MemoryEstimate:
    """Memória prevista para uma execução [bytes]."""

    table: int
    """Tabela de campos em float32 (uma cópia, compartilhada entre processos)."""
    evaluation: int
    """Blocos de avaliação (um por processo)."""
    field_model: int
    """Arrays temporários do modelo de campo durante o pré-cálculo (um por processo)."""

    @property
    def total(self) -> int:
        return self.table + max(self.evaluation, self.field_model)


def estimate_memory(
    n_points: int,
    n_slots: int,
    n_options: int,
    n_workers: int,
    chunk_bytes: int,
    field_chunk_pairs: int = FIELD_CHUNK_PAIRS,
) -> MemoryEstimate:
    """Estima a memória de uma execução.

    Args:
        n_points: pontos de avaliação.
        n_slots: posições otimizáveis.
        n_options: opções por posição.
        n_workers: processos.
        chunk_bytes: memória de trabalho de cada bloco de avaliação.
        field_chunk_pairs: pares (ponto, ímã) por bloco no modelo de campo.
    """
    table = n_points * n_slots * n_options * 4
    # bloco float64 + a linha float32 lida da tabela
    evaluation = n_workers * int(chunk_bytes * 1.5)
    field_model = n_workers * field_chunk_pairs * BYTES_PER_PAIR_CUBOID
    return MemoryEstimate(table=table, evaluation=evaluation, field_model=field_model)


def available_memory() -> int:
    """RAM disponível agora [bytes]."""
    return int(psutil.virtual_memory().available)


def format_bytes(n: float) -> str:
    """Formata bytes em KB/MB/GB."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    raise AssertionError  # inalcançável


def check_memory(estimate: MemoryEstimate, available: int | None = None) -> str | None:
    """Compara a estimativa com a RAM disponível.

    Returns:
        Uma mensagem de aviso se a estimativa passar de ``WARN_FRACTION`` da RAM
        disponível, senão ``None``.

    Raises:
        InsufficientMemoryError: se a estimativa passar da RAM disponível.
    """
    available = available_memory() if available is None else available
    need = estimate.total
    detail = (f"previsto {format_bytes(need)} (tabela {format_bytes(estimate.table)}) "
              f"para {format_bytes(available)} disponíveis")
    hints = ("para reduzir: domain.symmetry = \"octant\", grade mais grossa (grid_spacing_mm), "
             "menos opções de raio, menos processos (performance.n_workers) ou "
             "blocos menores (performance.eval_chunk_mb)")
    if need > available:
        raise InsufficientMemoryError(f"memória insuficiente: {detail}. {hints}")
    if need > WARN_FRACTION * available:
        return f"AVISO: uso alto de memória, {detail}. {hints}"
    return None
