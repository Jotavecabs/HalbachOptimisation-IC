"""Mede como o pré-cálculo da tabela (modelo exato) escala com o número de processos.

Uso::

    uv run python scripts/scaling.py --scenario head
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from halbach_ic.config import load_config
from halbach_ic.field_model import CuboidBackend
from halbach_ic.pipeline import build_objective, design_space, evaluation_grid

OUT = Path(__file__).resolve().parents[1] / "DOCS" / "resultados" / "fase3"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario", default="head")
    parser.add_argument("--workers", type=int, nargs="+", default=[1, 2, 4, 6, 8, 10])
    args = parser.parse_args()
    cfg = load_config(args.scenario)
    space, grid = design_space(cfg), evaluation_grid(cfg)
    times: dict[int, float] = {}
    for workers in args.workers:
        t0 = time.perf_counter()
        build_objective(cfg, space, grid, CuboidBackend(), n_workers=workers)
        times[workers] = time.perf_counter() - t0
        print(f"{workers:2d} processos: {times[workers]:6.1f} s  aceleração {times[args.workers[0]] / times[workers]:.2f}",
              flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"escalabilidade_{args.scenario}.json").write_text(json.dumps(times, indent=2))


if __name__ == "__main__":
    main()
