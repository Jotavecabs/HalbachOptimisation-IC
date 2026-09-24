"""Linha de comando.

Exemplos::

    uv run halbach-ic info --scenario head
    uv run halbach-ic run --scenario head
    uv run halbach-ic run --scenario limb --population 2000 --generations 30
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import time
from pathlib import Path

from halbach_ic.config import DEFAULT_CONFIG_PATH, ScenarioConfig, available_scenarios, load_config
from halbach_ic.optimizer import GenerationStats
from halbach_ic.pipeline import RunResult, design_space, evaluation_grid, run


def _print_generation(stats: GenerationStats) -> None:
    status = "viável" if stats.best_violation == 0 else f"violação {stats.best_violation:.3g}"
    print(
        f"geração {stats.generation:4d} | {stats.best_ppm:10.1f} ppm | {stats.best_mean_field * 1e3:7.3f} mT | "
        f"{status:>16} | viáveis {stats.feasible_fraction:5.1%} | repetidos {stats.duplicate_fraction:5.1%} | "
        f"{stats.elapsed:5.2f} s"
    )


def _info(cfg: ScenarioConfig) -> None:
    space = design_space(cfg)
    grid = evaluation_grid(cfg)
    n_points = int(grid.mask(cfg.domain.symmetry).sum())
    print(f"cenário: {cfg.name}")
    print(f"DSV: {cfg.domain.dsv_diameter * 1e3:.0f} mm, grade {grid.axis.size}^3, "
          f"{n_points} pontos avaliados ({cfg.domain.symmetry})")
    print(f"modelo de campo: {cfg.model.backend}")
    print(f"campo alvo: {cfg.field.target * 1e3:.1f} ± {cfg.field.tolerance * 1e3:.1f} mT, "
          f"direção {math.degrees(cfg.field.direction):.0f}°")
    print(f"{space.n_slots} slots (anéis em z = ±{max(max(s) for s in space.slots) * 1e3:.0f} mm), "
          f"{space.n_options} opções por slot -> {space.n_options:.0f}^{space.n_slots} = "
          f"{float(space.n_options) ** space.n_slots:.2e} combinações")
    print(f"tabela de campos: {n_points * space.n_slots * space.n_options * 4 / 1e6:.1f} MB (float32)")
    mass = space.mass_table()
    print(f"massa possível: {mass.min(axis=1).sum():.1f} a {mass.max(axis=1).sum():.1f} kg "
          f"(limite {cfg.constraints.max_magnet_mass:.1f} kg)")
    print("\nopções de anel:")
    for i, ring in enumerate(space.options):
        radii = ", ".join(f"{r * 1e3:.1f}" for r in ring.band_radii)
        print(f"  [{i:2d}] bore Ø{2 * ring.bore_radius * 1e3:6.1f} mm | raios das bandas {radii} mm | "
              f"ímãs {ring.n_magnets} | {ring.mass:.2f} kg/anel")
    for bore, reason in space.rejected:
        print(f"  recusado: bore {bore * 1e3:.1f} mm -> {reason}")


def _result_dict(result: RunResult) -> dict:
    design = result.design
    return {
        "scenario": result.cfg.name,
        "genes": list(design.genes),
        "rings": [
            {
                "z_mm": z * 1e3,
                "bore_diameter_mm": 2 * ring.bore_radius * 1e3,
                "band_radii_mm": [r * 1e3 for r in ring.band_radii],
                "n_magnets": list(ring.n_magnets),
            }
            for z, ring in design.rings()
        ],
        "optimization": {
            "symmetry": result.cfg.domain.symmetry,
            "ppm": result.ga.best.ppm,
            "mean_field_mT": result.ga.best.mean_field * 1e3,
            "violation": result.ga.best.violation,
        },
        "full_sphere": {"ppm": result.full_ppm, "mean_field_mT": result.full_mean_field * 1e3},
        "mass_kg": design.mass,
        "n_magnets": design.n_magnets,
        "free_bore_diameter_mm": design.free_bore_diameter * 1e3,
        "timing_s": {"precompute": result.precompute_time, "ga": result.ga.elapsed},
        "evaluations": result.ga.evaluations,
        "history": [dataclasses.asdict(h) for h in result.ga.history],
        "config": dataclasses.asdict(result.cfg),
    }


def _run(cfg: ScenarioConfig, outdir: Path, show: bool) -> None:
    result = run(cfg, progress=_print_generation)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "resultado.json").write_text(json.dumps(_result_dict(result), indent=2, ensure_ascii=False))

    from halbach_ic.visualization import save_basic_report

    paths = save_basic_report(result, outdir)
    best = result.ga.best
    print("\n=== melhor solução ===")
    print(f"genes: {list(result.design.genes)}")
    print(f"otimização ({cfg.domain.symmetry}): {best.ppm:.1f} ppm, {best.mean_field * 1e3:.3f} mT, "
          f"{'viável' if best.feasible else f'INVIÁVEL (violação {best.violation:.3g})'}")
    print(f"esfera inteira: {result.full_ppm:.1f} ppm, {result.full_mean_field * 1e3:.3f} mT")
    print(f"massa: {result.design.mass:.2f} kg em {result.design.n_magnets} ímãs; "
          f"bore livre Ø{result.design.free_bore_diameter * 1e3:.1f} mm")
    print(f"tempo: pré-cálculo {result.precompute_time:.1f} s, GA {result.ga.elapsed:.1f} s "
          f"({result.ga.evaluations} avaliações distintas)")
    print(f"arquivos em {outdir}: resultado.json, " + ", ".join(p.name for p in paths))
    if show:
        import matplotlib.pyplot as plt
        from matplotlib.image import imread

        for path in paths:
            plt.figure()
            plt.imshow(imread(path))
            plt.axis("off")
        plt.show()


def main(argv: list[str] | None = None) -> None:
    """Ponto de entrada de ``halbach-ic``."""
    parser = argparse.ArgumentParser(prog="halbach-ic", description="Otimização de arranjos Halbach")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="arquivo TOML")
    sub = parser.add_subparsers(dest="command", required=True)

    info = sub.add_parser("info", help="mostra o espaço de busca sem otimizar")
    info.add_argument("--scenario", required=True)

    run_cmd = sub.add_parser("run", help="otimiza e salva resultados e gráficos")
    run_cmd.add_argument("--scenario", required=True)
    run_cmd.add_argument("--out", type=Path, default=None, help="pasta de saída (padrão: results/<cenário>_<data>)")
    run_cmd.add_argument("--population", type=int, default=None, help="sobrescreve ga.population")
    run_cmd.add_argument("--generations", type=int, default=None, help="sobrescreve ga.generations")
    run_cmd.add_argument("--seed", type=int, default=None, help="sobrescreve ga.seed")
    run_cmd.add_argument("--backend", choices=["dipole", "cuboid"], default=None, help="sobrescreve model.backend")
    run_cmd.add_argument("--show", action="store_true", help="abre os gráficos ao final")

    args = parser.parse_args(argv)
    if args.scenario not in available_scenarios(args.config):
        parser.error(f"cenário '{args.scenario}' não existe; disponíveis: {available_scenarios(args.config)}")
    cfg = load_config(args.scenario, args.config)

    if args.command == "info":
        _info(cfg)
        return

    overrides = {k: v for k, v in {"population": args.population, "generations": args.generations,
                                    "seed": args.seed}.items() if v is not None}
    if overrides:
        cfg = dataclasses.replace(cfg, ga=dataclasses.replace(cfg.ga, **overrides))
    if args.backend is not None:
        cfg = dataclasses.replace(cfg, model=dataclasses.replace(cfg.model, backend=args.backend))
    outdir = args.out or Path("results") / f"{cfg.name}_{time.strftime('%Y%m%d_%H%M%S')}"
    _run(cfg, outdir, args.show)


if __name__ == "__main__":
    main()
