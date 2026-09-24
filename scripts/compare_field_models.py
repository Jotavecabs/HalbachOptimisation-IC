"""Compara o modelo de dipolo pontual com o campo exato do cubo (magpylib).

Parte 1 — um cubo isolado: erro relativo do dipolo em função da distância e
do tamanho do ímã. O erro relativo só depende de r/a (invariância de escala),
então os dados também são mostrados em função de r/a com o ajuste C (a/r)^4.

Parte 2 — arranjo completo: para cada cenário, compara os dois modelos em
(a) soluções aleatórias, (b) a solução ótima encontrada com cada modelo, e
(c) o quanto a solução otimizada com dipolo perde quando avaliada com o
modelo exato.

Saídas em DOCS/resultados/fase2/: CSV, JSON e PNG.

Uso::

    uv run python scripts/compare_field_models.py
    uv run python scripts/compare_field_models.py --quick   # GA menor, para testar
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import time
from pathlib import Path

import matplotlib
import matplotlib.ticker

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

from halbach_ic.config import ScenarioConfig, load_config  # noqa: E402
from halbach_ic.field_model import CuboidBackend, DipoleBackend  # noqa: E402
from halbach_ic.geometry import Design, MagnetArray, MagnetSpec  # noqa: E402
from halbach_ic.objective import homogeneity_ppm  # noqa: E402
from halbach_ic.optimizer import run_ga  # noqa: E402
from halbach_ic.pipeline import build_objective, design_space, evaluation_grid  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "DOCS" / "resultados" / "fase2"
SIZES_MM = (6.0, 10.0, 12.0, 15.0, 20.0)


def fibonacci_sphere(n: int) -> np.ndarray:
    """``n`` direções quase uniformes na esfera unitária."""
    i = np.arange(n) + 0.5
    phi = np.arccos(1 - 2 * i / n)
    theta = np.pi * (1 + 5**0.5) * i
    return np.stack([np.cos(theta) * np.sin(phi), np.sin(theta) * np.sin(phi), np.cos(phi)], axis=1)


def single_cube_errors() -> list[dict[str, float]]:
    """Erro relativo máximo e médio (sobre direções e orientações) para cada tamanho e distância."""
    directions = fibonacci_sphere(400)
    orientations = np.linspace(0, np.pi / 4, 4)
    rows = []
    for size_mm in SIZES_MM:
        spec = MagnetSpec(size=size_mm * 1e-3, remanence=1.3, density=7500.0)
        for ratio in np.geomspace(1.5, 40, 25):
            r = ratio * spec.size
            errs = []
            for angle in orientations:
                magnet = MagnetArray(spec, np.zeros((1, 3)), np.array([angle]))
                exact = CuboidBackend().field(r * directions, magnet)
                dipole = DipoleBackend().field(r * directions, magnet)
                errs.append(np.linalg.norm(exact - dipole, axis=1) / np.linalg.norm(exact, axis=1))
            errs = np.concatenate(errs)
            rows.append({"size_mm": size_mm, "distance_mm": r * 1e3, "r_over_a": ratio,
                         "max_rel_error": float(errs.max()), "mean_rel_error": float(errs.mean())})
    return rows


def fit_coefficient(rows: list[dict[str, float]], min_ratio: float = 5.0) -> float:
    """Ajuste de C em erro_max = C (a/r)^4 usando só r/a >= ``min_ratio``."""
    data = [(r["r_over_a"], r["max_rel_error"]) for r in rows if r["r_over_a"] >= min_ratio]
    ratio, err = np.array(data).T
    return float(np.exp(np.mean(np.log(err * ratio**4))))


def plot_single_cube(rows: list[dict[str, float]], coef: float) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), layout="constrained")
    for size_mm in SIZES_MM:
        sub = [r for r in rows if r["size_mm"] == size_mm]
        axes[0].loglog([r["distance_mm"] for r in sub], [r["max_rel_error"] * 1e6 for r in sub],
                       "o-", ms=3, label=f"cubo de {size_mm:.0f} mm")
        axes[1].loglog([r["r_over_a"] for r in sub], [r["max_rel_error"] * 1e6 for r in sub], "o", ms=3,
                       label=f"cubo de {size_mm:.0f} mm")
    ratio = np.geomspace(1.5, 40, 100)
    axes[1].loglog(ratio, coef * ratio**-4 * 1e6, "k--", label=f"ajuste {coef:.3f}·(a/r)$^4$")
    axes[0].set_xlabel("Distância ao centro do cubo (mm)")
    axes[1].set_xlabel("Distância / aresta (r/a)")
    for ax in axes:
        ax.set_ylabel("Erro relativo máximo do dipolo (ppm)")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=8)
    axes[1].set_xticks([1.5, 2, 3, 5, 10, 20, 40])
    axes[1].xaxis.set_major_formatter(matplotlib.ticker.ScalarFormatter())
    axes[1].xaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    axes[0].set_title("Erro do dipolo por distância e tamanho")
    axes[1].set_title("Mesmos dados em função de r/a")
    fig.savefig(OUT / "erro_dipolo_cubo_isolado.png", dpi=150)
    plt.close(fig)


def compare_scenario(cfg: ScenarioConfig, n_random: int) -> dict:
    """Compara os modelos num cenário: soluções aleatórias e ótimos de cada modelo."""
    space, grid = design_space(cfg), evaluation_grid(cfg)
    objectives, timing = {}, {}
    for backend in (DipoleBackend(), CuboidBackend()):
        t0 = time.perf_counter()
        objectives[backend.name] = build_objective(cfg, space, grid, backend)
        timing[backend.name] = time.perf_counter() - t0
        print(f"  tabela {backend.name}: {timing[backend.name]:.1f} s")
    dip, exa = objectives["dipole"], objectives["cuboid"]

    # (a) soluções aleatórias
    rng = np.random.default_rng(2)
    ppm_d, ppm_e, mean_err, point_err = [], [], [], []
    for _ in range(n_random):
        genes = rng.integers(0, space.n_options, space.n_slots)
        fd, fe = dip.table.total_field(genes), exa.table.total_field(genes)
        ed, ee = dip.evaluate(genes), exa.evaluate(genes)
        ppm_d.append(ed.ppm)
        ppm_e.append(ee.ppm)
        mean_err.append((ed.mean_field - ee.mean_field) / ee.mean_field)
        point_err.append(np.max(np.abs(fd - fe)) / ee.mean_field)
    ppm_d, ppm_e = np.array(ppm_d), np.array(ppm_e)
    rho = float(spearmanr(ppm_d, ppm_e).statistic)

    # (b, c) otimização com cada modelo, avaliação com o exato
    optima = {}
    for name, objective in objectives.items():
        result = run_ga(objective, space.n_slots, space.n_options, cfg.ga)
        exact_eval = exa.evaluate(result.best_genes)
        dipole_eval = dip.evaluate(result.best_genes)
        optima[name] = {
            "genes": list(result.best_genes),
            "ppm_own_model": result.best.ppm,
            "mean_field_mT_own_model": result.best.mean_field * 1e3,
            "ppm_exact": exact_eval.ppm,
            "mean_field_mT_exact": exact_eval.mean_field * 1e3,
            "feasible_exact": exact_eval.feasible,
            "ppm_dipole": dipole_eval.ppm,
        }
        print(f"  GA com {name}: {result.best.ppm:.1f} ppm no próprio modelo, "
              f"{exact_eval.ppm:.1f} ppm no exato, {exact_eval.mean_field * 1e3:.3f} mT")

    # mapa da diferença no plano central para o ótimo do modelo exato
    design = Design(space, tuple(optima["cuboid"]["genes"]))
    xs, ys = np.meshgrid(grid.axis, grid.axis, indexing="ij")
    plane = np.stack([xs.ravel(), ys.ravel(), np.zeros(xs.size)], axis=1)
    inside = np.linalg.norm(plane, axis=1) <= grid.dsv_radius * (1 + 1e-9)
    unit = np.array([np.cos(cfg.field.direction), np.sin(cfg.field.direction), 0.0])
    magnets = design.magnets()
    diff = np.full(xs.size, np.nan)
    b_exact = CuboidBackend().field(plane[inside], magnets) @ unit
    b_dip = DipoleBackend().field(plane[inside], magnets) @ unit
    diff[inside] = (b_dip - b_exact) / np.mean(b_exact) * 1e6
    fig, ax = plt.subplots(figsize=(5.5, 4.5), layout="constrained")
    extent = [grid.axis[0] * 1e3, grid.axis[-1] * 1e3] * 2
    im = ax.imshow(diff.reshape(xs.shape).T, origin="lower", extent=extent, cmap="RdBu_r")
    fig.colorbar(im, ax=ax, label="(B_dipolo − B_exato) / B_médio (ppm)")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.set_title(f"{cfg.name}: diferença dipolo − exato, plano z = 0")
    fig.savefig(OUT / f"diferenca_mapa_{cfg.name}.png", dpi=150)
    plt.close(fig)

    # dispersão ppm dipolo vs exato
    fig, ax = plt.subplots(figsize=(5.5, 4.5), layout="constrained")
    ax.loglog(ppm_e, ppm_d, ".", ms=4, alpha=0.6)
    lim = [min(ppm_e.min(), ppm_d.min()) * 0.9, max(ppm_e.max(), ppm_d.max()) * 1.1]
    ax.loglog(lim, lim, "k--", lw=1, label="y = x")
    ax.set_xlabel("Homogeneidade com modelo exato (ppm)")
    ax.set_ylabel("Homogeneidade com dipolo (ppm)")
    ax.set_title(f"{cfg.name}: {n_random} soluções aleatórias (Spearman {rho:.3f})")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.savefig(OUT / f"ppm_dipolo_vs_exato_{cfg.name}.png", dpi=150)
    plt.close(fig)

    return {
        "scenario": cfg.name,
        "table_time_s": timing,
        "random_designs": {
            "n": n_random,
            "spearman_ppm": rho,
            "ppm_rel_diff_median": float(np.median(np.abs(ppm_d / ppm_e - 1))),
            "ppm_rel_diff_max": float(np.max(np.abs(ppm_d / ppm_e - 1))),
            "ppm_abs_diff_median": float(np.median(np.abs(ppm_d - ppm_e))),
            "mean_field_rel_diff_median_ppm": float(np.median(np.abs(mean_err)) * 1e6),
            "pointwise_max_diff_ppm_max": float(np.max(point_err) * 1e6),
        },
        "optima": optima,
        # diferença entre os ótimos avaliados no modelo exato: mistura erro do
        # modelo e variação do GA (ver ppm_dipole de cada ótimo para separar)
        "dipole_optimum_loss_ppm": optima["dipole"]["ppm_exact"] - optima["cuboid"]["ppm_exact"],
        "same_design_model_error_ppm": {
            name: opt["ppm_dipole"] - opt["ppm_exact"] for name, opt in optima.items()
        },
        "difference_map_z0_ppm": {"min": float(np.nanmin(diff)), "max": float(np.nanmax(diff))},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="GA com população 1000 e 20 gerações")
    parser.add_argument("--random", type=int, default=300, help="soluções aleatórias por cenário")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    print("parte 1: cubo isolado")
    rows = single_cube_errors()
    coef = fit_coefficient(rows)
    with open(OUT / "erro_dipolo_cubo_isolado.csv", "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    plot_single_cube(rows, coef)
    print(f"  erro máximo ≈ {coef:.4f} (a/r)^4")

    summary = {"single_cube_fit": {"formula": "max_rel_error = C * (a/r)^4", "C": coef, "fit_range": "r/a >= 5"},
               "scenarios": []}
    for name in ("head", "limb"):
        cfg = load_config(name)
        if args.quick:
            cfg = dataclasses.replace(cfg, ga=dataclasses.replace(cfg.ga, population=1000, generations=20))
        print(f"parte 2: cenário {name}")
        summary["scenarios"].append(compare_scenario(cfg, args.random))

    (OUT / "resumo.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nresultados em {OUT}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
