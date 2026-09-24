"""Exportação CAD do suporte dos ímãs (STEP/STL) e lista de materiais.

Implementação prevista para a Fase 7 (build123d). Por enquanto só existe a
interface, para que o resto do pacote já saiba onde isso vai ficar.
"""

from __future__ import annotations

from pathlib import Path

from halbach_ic.geometry import Design


def export_design(design: Design, outdir: Path, clearance: float = 0.2e-3) -> list[Path]:
    """Gera os arquivos STEP/STL do suporte e a lista de materiais.

    Args:
        design: solução a fabricar.
        outdir: pasta de saída.
        clearance: folga de montagem de cada cavidade [m].

    Raises:
        NotImplementedError: sempre, até a Fase 7.
    """
    raise NotImplementedError("exportação CAD entra na Fase 7")
