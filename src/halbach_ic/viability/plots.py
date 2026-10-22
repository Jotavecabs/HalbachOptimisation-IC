"""Gráficos da análise de viabilidade (matplotlib).

Cada função devolve uma ``Figure``. Convenções em todos os gráficos:

* linha/faixa cinza = campo alvo (50 mT) e sua tolerância;
* linha vermelha tracejada = limite de massa;
* estrela = configuração de referência (base);
* inomogeneidade em escala logarítmica (varia por ordens de grandeza).
"""

from __future__ import annotations

import math

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import colors
from matplotlib.figure import Figure
from matplotlib.patches import Patch
from numpy.typing import NDArray

from halbach_ic.viability.params import PARAMS
from halbach_ic.viability.simulate import METRICS
from halbach_ic.viability.sweeps import STATUS_LABELS, AnalysisData, Criteria, LineData, MapData, viability_code

STATUS_COLORS = {
    0: "#2ca02c",  # viável
    1: "#ffdd57",  # campo fora
    2: "#ff9f40",  # ppm
    3: "#d62728",  # massa
    4: "#9467bd",  # bore
    5: "#7f7f7f",  # geometria
}

LINE_PANELS = ("b0_mT", "ppm", "mass_kg", "efficiency_mT_per_kg")


def _fmt(value: float) -> str:
    """Número curto para legendas (vírgula decimal)."""
    text = f"{value:g}"
    return text.replace(".", ",")


def _series_label(line: LineData, value: float | None) -> str:
    if value is None:
        return "configuração de referência"
    info = PARAMS[line.sweep.series]  # type: ignore[index]
    return f"{info.label} = {_fmt(value)}" + (f" {info.unit}" if info.unit else "")


def _decorate_metric_axis(ax, metric: str, criteria: Criteria) -> None:
    info = METRICS[metric]
    ax.set_ylabel(info.axis_label())
    if info.log:
        ax.set_yscale("log")
    if metric == "b0_mT":
        ax.axhspan(criteria.target_mT - criteria.tolerance_mT, criteria.target_mT + criteria.tolerance_mT,
                   color="0.85", zorder=0)
        ax.axhline(criteria.target_mT, color="0.4", lw=1, ls="--", label=f"alvo {_fmt(criteria.target_mT)} mT")
    if metric == "mass_kg":
        ax.axhline(criteria.max_mass_kg, color="tab:red", lw=1, ls="--",
                   label=f"limite {_fmt(criteria.max_mass_kg)} kg")
    if metric == "ppm" and criteria.max_ppm is not None:
        ax.axhline(criteria.max_ppm, color="tab:orange", lw=1, ls="--", label=f"limite {_fmt(criteria.max_ppm)} ppm")
    ax.grid(True, which="both", alpha=0.3)


def plot_line(line: LineData, base_value: float, criteria: Criteria, scenario: str) -> Figure:
    """Painel 2×2 (campo, inomogeneidade, massa, campo por massa) em função de ``x``."""
    sweep = line.sweep
    x_info = PARAMS[sweep.x]
    x = np.array(sweep.x_values, dtype=float)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.5), layout="constrained", sharex=True)
    for ax, metric in zip(axes.flat, LINE_PANELS):
        for value in line.results:
            ax.plot(x, line.metric(value, metric), "o-", ms=3, lw=1.5, label=_series_label(line, value))
        ax.axvline(base_value, color="k", lw=0.8, ls=":")
        _decorate_metric_axis(ax, metric, criteria)
        ax.set_title(METRICS[metric].label)
    for ax in axes[1]:
        ax.set_xlabel(x_info.axis_label())
    axes[0, 0].legend(fontsize=8)
    if criteria.max_mass_kg:
        axes[1, 0].legend(fontsize=8)
    title = f"{scenario}: efeito de {x_info.lower}"
    if sweep.series:
        title += f" para vários valores de {PARAMS[sweep.series].lower}"
    fig.suptitle(title + "\n(linha pontilhada vertical = valor da configuração de referência)", fontsize=11)
    return fig


def _edges(values: NDArray[np.float64]) -> NDArray[np.float64]:
    """Bordas das células de um eixo a partir dos centros."""
    if values.size == 1:
        return np.array([values[0] - 0.5, values[0] + 0.5])
    mid = (values[1:] + values[:-1]) / 2
    return np.concatenate([[2 * values[0] - mid[0]], mid, [2 * values[-1] - mid[-1]]])


def _mark_base(ax, m: MapData, base) -> None:
    bx, by = getattr(base, m.sweep.x), getattr(base, m.sweep.y)
    xs, ys = m.sweep.x_values, m.sweep.y_values
    if min(xs) <= bx <= max(xs) and min(ys) <= by <= max(ys):
        ax.plot(bx, by, marker="*", ms=16, mec="k", mfc="white", ls="none", label="referência")


