"""Quantifica o erro de avaliar a homogeneidade só no octante positivo (item 6).

Para soluções aleatórias do espaço de busca, compara o ppm calculado no
octante (x, y, z >= 0) com o ppm na esfera inteira, e mede quanto o campo
deixa de ser simétrico por espelhamento em x e em y.

Uso::

    uv run python scripts/quantify_octant_error.py --scenario head
"""

from __future__ import annotations

import argparse
import dataclasses
import math

import numpy as np

from halbach_ic.config import load_config
from halbach_ic.field_model import DipoleBackend
from halbach_ic.objective import homogeneity_ppm
from halbach_ic.pipeline import build_objective, design_space, evaluation_grid


def mirror_asymmetry_ppm(grid, component: np.ndarray, axis: int) -> float:
    """max |B(p) - B(p espelhado no eixo)| / média, em ppm, dentro do DSV."""
    mask = grid.sphere_mask()
    mirrored = np.flip(component, axis=axis)
    diff = np.abs(component - mirrored)[mask]
    return float(diff.max() / np.mean(component[mask]) * 1e6)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", default="head")
    parser.add_argument("--samples", type=int, default=300)
    args = parser.parse_args()

    base = load_config(args.scenario)
    rng = np.random.default_rng(1)
    backend = DipoleBackend()
    print(f"cenário {base.name}: DSV {base.domain.dsv_diameter * 1e3:.0f} mm, grade {base.domain.grid_spacing * 1e3:.0f} mm")

    for direction_deg in (0.0, -90.0):
        cfg = dataclasses.replace(base, field=dataclasses.replace(base.field, direction=math.radians(direction_deg)))
        space = design_space(cfg)
        grid = evaluation_grid(cfg)
        full = build_objective(cfg, space, grid, backend, symmetry="full").table
        octant = build_objective(cfg, space, grid, backend, symmetry="octant").table
        parities = sorted({tuple(n % 2 for n in ring.n_magnets) for ring in space.options})

        err_range, err_mean_simple, err_ppm_simple, err_ppm_weighted = [], [], [], []
        for _ in range(args.samples):
            genes = rng.integers(0, space.n_options, space.n_slots)
            f, o = full.total_field(genes), octant.total_field(genes)
            ppm_full = homogeneity_ppm(f)
            err_range.append(abs(np.ptp(o) / np.ptp(f) - 1))
            err_mean_simple.append(abs(np.mean(o) / np.mean(f) - 1))
            err_ppm_simple.append(abs(homogeneity_ppm(o) / ppm_full - 1))
            err_ppm_weighted.append(abs(homogeneity_ppm(o, octant.weights) / ppm_full - 1))

        # assimetria do campo de um anel isolado (opção 0, slot central)
        component = np.full(grid.shape, np.nan)
        component[grid.sphere_mask()] = full.values[:, 0, 0]
        asym_x = mirror_asymmetry_ppm(grid, component, axis=0)
        asym_y = mirror_asymmetry_ppm(grid, component, axis=1)

        print(f"\nB0 em {direction_deg:+.0f}°  (paridade de N por banda nas opções: {parities})")
        print(f"  erro relativo máximo do octante vs esfera inteira ({args.samples} soluções aleatórias):")
        print(f"    pico a pico (max - min):         {max(err_range):.1e}")
        print(f"    média simples (como no original): {max(err_mean_simple):.1e}")
        print(f"    ppm com média simples:            {max(err_ppm_simple):.1e}")
        print(f"    ppm com média ponderada (novo):   {max(err_ppm_weighted):.1e}")
        print(f"  assimetria de espelho de um anel isolado (z = 0, opção 0):")
        print(f"    x -> -x: {asym_x:.1e} ppm | y -> -y: {asym_y:.1e} ppm")


if __name__ == "__main__":
    main()
