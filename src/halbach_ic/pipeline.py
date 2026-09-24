"""Monta as peças (geometria, grade, tabela, objetivo, GA) a partir da configuração."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from halbach_ic.config import ScenarioConfig, Symmetry
from halbach_ic.domain import EvaluationGrid, make_grid
from halbach_ic.field_model import FieldBackend, get_backend
from halbach_ic.geometry import Design, DesignSpace, MagnetSpec, build_design_space
from halbach_ic.objective import Objective, build_field_table, field_unit_vector, homogeneity_ppm
from halbach_ic.optimizer import GAResult, GenerationStats, run_ga


def magnet_spec(cfg: ScenarioConfig) -> MagnetSpec:
    """Ímã descrito na configuração."""
    return MagnetSpec(size=cfg.magnet.size, remanence=cfg.magnet.remanence, density=cfg.magnet.density)


def design_space(cfg: ScenarioConfig) -> DesignSpace:
    """Espaço de busca descrito na configuração."""
    return build_design_space(
        magnet=magnet_spec(cfg),
        bore_radius_candidates=cfg.ring.bore_radius_candidates,
        n_bands=cfg.ring.n_bands,
        band_gap=cfg.ring.band_gap,
        magnet_gap=cfg.ring.magnet_gap,
        field_direction=cfg.field.direction,
        angle_offset=cfg.ring.angle_offset,
        n_rings=cfg.stack.n_rings,
        ring_spacing=cfg.stack.ring_spacing,
        axial_gap=cfg.stack.axial_gap,
        min_bore_diameter=cfg.constraints.min_bore_diameter,
    )


def evaluation_grid(cfg: ScenarioConfig) -> EvaluationGrid:
    """Grade de avaliação descrita na configuração."""
    return make_grid(cfg.domain.dsv_diameter, cfg.domain.grid_spacing)


def build_objective(
    cfg: ScenarioConfig,
    space: DesignSpace,
    grid: EvaluationGrid,
    backend: FieldBackend,
    symmetry: Symmetry | None = None,
) -> Objective:
    """Pré-calcula a tabela de campos e monta a função objetivo."""
    symmetry = symmetry or cfg.domain.symmetry
    table = build_field_table(
        space, grid.points(symmetry), backend, cfg.field.direction, weights=grid.weights(symmetry)
    )
    return Objective(
        table=table,
        mass_table=space.mass_table(),
        target_field=cfg.field.target,
        field_tolerance=cfg.field.tolerance,
        max_mass=cfg.constraints.max_magnet_mass,
    )


@dataclass(frozen=True)
class FieldMap:
    """Campo de uma solução na grade inteira (NaN fora do DSV)."""

    grid: EvaluationGrid
    vector: NDArray[np.float64]
    """B [T], forma (n, n, n, 3)."""
    component: NDArray[np.float64]
    """Componente na direção de B0 [T], forma (n, n, n)."""

    def inside_values(self) -> NDArray[np.float64]:
        """Componente na direção de B0 nos pontos do DSV."""
        return self.component[self.grid.sphere_mask()]


def field_map(design: Design, grid: EvaluationGrid, backend: FieldBackend, field_direction: float) -> FieldMap:
    """Calcula o campo da solução na esfera inteira do DSV."""
    mask = grid.sphere_mask()
    vector = np.full((*grid.shape, 3), np.nan)
    vector[mask] = backend.field(grid.points("full"), design.magnets())
    component = vector @ field_unit_vector(field_direction)
    return FieldMap(grid=grid, vector=vector, component=component)


@dataclass(frozen=True)
class RunResult:
    """Tudo o que uma execução produz."""

    cfg: ScenarioConfig
    design: Design
    ga: GAResult
    field: FieldMap
    full_ppm: float
    """Homogeneidade na esfera inteira (independe da simetria usada na otimização) [ppm]."""
    full_mean_field: float
    """Campo médio na esfera inteira [T]."""
    precompute_time: float
    """Tempo de pré-cálculo da tabela [s]."""


def run(
    cfg: ScenarioConfig,
    progress: Callable[[GenerationStats], None] | None = None,
    log: Callable[[str], None] = print,
) -> RunResult:
    """Executa o fluxo completo: geometria, pré-cálculo, GA e avaliação final na esfera inteira."""
    backend = get_backend(cfg.model.backend)
    space = design_space(cfg)
    grid = evaluation_grid(cfg)
    for bore, reason in space.rejected:
        log(f"candidato recusado (bore {bore * 1e3:.1f} mm): {reason}")
    log(f"{space.n_slots} slots x {space.n_options} opções; simetria: {cfg.domain.symmetry}; "
        f"modelo de campo: {backend.name}")

    t0 = time.perf_counter()
    objective = build_objective(cfg, space, grid, backend)
    precompute_time = time.perf_counter() - t0
    log(f"tabela de campos: {objective.table.values.nbytes / 1e6:.1f} MB, {precompute_time:.1f} s")

    ga = run_ga(objective, space.n_slots, space.n_options, cfg.ga, progress)
    design = Design(space, ga.best_genes)
    fmap = field_map(design, grid, backend, cfg.field.direction)
    inside = fmap.inside_values()
    return RunResult(
        cfg=cfg,
        design=design,
        ga=ga,
        field=fmap,
        full_ppm=homogeneity_ppm(inside),
        full_mean_field=float(np.mean(inside)),
        precompute_time=precompute_time,
    )
