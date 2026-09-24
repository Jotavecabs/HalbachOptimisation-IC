"""Mede o tempo de cada etapa com 1 processo e com todos os núcleos.

Compara com a linha de base medida antes da Fase 3
(DOCS/resultados/fase3/linha_de_base.json) e salva
DOCS/resultados/fase3/benchmark.json.

Uso::

    uv run python scripts/benchmark.py
"""

from __future__ import annotations

import json
import os
import platform
import time
from pathlib import Path

import psutil

from halbach_ic.config import load_config
from halbach_ic.evaluator import ParallelEvaluator
from halbach_ic.field_model import get_backend
from halbach_ic.geometry import Design
from halbach_ic.memory import format_bytes
from halbach_ic.optimizer import run_ga
from halbach_ic.parallel import resolve_workers
from halbach_ic.pipeline import build_objective, design_space, evaluation_grid, field_map

OUT = Path(__file__).resolve().parents[1] / "DOCS" / "resultados" / "fase3"


def timed(fn):
    t0 = time.perf_counter()
    value = fn()
    return value, time.perf_counter() - t0


def main() -> None:
    all_cores = resolve_workers(0)
    result: dict = {
        "machine": {"cpu": platform.processor() or platform.machine(), "cores": os.cpu_count(),
                    "ram": format_bytes(psutil.virtual_memory().total), "python": platform.python_version()},
        "scenarios": {},
    }
    for name in ("head", "limb"):
        cfg = load_config(name)
        space, grid = design_space(cfg), evaluation_grid(cfg)
        rows: dict = {}
        for backend_name in ("dipole", "cuboid"):
            backend = get_backend(backend_name)
            for workers in (1, all_cores):
                objective, dt = timed(lambda: build_objective(cfg, space, grid, backend, n_workers=workers))
                rows[f"table_{backend_name}_{workers}w_s"] = dt
                print(f"{name}: tabela {backend_name}, {workers} processo(s): {dt:.1f} s", flush=True)
        for workers in (1, all_cores):
            with ParallelEvaluator(objective, workers) as evaluate:
                ga, dt = timed(lambda: run_ga(evaluate, space.n_slots, space.n_options, cfg.ga))
            rows[f"ga_{workers}w_s"] = dt
            rows[f"ga_{workers}w_ppm"] = ga.best.ppm
            rows["ga_evaluations"] = ga.evaluations
            print(f"{name}: GA, {workers} processo(s): {dt:.1f} s ({ga.best.ppm:.1f} ppm)", flush=True)
        design = Design(space, ga.best_genes)
        for workers in (1, all_cores):
            _, dt = timed(lambda: field_map(design, grid, get_backend("cuboid"), cfg.field.direction, workers))
            rows[f"fieldmap_cuboid_{workers}w_s"] = dt
            print(f"{name}: mapa final cuboid, {workers} processo(s): {dt:.1f} s", flush=True)
        rows["table_mb"] = objective.table.values.nbytes / 2**20
        rows["peak_rss_mb"] = psutil.Process().memory_info().rss / 2**20
        result["scenarios"][name] = rows

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "benchmark.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