def plot_map(m: MapData, base, criteria: Criteria, scenario: str) -> Figure:
    """Painel 2×2: campo, inomogeneidade, massa e mapa de viabilidade sobre o plano (x, y)."""
    sweep = m.sweep
    x = np.array(sweep.x_values, dtype=float)
    y = np.array(sweep.y_values, dtype=float)
    xe, ye = _edges(x), _edges(y)
    xx, yy = np.meshgrid(x, y)
    fig, axes = plt.subplots(2, 2, figsize=(13, 10), layout="constrained")

    # campo
    ax = axes[0, 0]
    b0 = m.metric("b0_mT")
    mesh = ax.pcolormesh(xe, ye, b0, cmap="viridis", shading="flat")
    fig.colorbar(mesh, ax=ax, label=METRICS["b0_mT"].axis_label())
    if np.nanmin(b0) < criteria.target_mT < np.nanmax(b0):
        cs = ax.contour(xx, yy, b0, levels=[criteria.target_mT], colors="white", linewidths=2)
        ax.clabel(cs, fmt=lambda v: f"{_fmt(v)} mT", fontsize=9)
        ax.contour(xx, yy, b0, levels=[criteria.target_mT - criteria.tolerance_mT,
                                       criteria.target_mT + criteria.tolerance_mT],
                   colors="white", linewidths=1, linestyles="--")
    ax.set_title("Campo B0 no centro (linha branca = alvo)")

    # inomogeneidade
    ax = axes[0, 1]
    ppm = m.metric("ppm")
    finite = ppm[np.isfinite(ppm) & (ppm > 0)]
    if finite.size:
        norm = colors.LogNorm(vmin=finite.min(), vmax=finite.max())
        mesh = ax.pcolormesh(xe, ye, ppm, cmap="magma_r", norm=norm, shading="flat")
        fig.colorbar(mesh, ax=ax, label=METRICS["ppm"].axis_label() + " — escala log")
        decades = [10.0**k for k in range(int(math.ceil(math.log10(finite.min()))),
                                          int(math.floor(math.log10(finite.max()))) + 1)]
        if decades:
            cs = ax.contour(xx, yy, ppm, levels=decades, colors="k", linewidths=0.8)
            ax.clabel(cs, fmt=lambda v: f"{v:,.0f}".replace(",", " "), fontsize=8)
    ax.set_title("Inomogeneidade no DSV (mais claro = melhor)")

    # massa
    ax = axes[1, 0]
    mass = m.metric("mass_kg")
    mesh = ax.pcolormesh(xe, ye, mass, cmap="cividis", shading="flat")
    fig.colorbar(mesh, ax=ax, label=METRICS["mass_kg"].axis_label())
    if np.nanmin(mass) < criteria.max_mass_kg < np.nanmax(mass):
        cs = ax.contour(xx, yy, mass, levels=[criteria.max_mass_kg], colors="tab:red", linewidths=2)
        ax.clabel(cs, fmt=lambda v: f"limite {_fmt(v)} kg", fontsize=9)
    ax.set_title("Massa dos ímãs (linha vermelha = limite)")

    # viabilidade
    ax = axes[1, 1]
    codes = m.codes(criteria)
    present = sorted(set(codes.flat))
    cmap = colors.ListedColormap([STATUS_COLORS[c] for c in range(6)])
    ax.pcolormesh(xe, ye, codes, cmap=cmap, norm=colors.BoundaryNorm(np.arange(-0.5, 6.5), 6), shading="flat")
    ax.legend(handles=[Patch(color=STATUS_COLORS[c], label=STATUS_LABELS[c]) for c in present],
              loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, fontsize=8)
    ax.set_title("Viabilidade (primeiro critério que falha)")

    for ax in axes.flat:
        ax.set_xlabel(PARAMS[sweep.x].axis_label())
        ax.set_ylabel(PARAMS[sweep.y].axis_label())
        _mark_base(ax, m, base)
    fig.suptitle(f"{scenario}: {PARAMS[sweep.x].lower} × {PARAMS[sweep.y].lower}\n"
                 "(estrela = configuração de referência; células cinza = geometria impossível)", fontsize=11)
    return fig


def plot_tradeoff(data: AnalysisData) -> Figure:
    """Massa × inomogeneidade de todos os arranjos dos mapas, colorido pelo campo."""
    crit = data.plan.criteria
    results = [r for m in data.maps for row in m.results for r in row if r.status == "ok"]
    fig, ax = plt.subplots(figsize=(9, 6.5), layout="constrained")
    if not results:
        ax.text(0.5, 0.5, "sem arranjos válidos", ha="center", transform=ax.transAxes)
        return fig
    mass = np.array([r.metrics["mass_kg"] for r in results])
    ppm = np.array([r.metrics["ppm"] for r in results])
    b0 = np.array([r.metrics["b0_mT"] for r in results])
    on_target = np.array([viability_code(r, crit) == 0 for r in results])
    sc = ax.scatter(mass, ppm, c=b0, cmap="viridis", s=12, alpha=0.7)
    fig.colorbar(sc, ax=ax, label=METRICS["b0_mT"].axis_label())
    ax.scatter(mass[on_target], ppm[on_target], s=40, facecolors="none", edgecolors="tab:red", linewidths=1.2,
               label="viável (campo no alvo, massa e bore ok)")
    base = data.base
    if base.status == "ok":
        ax.plot(base.metrics["mass_kg"], base.metrics["ppm"], marker="*", ms=16, mec="k", mfc="white",
                ls="none", label="referência")
    ax.axvline(crit.max_mass_kg, color="tab:red", ls="--", lw=1, label=f"limite de massa {_fmt(crit.max_mass_kg)} kg")
    ax.set_yscale("log")
    ax.set_xlabel(METRICS["mass_kg"].axis_label())
    ax.set_ylabel(METRICS["ppm"].axis_label())
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=8)
    ax.set_title(f"{data.plan.scenario}: compromisso entre massa e homogeneidade\n"
                 "(cada ponto é um arranjo dos mapas de calor; embaixo e à esquerda = melhor)", fontsize=11)
    return fig
