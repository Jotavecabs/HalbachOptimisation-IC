"""Gráficos (matplotlib).

Fase 1: os três gráficos do código original, corrigidos (eixos certos,
unidades, títulos, colorbar). O conjunto completo entra na Fase 6.
Cada função devolve a ``Figure``; quem chama decide se salva ou mostra.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.figure import Figure

from halbach_ic.optimizer import GenerationStats
from halbach_ic.pipeline import FieldMap, RunResult

T_TO_MT = 1e3
M_TO_MM = 1e3


def plot_convergence(history: tuple[GenerationStats, ...]) -> Figure:
    """Homogeneidade do melhor indivíduo por geração (escala log)."""
    fig, ax = plt.subplots(figsize=(7, 4))
    gen = [h.generation for h in history]
    feasible = [h.best_violation == 0 for h in history]
    ppm = np.array([h.best_ppm for h in history])
    ax.semilogy(gen, ppm, color="0.3", lw=1, label="melhor da geração")
    ax.semilogy(np.array(gen)[feasible], ppm[feasible], "o", ms=3, color="tab:blue", label="viável")
    ax.set_xlabel("Geração")
    ax.set_ylabel("Homogeneidade pico a pico (ppm)")
    ax.set_title("Convergência do GA")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    return fig


def plot_profiles(fmap: FieldMap, target_field: float) -> Figure:
    """Componente de B0 ao longo de x, y e z passando pelo centro."""
    grid = fmap.grid
    center = grid.axis.size // 2
    axis_mm = grid.axis * M_TO_MM
    profiles = {
        "x": fmap.component[:, center, center],
        "y": fmap.component[center, :, center],
        "z": fmap.component[center, center, :],
    }
    fig, ax = plt.subplots(figsize=(7, 4))
    for name, values in profiles.items():
        ax.plot(axis_mm, values * T_TO_MT, label=f"ao longo de {name}")
    ax.axhline(target_field * T_TO_MT, color="k", ls="--", lw=1, label="alvo")
    ax.set_xlabel("Posição (mm)")
    ax.set_ylabel("B0 (mT)")
    ax.set_title("Perfis de B0 pelo centro do DSV")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    return fig


def plot_slices(fmap: FieldMap) -> Figure:
    """Mapas de B0 nos três planos centrais."""
    grid = fmap.grid
    center = grid.axis.size // 2
    extent_mm = [grid.axis[0] * M_TO_MM, grid.axis[-1] * M_TO_MM] * 2
    planes = [
        ("Plano xy (z = 0)", fmap.component[:, :, center], "x (mm)", "y (mm)"),
        ("Plano xz (y = 0)", fmap.component[:, center, :], "x (mm)", "z (mm)"),
        ("Plano yz (x = 0)", fmap.component[center, :, :], "y (mm)", "z (mm)"),
    ]
    values = fmap.inside_values() * T_TO_MT
    vmin, vmax = float(np.min(values)), float(np.max(values))
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.4), layout="constrained")
    for ax, (title, data, xlabel, ylabel) in zip(axes, planes):
        image = ax.imshow(data.T * T_TO_MT, origin="lower", extent=extent_mm, vmin=vmin, vmax=vmax, cmap="viridis")
        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
    fig.colorbar(image, ax=axes, label="B0 (mT)", shrink=0.85)
    fig.suptitle("B0 nos planos centrais do DSV")
    return fig


def save_basic_report(result: RunResult, outdir: Path) -> list[Path]:
    """Salva os gráficos da Fase 1 em ``outdir`` e devolve os caminhos."""
    outdir.mkdir(parents=True, exist_ok=True)
    figures = {
        "convergencia.png": plot_convergence(result.ga.history),
        "perfis.png": plot_profiles(result.field, result.cfg.field.target),
        "cortes.png": plot_slices(result.field),
    }
    paths = []
    for name, fig in figures.items():
        path = outdir / name
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        paths.append(path)
    return paths

