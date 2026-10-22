"""Busca, por força bruta, os arranjos de anéis iguais que atendem a todos os requisitos.

Varre número de anéis, espaçamento, raio do bore e número de camadas (o resto
fica como na configuração de referência do viabilidade.toml), aplica os
critérios (campo alvo, bore mínimo, massa máxima e faixa de comprimento) e
lista os mais homogêneos. Foi assim que as configurações de referência do
viabilidade.toml foram escolhidas.

Usa o modelo de dipolo (rápido) por padrão; confira o escolhido com o modelo
exato rodando ``halbach-ic viabilidade``.

Uso::

    uv run python scripts/buscar_referencia.py --scenario head
    uv run python scripts/buscar_referencia.py --scenario limb --bore 75 140 5 --camadas 1 2
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

from halbach_ic.config import load_config
from halbach_ic.viability.params import PARAMS
from halbach_ic.viability.simulate import METRICS, simulate_many
from halbach_ic.viability.sweeps import load_plan, viability_code


def inclusive(start: float, stop: float, step: float) -> list[float]:
    values, v = [], start
    while v <= stop + 1e-9:
        values.append(round(v, 9))
        v += step
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", default="head")
    parser.add_argument("--aneis", type=float, nargs=3, default=[15, 60, 1], metavar=("INI", "FIM", "PASSO"))
    parser.add_argument("--espacamento", type=float, nargs=3, default=[13, 40, 1], metavar=("INI", "FIM", "PASSO"))
    parser.add_argument("--bore", type=float, nargs=3, default=None, metavar=("INI", "FIM", "PASSO"),
                        help="raio do bore em mm (padrão: head 135-200, limb 75-140, passo 5)")
    parser.add_argument("--camadas", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--modelo", choices=["dipole", "cuboid"], default="dipole")
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--csv", type=Path, default=None, help="salva todos os viáveis neste CSV")
    args = parser.parse_args()

    plan = load_plan(load_config(args.scenario))
    bore = args.bore or ([135, 200, 5] if args.scenario == "head" else [75, 140, 5])
    requests = [plan.base.with_(n_rings=n, ring_spacing_mm=s, bore_radius_mm=b, n_bands=k)
                for n in inclusive(*args.aneis) for s in inclusive(*args.espacamento)
                for b in inclusive(*bore) for k in args.camadas]
    t0 = time.perf_counter()
    results = simulate_many(requests, args.modelo, plan.general.n_surface // 2, plan.general.n_workers)
    viable = sorted((r for r in results if viability_code(r, plan.criteria) == 0), key=lambda r: r.metrics["ppm"])
    print(f"{len(requests)} arranjos simulados em {time.perf_counter() - t0:.0f} s; {len(viable)} atendem a "
          f"todos os requisitos (modelo {args.modelo}).\n")
    print(f"{'#':>3} {'anéis':>5} {'espaç.':>7} {'bore Ø':>7} {'camadas':>7} {'B0 (mT)':>8} {'homog.':>9} "
          f"{'ppm':>8} {'massa':>7} {'compr.':>7}")
    for i, r in enumerate(viable[: args.top], 1):
        p, m = r.params, r.metrics
        print(f"{i:3d} {p.n_rings:5d} {p.ring_spacing_mm:5.0f}mm {2 * p.bore_radius_mm:5.0f}mm {p.n_bands:7d} "
              f"{m['b0_mT']:8.2f} {m['homogeneity_pct']:8.3f}% {m['ppm']:8.0f} {m['mass_kg']:5.1f}kg "
              f"{m['length_mm'] / 10:5.1f}cm")
    if args.csv:
        with open(args.csv, "w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow([*PARAMS, *METRICS])
            for r in viable:
                writer.writerow([getattr(r.params, k) for k in PARAMS] + [f"{r.metrics[k]:.6g}" for k in METRICS])
        print(f"\nviáveis salvos em {args.csv}")


if __name__ == "__main__":
    main()
